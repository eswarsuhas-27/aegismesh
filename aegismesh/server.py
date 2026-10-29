"""Dependency-free web server: dashboard + JSON API + Server-Sent Events.

    python -m aegismesh.server [--host 127.0.0.1] [--port 8000]
"""
from __future__ import annotations

import argparse
import json
import os
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import recordings, usage
from .config import ROOT, Settings, get_settings
from .llm import LLMError, NebiusClient
from .orchestrator import Run
from .scenarios import BY_ID, SCENARIOS
from .tavily import Tavily

STATIC = Path(__file__).parent / "static"


class ReplayRun:
    """Streams a recorded live run. Makes no API calls."""
    def __init__(self, rec: dict):
        self.id, self.rec, self.events, self.status, self.result = uuid.uuid4().hex[:8], rec, [], "running", None

    def _emit(self, type_, data, ts):
        self.events.append({"i": len(self.events), "ts": ts, "type": type_, "data": data})

    def play(self):
        speed = float(os.environ.get("AEGIS_REPLAY_SPEED", "0.25"))
        self._emit("replay", {"recorded_at": self.rec["recorded_at"], "models": self.rec["models"], "condition": self.rec["condition"]}, time.time())
        prev = None
        for e in self.rec["events"]:
            if prev is not None and speed > 0:
                time.sleep(min(0.6, max(0.0, e["ts"] - prev) * speed))
            prev = e["ts"]
            self._emit(e["type"], e["data"], e["ts"])
        self.result = {"id": self.id, "scenario": self.rec["scenario"], "mode": "replay", "metrics": self.rec["metrics"],
                       "report": self.rec["report"], "events": self.events}
        self.status = "done"


class App:
    def __init__(self, settings: Settings, llm=None, tavily=None):
        self.s, self._llm, self._tavily = settings, llm, tavily
        self.runs = {}
        self.lock = threading.Lock()
        self.public = os.environ.get("AEGIS_PUBLIC") == "1"            # hosted demo: cap live spending
        self.live_budget = int(os.environ.get("AEGIS_LIVE_BUDGET", "12"))   # live AI incidents the demo may run
        self.cooldown = float(os.environ.get("AEGIS_COOLDOWN", "20"))      # seconds between live runs per visitor
        self.live_used, self.last = 0, {}
        (ROOT / "results" / "runs").mkdir(parents=True, exist_ok=True)

    def llm(self):
        if self._llm is None and self.s.nebius_key:
            self._llm = NebiusClient(self.s.nebius_key, self.s.nebius_base, self.s.model_fast, self.s.model_reason, model_heavy=self.s.model_heavy)
        return self._llm

    def tavily(self):
        if self._tavily is None:
            self._tavily = Tavily(self.s.tavily_key, self.s.tavily_base, self.s.tavily_cache, self.s.tavily_mode, credit_budget=self.s.tavily_budget)
        return self._tavily

    def status(self, check: bool) -> dict:
        llm = self.llm()
        nb = {"configured": llm is not None, "base_url": self.s.nebius_base, "models": None, "error": None}
        if llm is not None and check and hasattr(llm, "resolve_models"):
            try:
                fast, reason = llm.resolve_models()
                nb["models"] = {"fast": fast, "reasoning": reason, "heavy": llm.model_heavy}
            except LLMError as e:
                nb["error"] = str(e)[:300]
        elif llm is not None and getattr(llm, "model_reason", ""):
            nb["models"] = {"fast": llm.model_fast, "reasoning": llm.model_reason}
        t = self.tavily()
        return {"nebius": nb, "tavily": {"available": t.available, "status": t.status()}, "recordings": recordings.index(),
                "public": self.public, "live_runs_left": max(0, self.live_budget - self.live_used) if self.public else None, "usage": usage.snapshot(),
                "scenarios": [{"id": s.id, "title": s.title, "description": s.description, "domain": s.domain} for s in SCENARIOS]}

    def start(self, scenario: str, mode: str, research, ip: str = "-"):
        notice = ""
        if mode == "ai" and self.public:
            now = time.time()
            if self.live_used >= self.live_budget:
                mode, notice = "replay", "This demo's live AI budget is used up, so this is a recorded live run."
            elif now - self.last.get(ip, 0) < self.cooldown:
                mode, notice = "replay", f"Live AI runs are limited to one per {int(self.cooldown)}s per visitor, so this is a recorded live run."
            else:
                self.live_used += 1
                self.last[ip] = now
        if mode == "replay":
            rec = recordings.load(scenario)
            if rec is None:
                raise ValueError("no recording exists for this scenario yet (run scripts/finalize_submission.py with your keys)")
            run = ReplayRun(rec)
            threading.Thread(target=run.play, daemon=True).start()
            with self.lock:
                self.runs[run.id] = run
            return run, notice
        run = Run(scenario, mode, research, llm=self.llm() if mode == "ai" else None, tavily=self.tavily())

        def work():
            try:
                res = run.execute()
                (ROOT / "results" / "runs").mkdir(parents=True, exist_ok=True)
                (ROOT / "results" / "runs" / f"{run.id}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
            except Exception as e:  # surface, never hang the stream
                run.emit("fatal", error=f"{type(e).__name__}: {e}")
                run.status = "error"
        with self.lock:
            self.runs[run.id] = run
        threading.Thread(target=work, daemon=True).start()
        return run, notice


def make_handler(app: App):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, obj, code=200):
            b = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            u = urlparse(self.path)
            parts = [p for p in u.path.split("/") if p]
            q = parse_qs(u.query)
            if u.path in ("/", "/index.html"):
                b = (STATIC / "index.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)
            elif u.path == "/api/status":
                self._json(app.status(q.get("check") == ["1"]))
            elif u.path == "/api/eval":
                p = ROOT / "results" / "eval_latest.json"
                self._json(json.loads(p.read_text()) if p.exists() else {"missing": True})
            elif len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "stream":
                run = app.runs.get(parts[2])
                if not run:
                    return self._json({"error": "unknown run"}, 404)
                self._sse(run, int(q.get("after", ["0"])[0]))
            elif len(parts) == 3 and parts[:2] == ["api", "runs"]:
                run = app.runs.get(parts[2])
                self._json(run.result if run and run.result else {"status": run.status if run else "unknown"}, 200 if run else 404)
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            if self.path != "/api/run":
                return self._json({"error": "not found"}, 404)
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            except ValueError:
                return self._json({"error": "invalid JSON"}, 400)
            if body.get("scenario") not in BY_ID or body.get("mode", "ai") not in ("ai", "baseline", "replay"):
                return self._json({"error": "unknown scenario or mode"}, 400)
            research = body.get("research", "always")
            if isinstance(research, str) and research not in ("always", "adaptive", "off"):
                return self._json({"error": "research must be always, adaptive or off"}, 400)
            ip = self.headers.get("X-Forwarded-For", "").split(",")[0].strip() or self.client_address[0]
            try:
                run, notice = app.start(body["scenario"], body.get("mode", "ai"), research, ip)
            except ValueError as e:
                return self._json({"error": str(e)}, 404)
            self._json({"run_id": run.id, "notice": notice})

        def _sse(self, run, i):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            try:
                while True:
                    for e in run.events[i:]:
                        self.wfile.write(f"id: {e['i']}\ndata: {json.dumps(e)}\n\n".encode())
                        i += 1
                    self.wfile.flush()
                    if run.status != "running" and i >= len(run.events):
                        break
                    time.sleep(0.1)
            except (BrokenPipeError, ConnectionResetError):
                pass
    return H


def serve(app: App, host: str, port: int) -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer((host, port), make_handler(app))
    srv.daemon_threads = True
    return srv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0" if os.environ.get("AEGIS_PUBLIC") == "1" else "127.0.0.1")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    a = ap.parse_args()
    app = App(get_settings())
    st = app.status(check=False)
    print(f"AegisMesh dashboard: http://{a.host}:{a.port}")
    print(f"  Nebius Token Factory: {'key found' if st['nebius']['configured'] else 'NO KEY (AI mode disabled; set NEBIUS_API_KEY)'}")
    print(f"  Tavily: {st['tavily']['status']}")
    print(f"  Recordings available for replay: {len(st['recordings'])}; public demo mode: {app.public}")
    serve(app, a.host, a.port).serve_forever()


if __name__ == "__main__":
    main()
