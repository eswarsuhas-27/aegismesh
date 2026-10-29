"""Verify your real keys end to end in ~1 minute:  python scripts/smoke_live.py
Checks: Token Factory auth, NVIDIA model discovery, a real JSON completion, Tavily search, and one full AI incident."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aegismesh.config import get_settings
from aegismesh.llm import LLMError, NebiusClient
from aegismesh.orchestrator import Run
from aegismesh.tavily import Tavily

s = get_settings()
ok = True
print("1. Token Factory")
if not s.nebius_key:
    sys.exit("   FAIL: NEBIUS_API_KEY not set (put it in .env)")
c = NebiusClient(s.nebius_key, s.nebius_base, s.model_fast, s.model_reason, model_heavy=s.model_heavy)
try:
    models = c.list_models()
    print(f"   {len(models)} models visible; NVIDIA ones: {[m for m in models if m.lower().startswith('nvidia/')][:8]}")
    fast, reason = c.resolve_models()
    print(f"   fast={fast}\n   mid (investigator, planner)={reason}\n   heavy (skeptic)={c.model_heavy}")
    data, meta = c.chat_json("planner", "Reply with JSON only.", 'Return {"pong": true}.', max_tokens=200)
    print(f"   completion OK: {data} ({meta['latency_s']}s, {meta['prompt_tokens'] + meta['completion_tokens']} tokens)")
except LLMError as e:
    sys.exit(f"   FAIL: {e}\n   Tip: if the model is not found, set NEBIUS_MODEL_REASON / NEBIUS_MODEL_FAST in .env to an id from your catalog.")

print("2. Tavily")
t = Tavily(s.tavily_key, s.tavily_base, s.tavily_cache, s.tavily_mode, credit_budget=s.tavily_budget)
print(f"   {t.status()}")
if t.mode == "live":
    r = t.search("PostgreSQL too many connections max_connections troubleshooting", 3)
    print(f"   OK: {len(r['results'])} results, first: {r['results'][0]['url'] if r['results'] else 'none'}")
else:
    print("   (research will be reported as unavailable until TAVILY_API_KEY is set)")

print("3. Full incident (db_pool_misconfig)")
res = Run("db_pool_misconfig", "ai", t.available, llm=c, tavily=t).execute()
m = res["metrics"]
print(f"   recovered={m['recovered']} root_cause_correct={m['root_cause_correct']} degraded={m['degraded']} "
      f"calls={m['llm_calls']} citations_verified={m['verified_citations']} research={m['research_status']}")
for e in res["events"]:
    if e["type"] in ("agent_error", "llm_call") and not e["data"].get("ok", False):
        print("   problem:", e["data"])
        ok = False
sys.exit(0 if ok and m["recovered"] and not m["degraded"] else 1)
