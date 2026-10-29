"""Evaluation harness. Runs recorded experiments; never fabricates numbers.

    python -m aegismesh.eval --repeats 2                       # all conditions
    python -m aegismesh.eval --conditions baseline --repeats 1 # offline, no keys
Writes results/eval_latest.json and results/eval_latest.md
"""
from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict

from .config import ROOT, get_settings
from .llm import NebiusClient
from .orchestrator import Run
from .scenarios import BY_ID, SCENARIOS
from .tavily import Tavily

CONDITIONS = {"baseline": ("baseline", False), "ai_no_research": ("ai", False), "ai_research": ("ai", "always"), "ai_adaptive": ("ai", "adaptive")}


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 2) if xs else None


def summarize(rows):
    out = {}
    for cond, rs in rows.items():
        m = [r["metrics"] for r in rs]
        rc = [x["root_cause_correct"] for x in m if x["root_cause_correct"] is not None]
        out[cond] = {
            "runs": len(m), "recovery_rate": round(sum(x["recovered"] for x in m) / len(m), 2),
            "success_rate": round(sum(x["success"] for x in m) / len(m), 2),
            "mean_clinical_risk_reduction": _mean([x["clinical_risk_start"] - x["clinical_risk_end"] for x in m if x["domain"] == "hospital"]),
            "root_cause_accuracy": round(sum(rc) / len(rc), 2) if rc else None,
            "mean_ticks_to_recovery": _mean([x["ticks_to_recovery"] for x in m]),
            "mean_wall_seconds": _mean([x["wall_seconds"] for x in m]),
            "unnecessary_remediations": sum(x["unnecessary_remediations"] for x in m),
            "candidates_blocked": sum(x["blocked_by_policy"] for x in m), "candidates_total": sum(x["candidates"] for x in m),
            "probe_block_rate": _mean([x["probe_block_rate"] for x in m]),
            "tavily_searches": sum(x["tavily_searches"] for x in m), "tavily_live_searches": sum(x["tavily_live"] for x in m),
            "correct_rc_per_search": (round(sum(rc) / max(1, sum(x["tavily_searches"] for x in m)), 2) if rc and any(x["tavily_searches"] for x in m) else None),
            "verified_citations": sum(x["verified_citations"] for x in m), "unverified_citations": sum(x["unverified_citations"] for x in m),
            "mean_llm_tokens": _mean([x["llm_tokens"] for x in m]), "degraded_runs": sum(x["degraded"] for x in m),
            "llm_prediction_accuracy": _mean([x["llm_prediction_accuracy"] for x in m]),
        }
    return out


def to_markdown(summary, meta, per_scenario) -> str:
    cols = ["success_rate", "recovery_rate", "mean_clinical_risk_reduction", "root_cause_accuracy", "mean_ticks_to_recovery", "mean_wall_seconds", "unnecessary_remediations",
            "candidates_blocked", "probe_block_rate", "tavily_searches", "tavily_live_searches", "correct_rc_per_search", "verified_citations", "mean_llm_tokens", "degraded_runs"]
    L = [f"# AegisMesh evaluation ({meta['finished']})", f"Scenarios: {len(meta['scenarios'])}, repeats: {meta['repeats']}, models: {', '.join(meta['models']) or 'n/a'}", "",
         "| metric | " + " | ".join(summary) + " |", "|---|" + "---|" * len(summary)]
    for c in cols:
        L.append(f"| {c} | " + " | ".join(str(summary[k][c]) for k in summary) + " |")
    L += ["", "## Per scenario (root cause correct / success)", "| scenario | " + " | ".join(summary) + " |", "|---|" + "---|" * len(summary)]
    for sid, d in per_scenario.items():
        L.append(f"| {sid} | " + " | ".join(d.get(k, "-") for k in summary) + " |")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--conditions", default="baseline,ai_no_research,ai_research,ai_adaptive")
    ap.add_argument("--scenarios", default="all", help="all | plain | vendor | comma-separated ids")
    ap.add_argument("--repeats", type=int, default=1)
    a = ap.parse_args(argv)
    s = get_settings()
    conds = [c for c in a.conditions.split(",") if c in CONDITIONS]
    sids = ([x.id for x in SCENARIOS] if a.scenarios == "all" else [x.id for x in SCENARIOS if not x.cryptic] if a.scenarios == "plain"
            else [x.id for x in SCENARIOS if x.cryptic] if a.scenarios == "vendor" else a.scenarios.split(","))
    llm = NebiusClient(s.nebius_key, s.nebius_base, s.model_fast, s.model_reason, model_heavy=s.model_heavy) if s.nebius_key else None
    tav = Tavily(s.tavily_key, s.tavily_base, s.tavily_cache, s.tavily_mode, credit_budget=s.tavily_budget)
    rows, per = defaultdict(list), defaultdict(dict)
    for cond in conds:
        mode, research = CONDITIONS[cond]
        if mode == "ai" and llm is None:
            print(f"skip {cond}: NEBIUS_API_KEY not set"); continue
        if research and not tav.available:
            print(f"skip {cond}: Tavily {tav.status()}"); continue
        for sid in sids:
            res_list = []
            for rep in range(a.repeats):
                r = Run(sid, mode, research, llm=llm, tavily=tav).execute()
                rows[cond].append(r); res_list.append(r["metrics"])
                m = r["metrics"]
                print(f"{cond:15} {sid:24} rep{rep + 1} success={m['success']} recovered={m['recovered']} rc={m['root_cause_correct']} t={m['wall_seconds']}s")
            ok = sum(m["success"] for m in res_list)
            rc = [m["root_cause_correct"] for m in res_list if m["root_cause_correct"] is not None]
            per[sid][cond] = f"{sum(rc)}/{len(rc)} rc, {ok}/{len(res_list)} ok" if rc else f"{ok}/{len(res_list)} ok"
    if not rows:
        print("nothing ran"); return 1
    models = sorted({m for rs in rows.values() for r in rs for m in r["metrics"]["models"]})
    meta = {"finished": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "scenarios": sids, "repeats": a.repeats, "models": models}
    summary = summarize(rows)
    allm = [r["metrics"] for rs in rows.values() for r in rs]
    usage = {"nebius_calls": sum(m["llm_calls"] for m in allm), "nebius_tokens": sum(m["llm_tokens"] for m in allm),
             "tavily_live_searches": tav.live_calls, "tavily_cache_hits": tav.cache_hits, "tavily_credits_used_est": tav.live_calls,
             "incidents_run": len(allm)}
    out = {"meta": meta, "usage": usage, "summary": summary, "per_scenario": per,
           "runs": [{"condition": c, "scenario": r["scenario"], "metrics": r["metrics"]} for c, rs in rows.items() for r in rs]}
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "eval_latest.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    md = to_markdown(summary, meta, per) + (
        f"\n\n## API usage\nNebius: {usage['nebius_calls']} calls, {usage['nebius_tokens']} tokens over {usage['incidents_run']} incidents. "
        f"Tavily: {usage['tavily_live_searches']} live searches (about {usage['tavily_credits_used_est']} credits), {usage['tavily_cache_hits']} answered from cache.")
    (ROOT / "results" / "eval_latest.md").write_text(md, encoding="utf-8")
    print("\n" + md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
