import json
import tempfile
import urllib.request

from aegismesh import llm as L
from aegismesh.llm import LLMError, NebiusClient, extract_json, pick_models
from aegismesh.orchestrator import Run
from aegismesh.scenarios import SCENARIOS as _ALL
from aegismesh.server import App, serve
from aegismesh.config import get_settings
from aegismesh.tavily import Tavily, TavilyUnavailable

from tests.fakes import OracleLLM, nebius_mock, tavily_mock

SCENARIOS = [s for s in _ALL if not s.expects_escalation]


def test_extract_json_variants():
    assert extract_json('<think>hmm {"a":0}</think>```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! Here it is: {"a": {"b": [1,2]}} thanks') == {"a": {"b": [1, 2]}}
    try:
        extract_json("no json here"); assert False
    except ValueError:
        pass


def test_model_selection_is_nvidia_only():
    ids = ["meta-llama/Llama-3.3-70B-Instruct", "nvidia/Nemotron-3-Nano-Omni", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B", "nvidia/nemotron-3-super-120b-a12b"]
    fast, reason = pick_models(ids)
    assert fast == "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B" and reason == "nvidia/nemotron-3-super-120b-a12b"
    assert pick_models(["nvidia/Foo-Nemotron-X"]) == ("nvidia/Foo-Nemotron-X",) * 2
    assert L.pick_heavy(ids + ["nvidia/nemotron-3-ultra-550b-a55b"], reason) == "nvidia/nemotron-3-ultra-550b-a55b" and L.pick_heavy(ids, reason) == reason
    try:
        pick_models(["meta-llama/Llama-3.3-70B-Instruct"]); assert False
    except LLMError:
        pass


def test_nebius_client_retries_and_parses():
    srv, url, st = nebius_mock('<think>plan</think>```json\n{"ok": true}\n```', fail_first=1)
    L.time.sleep = lambda s: None
    c = NebiusClient("test-key", url + "/v1/")
    data, meta = c.chat_json("planner", "sys", "user")
    assert data == {"ok": True} and st["chat"] == 2
    assert meta["model"] == "nvidia/nemotron-3-super-120b-a12b" and meta["prompt_tokens"] == 11
    data, meta = c.chat_json("researcher_queries", "s", "u")
    assert meta["model"] == "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
    assert c.chat_json("skeptic", "s", "u")[1]["model"] == "nvidia/nemotron-3-ultra-550b-a55b"   # heavy tier
    srv.shutdown()


def test_nebius_json_mode_fallback():
    srv, url, st = nebius_mock('{"ok": 1}', reject_response_format=True)
    c = NebiusClient("test-key", url)
    assert c.chat_json("planner", "s", "u")[0] == {"ok": 1}
    assert "response_format" not in st["bodies"][-1]
    srv.shutdown()


def test_tavily_live_cache_replay_off():
    srv, url, st = tavily_mock()
    path = tempfile.mktemp(suffix=".json")
    t = Tavily("tvly-test", url, path)
    r1 = t.search("Max connections too low")
    r2 = t.search("max   connections too low")
    assert st["n"] == 1 and not r1["from_cache"] and r2["from_cache"]
    srv.shutdown()
    replay = Tavily("", "http://127.0.0.1:1", path)  # no key, cache present -> replay
    assert replay.mode == "replay" and replay.search("max connections too low")["from_cache"]
    try:
        replay.search("never asked"); assert False
    except TavilyUnavailable:
        pass
    assert Tavily("", "x", tempfile.mktemp()).available is False


def _tav():
    srv, url, st = tavily_mock()
    return srv, Tavily("tvly-test", url, tempfile.mktemp(suffix=".json"))


def test_ai_run_all_scenarios_with_research():
    srv, tav = _tav()
    for s in SCENARIOS:
        r = Run(s.id, "ai", True, llm=OracleLLM(s.id), tavily=tav).execute()
        m = r["metrics"]
        assert m["recovered"] and m["root_cause_correct"] and m["unnecessary_remediations"] == 0, (s.id, m)
        assert m["verified_citations"] >= 1 and m["research_status"] == "ok"
        assert "RECOVERED" in r["report"] and "example.test" in r["report"]
    srv.shutdown()


def test_bad_model_cannot_cause_harm_or_fake_citations():
    srv, tav = _tav()
    s = "db_pool_misconfig"
    r = Run(s, "ai", True, llm=OracleLLM(s, lying=True), tavily=tav).execute()
    m, ev = r["metrics"], r["events"]
    assert m["recovered"] and m["unverified_citations"] == 1 and m["verified_citations"] == 1
    cands = {e["data"]["action"]: e["data"] for e in ev if e["type"] == "candidate"}
    assert not cands["block_traffic(gateway, percent=100.0)"]["viable"] and not cands["restart_service(db)"]["viable"]
    assert any(e["type"] == "rejected_proposals" for e in ev)
    assert [e["data"]["action"] for e in ev if e["type"] == "executed"] == ["revert_config(db, key=max_connections)"]
    hyp = next(e for e in ev if e["type"] == "hypotheses")["data"]
    assert hyp["warnings"] and "L999" not in hyp["hypotheses"][0]["evidence"]
    srv.shutdown()


def test_research_unavailable_is_reported_not_faked():
    s = "cache_oom_config"
    r = Run(s, "ai", True, llm=OracleLLM(s), tavily=Tavily("", "x", "")).execute()
    assert r["metrics"]["research_status"] == "unavailable" and r["metrics"]["sources"] == 0
    assert r["metrics"]["recovered"] and "No citations were used" in r["report"]


def test_research_off_and_baseline_modes():
    s = "traffic_surge"
    r = Run(s, "ai", False, llm=OracleLLM(s)).execute()
    assert r["metrics"]["research_status"] == "disabled" and r["metrics"]["recovered"]
    b = Run(s, "baseline", False).execute()
    assert b["metrics"]["recovered"] and b["metrics"]["llm_calls"] == 0 and b["metrics"]["root_cause_correct"] is None


def test_llm_outage_degrades_to_baseline_safely():
    class Down:
        def chat_json(self, *a, **k):
            raise LLMError("HTTP 503")
    r = Run("orders_memory_leak", "ai", True, llm=Down()).execute()
    assert r["metrics"]["degraded"] and r["metrics"]["recovered"] and any(e["type"] == "agent_error" for e in r["events"])


def test_replan_after_all_candidates_fail():
    class Bad(OracleLLM):
        def _planner(self, user, gt):
            if "PREVIOUS ROUND" in user:
                return {"candidates": self._fixes()}
            return {"candidates": [{"action": {"kind": "restart_service", "target": "auth"}, "rationale": "guess"}]}
    r = Run("db_pool_misconfig", "ai", False, llm=Bad("db_pool_misconfig")).execute()
    assert r["metrics"]["recovered"] and any(e["type"] == "replan" for e in r["events"])


def test_http_server_end_to_end():
    s = "db_pool_misconfig"
    app = App(get_settings(), llm=OracleLLM(s), tavily=Tavily("", "x", ""))
    srv = serve(app, "127.0.0.1", 0)
    import threading
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    assert b"AegisMesh" in urllib.request.urlopen(base + "/").read()
    st = json.loads(urllib.request.urlopen(base + "/api/status").read())
    assert len(st["scenarios"]) == 20 and {x["domain"] for x in st["scenarios"]} == {"it", "hospital"}
    req = urllib.request.Request(base + "/api/run", json.dumps({"scenario": s, "mode": "ai", "research": False}).encode(), {"Content-Type": "application/json"})
    rid = json.loads(urllib.request.urlopen(req).read())["run_id"]
    types = []
    for line in urllib.request.urlopen(f"{base}/api/runs/{rid}/stream"):
        if line.startswith(b"data: "):
            types.append(json.loads(line[6:])["type"])
    assert types[0] == "started" and types[-1] == "done" and "verified" in types
    res = json.loads(urllib.request.urlopen(f"{base}/api/runs/{rid}").read())
    assert res["metrics"]["recovered"]
    bad = urllib.request.Request(base + "/api/run", b'{"scenario":"nope"}', {"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(bad); assert False
    except urllib.error.HTTPError as e:
        assert e.code == 400
    srv.shutdown()
