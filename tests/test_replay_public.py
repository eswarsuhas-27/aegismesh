import json
import os
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

from aegismesh import recordings
from aegismesh.config import get_settings
from aegismesh.orchestrator import Run
from aegismesh.server import App, serve
from aegismesh.tavily import Tavily

from tests.fakes import OracleLLM

os.environ["AEGIS_REPLAY_SPEED"] = "0"
SID = "hl7_channel_disabled"


def _post(base, body):
    req = urllib.request.Request(base + "/api/run", json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())


def _stream(base, rid):
    return [json.loads(l[6:]) for l in urllib.request.urlopen(f"{base}/api/runs/{rid}/stream") if l.startswith(b"data: ")]


def test_recording_roundtrip_and_public_budget_falls_back_to_free_replay():
    recordings.DIR = Path(tempfile.mkdtemp())
    llm = OracleLLM(SID)
    recordings.save(Run(SID, "ai", "off", llm=llm, tavily=Tavily("", "x", "")).execute())
    assert recordings.index()[0]["scenario"] == SID and recordings.load(SID)["condition"] == "ai_off"
    calls_after_recording = len(llm.calls)

    app = App(get_settings(), llm=llm, tavily=Tavily("", "x", ""))
    app.public, app.live_budget, app.cooldown = True, 1, 3600
    srv = serve(app, "127.0.0.1", 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"

    first = _post(base, {"scenario": SID, "mode": "ai", "research": "off"})          # live, uses the budget
    assert first["notice"] == "" and _stream(base, first["run_id"])[-1]["type"] == "done"
    live_calls = len(llm.calls)
    assert live_calls > calls_after_recording

    second = _post(base, {"scenario": SID, "mode": "ai", "research": "off"})         # same visitor, budget gone -> free replay
    assert "recorded live run" in second["notice"]
    ev = _stream(base, second["run_id"])
    assert ev[0]["type"] == "replay" and ev[-1]["type"] == "done" and "verified" in {e["type"] for e in ev}
    assert len(llm.calls) == live_calls                                                # replay made no model calls
    st = json.loads(urllib.request.urlopen(base + "/api/status").read())
    assert st["public"] and st["live_runs_left"] == 0 and st["recordings"]

    try:
        _post(base, {"scenario": "pacs_storage_full", "mode": "replay"}); assert False   # nothing recorded for this one
    except urllib.error.HTTPError as e:
        assert e.code == 404
    try:
        _post(base, {"scenario": SID, "mode": "ai", "research": "bogus"}); assert False
    except urllib.error.HTTPError as e:
        assert e.code == 400
    srv.shutdown()
