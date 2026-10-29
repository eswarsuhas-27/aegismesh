import os
import tempfile

from aegismesh import usage
from aegismesh.orchestrator import Run
from aegismesh.tavily import Tavily, TavilyUnavailable

from tests.fakes import OracleLLM, tavily_mock

SID = "db_pool_misconfig__vendor"


class Decisive(OracleLLM):
    def _investigator(self, user, gt):
        d = super()._investigator(user, gt)
        d["hypotheses"][0]["confidence"], d["hypotheses"][1]["confidence"] = 0.92, 0.05
        return d


class Chatty(OracleLLM):
    def _researcher_queries(self, user, gt):
        q = "postgres too many clients already sqlstate 53300"
        return {"queries": [{"query": q}, {"query": q + " fix"}, {"query": "Postgres too many clients already SQLSTATE 53300 "}, {"query": "ehr login failure"}]}


def _tav(**kw):
    srv, url, st = tavily_mock()
    return srv, st, Tavily("tvly-test", url, tempfile.mktemp(suffix=".json"), **kw)


def test_adaptive_skips_research_when_logs_are_decisive():
    srv, st, tav = _tav()
    llm = Decisive(SID)
    r = Run(SID, "ai", "adaptive", llm=llm, tavily=tav).execute()
    m = r["metrics"]
    assert m["research_status"] == "skipped" and m["tavily_searches"] == 0 and st["n"] == 0
    assert "researcher_queries" not in llm.calls and m["recovered"] and m["root_cause_correct"]
    assert "Skipped to save API credits" in r["report"]
    srv.shutdown()


def test_adaptive_searches_when_ambiguous_and_cache_makes_repeats_free():
    srv, st, tav = _tav()
    m1 = Run(SID, "ai", "adaptive", llm=OracleLLM(SID), tavily=tav).execute()["metrics"]
    m2 = Run(SID, "ai", "adaptive", llm=OracleLLM(SID), tavily=tav).execute()["metrics"]
    assert m1["tavily_live"] == 1 and m1["tavily_searches"] == 1
    assert m2["tavily_live"] == 0 and m2["tavily_searches"] == 1 and st["n"] == 1   # second run: cache hit, zero credits
    srv.shutdown()


def test_duplicate_queries_cost_one_search_each_idea_only():
    srv, st, tav = _tav()
    m = Run(SID, "ai", "always", llm=Chatty(SID), tavily=tav).execute()["metrics"]
    assert m["tavily_searches"] == 2 and st["n"] == 2   # 4 proposed -> 2 distinct (capped at 2)
    srv.shutdown()


def test_credit_budget_is_enforced_and_ledger_counts_real_spend():
    srv, st, tav = _tav(credit_budget=0)
    base = usage.snapshot().get("tavily_live_searches", 0)
    tav.credit_budget = base + 1
    tav.search("first distinct query")
    try:
        tav.search("second distinct query"); assert False
    except TavilyUnavailable as e:
        assert "budget" in str(e)
    assert tav.search("first distinct query")["from_cache"]                       # cache still served after budget is gone
    assert usage.snapshot()["tavily_live_searches"] == base + 1 and st["n"] == 1
    srv.shutdown()


def test_vendor_logs_hide_the_config_change_evidence():
    from aegismesh.scenarios import BY_ID, build
    plain = " ".join(e.message for e in build(BY_ID["db_pool_misconfig"]).logs)
    vendor = " ".join(e.message for e in build(BY_ID["db_pool_misconfig__vendor"]).logs)
    assert "CONFIG_CHANGE" in plain and "CONFIG_CHANGE" not in vendor and "SQLSTATE 53300" in vendor
