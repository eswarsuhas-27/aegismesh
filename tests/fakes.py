"""Test doubles: an oracle 'model' and local mock Token Factory / Tavily HTTP servers."""
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from aegismesh.scenarios import BY_ID


class OracleLLM:
    """Behaves like a competent model. lying=True adds a fabricated citation and an unsafe/malformed plan."""
    def __init__(self, scenario_id, lying=False):
        self.sc, self.lying, self.calls = BY_ID[scenario_id], lying, []

    def chat_json(self, role, system, user, **kw):
        self.calls.append(role)
        gt = self.sc.root_cause
        meta = {"role": role, "model": "fake/oracle", "latency_s": 0.0, "attempts": 1, "prompt_tokens": 10, "completion_tokens": 5}
        return getattr(self, "_" + role)(user, gt), meta

    def _investigator(self, user, gt):
        ev = [m.group(1) for m in re.finditer(r"^(L\d+) .*?(?:\b%s\b|%s\.)" % (gt["service"], gt["service"]), user, re.M)]
        return {"timeline": [{"log": ev[0], "summary": "first sign"}] if ev else [],
                "hypotheses": [{"id": "H1", "service": gt["service"], "kind": gt["kind"], "statement": "origin of the failure",
                                "confidence": 0.7, "evidence": ev[:3] + ["L999"], "unknowns": []},
                               {"id": "H2", "service": "gateway", "kind": "dependency_failure", "statement": "symptom only",
                                "confidence": 0.2, "evidence": [], "unknowns": []}]}

    def _researcher_queries(self, user, gt):
        return {"queries": [{"query": "connection pool exhausted max connections troubleshooting", "hypothesis": "H1", "purpose": "confirm"}]}

    def _researcher_findings(self, user, gt):
        m = re.search(r"\[S1\][^\n]*\n(.+)", user)
        quote = " ".join(m.group(1).split()[:8]) if m else ""
        f = [{"hypothesis": "H1", "stance": "supports", "claim": "docs match", "source": "S1", "quote": quote}]
        if self.lying:
            f.append({"hypothesis": "H1", "stance": "supports", "claim": "invented", "source": "S1", "quote": "this sentence never appears in any source text"})
            f.append({"hypothesis": "H1", "stance": "supports", "claim": "ghost", "source": "S99", "quote": "x"})
        return {"findings": f}

    def _skeptic(self, user, gt):
        return {"verdicts": [{"hypothesis": "H1", "confidence": 0.85, "confirmed_facts": ["L1", "S1", "L999"], "assumptions": [], "alternative": "none", "would_refute": "healthy logs", "challenge": "ok"},
                             {"hypothesis": "H2", "confidence": 0.1, "confirmed_facts": [], "assumptions": ["x"], "alternative": "", "would_refute": "", "challenge": ""}], "leading": "H1"}

    def _planner(self, user, gt):
        if "PREVIOUS ROUND" in user:
            return {"candidates": self._fixes()}
        c = self._fixes()
        if self.lying:
            hosp = self.sc.domain == "hospital"
            bad = [{"action": {"kind": "purge_queue", "target": "interface_engine", "params": {}}, "rationale": "clear the backlog", "predicts_resolved": True},
                   {"action": {"kind": "format_disk", "target": "ehr_db", "params": {}}, "rationale": "nonsense"},
                   {"action": {"kind": "restart_service", "target": "ehr_db"}, "rationale": "turn it off and on", "predicts_resolved": True}] if hosp else \
                  [{"action": {"kind": "block_traffic", "target": "gateway", "params": {"percent": 100}}, "rationale": "stop everything", "predicts_resolved": True},
                   {"action": {"kind": "format_disk", "target": "db", "params": {}}, "rationale": "nonsense"},
                   {"action": {"kind": "restart_service", "target": "db"}, "rationale": "turn it off and on", "predicts_resolved": True}]
            c = bad + c
        return {"candidates": c}

    def _fixes(self):
        k = {"db_pool_misconfig": ("revert_config", "db", {"key": "max_connections"}), "cache_oom_config": ("revert_config", "cache", {"key": "maxmemory_mb"}),
             "payments_timeout": ("revert_config", "payments", {"key": "upstream_timeout_ms"}), "orders_memory_leak": ("restart_service", "orders", {}),
             "traffic_surge": ("scale_up", "gateway", {"replicas": 4}),
             "hl7_cert_expired": ("renew_certificate", "interface_engine", {}), "hl7_channel_disabled": ("revert_config", "interface_engine", {"key": "channel_enabled"}),
             "pacs_storage_full": ("revert_config", "pacs_storage", {"key": "auto_purge_enabled"}), "ehr_db_conn_limit": ("revert_config", "ehr_db", {"key": "max_connections"}),
             "monitor_gw_memory_leak": ("restart_service", "monitor_gw", {})}[self.sc.id.split("__")[0]]
        fixes = [{"action": {"kind": k[0], "target": k[1], "params": k[2]}, "rationale": "fix", "expected_effect": "recovers", "predicts_resolved": True}]
        if self.sc.id.startswith("monitor_gw_memory_leak"):
            fixes.append({"action": {"kind": "enable_downtime_procedure", "target": "monitor_gw", "params": {}}, "rationale": "manual monitoring while waiting", "predicts_resolved": False})
        return fixes


class _Quiet(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)


def start_server(handler_cls):
    srv = HTTPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}"


def nebius_mock(reply_text, fail_first=0, reject_response_format=False):
    state = {"chat": 0, "bodies": []}

    class H(_Quiet):
        def do_GET(self):
            self._send(200, {"data": [{"id": "meta-llama/Llama-3.3-70B-Instruct"}, {"id": "nvidia/Nemotron-3-Nano-Omni"},
                                       {"id": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"}, {"id": "nvidia/nemotron-3-super-120b-a12b"}, {"id": "nvidia/nemotron-3-ultra-550b-a55b"}]})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["bodies"].append(body); state["chat"] += 1
            assert self.headers["Authorization"] == "Bearer test-key"
            if state["chat"] <= fail_first:
                return self._send(503, {"error": "busy"})
            if reject_response_format and "response_format" in body:
                return self._send(400, {"error": "response_format is not supported"})
            self._send(200, {"model": body["model"], "usage": {"prompt_tokens": 11, "completion_tokens": 7},
                             "choices": [{"message": {"content": reply_text}}]})
    srv, url = start_server(H)
    return srv, url, state


def tavily_mock():
    state = {"n": 0}

    class H(_Quiet):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert self.headers["Authorization"] == "Bearer tvly-test"
            state["n"] += 1
            self._send(200, {"results": [{"title": "Connection limits", "url": "https://example.test/docs/connections", "score": 0.9,
                                          "content": "When max_connections is set too low the server rejects new clients with too many connections errors."}]})
    srv, url = start_server(H)
    return srv, url, state
