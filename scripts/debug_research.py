"""Debug research for a specific scenario: python scripts/debug_research.py [scenario_id]"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aegismesh.config import get_settings
from aegismesh.llm import NebiusClient
from aegismesh.orchestrator import Run
from aegismesh.tavily import Tavily


def main():
    scenario = sys.argv[1] if len(sys.argv) > 1 else "db_pool_misconfig__vendor"
    s = get_settings()
    if not s.nebius_key:
        sys.exit("NEBIUS_API_KEY not set in .env")
    c = NebiusClient(s.nebius_key, s.nebius_base, s.model_fast, s.model_reason, model_heavy=s.model_heavy)
    t = Tavily(s.tavily_key, s.tavily_base, s.tavily_cache, s.tavily_mode, credit_budget=s.tavily_budget)

    print(f"Running scenario: {scenario} (mode=ai, research=always)")
    res = Run(scenario, "ai", "always", llm=c, tavily=t).execute()
    m = res["metrics"]
    print("\n=== METRICS ===")
    print(f"  recovered={m.get('recovered')}  root_cause_correct={m.get('root_cause_correct')}  degraded={m.get('degraded')}")
    print(f"  tavily_searches={m.get('tavily_searches')}  sources={m.get('sources')}  verified_citations={m.get('verified_citations')}")

    print("\n=== RESEARCH EVENTS ===")
    for e in res["events"]:
        if e["type"] in ("research_query", "research"):
            print(f"  [{e['type']}] {e['data']}")

    print("\n=== REPORT ===")
    print(res["report"])


if __name__ == "__main__":
    main()

