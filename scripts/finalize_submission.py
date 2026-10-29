"""One command that produces everything that needs your keys (run it on your own machine):

    python scripts/finalize_submission.py            # full: record demos + evaluate all conditions
    python scripts/finalize_submission.py --quick    # vendor-style scenarios only (fewer API calls)

1. smoke test of Token Factory + Tavily            (stops on failure)
2. records live demo runs -> results/recordings/    (powers the free replay mode on the hosted demo)
3. evaluation: baseline vs AI without research vs AI with research (always / adaptive)
4. writes deliverables/RESULTS.md with the measured numbers and the real API spend
Tavily answers are cached, so re-running costs no extra Tavily credits for repeated queries.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from aegismesh import recordings, usage                      # noqa: E402
from aegismesh.config import get_settings                    # noqa: E402
from aegismesh.llm import NebiusClient                       # noqa: E402
from aegismesh.orchestrator import Run                       # noqa: E402
from aegismesh.tavily import Tavily                          # noqa: E402

FULL_RECORD = [("db_pool_misconfig", "adaptive"), ("db_pool_misconfig__vendor", "always"), ("hl7_channel_disabled", "adaptive"),
               ("hl7_cert_expired__vendor", "always"), ("monitor_gw_memory_leak", "adaptive"), ("traffic_surge__vendor", "always"),
               ("ehr_db_conn_limit__vendor", "always")]
QUICK_RECORD = [("db_pool_misconfig__vendor", "always"), ("hl7_channel_disabled", "adaptive"), ("monitor_gw_memory_leak", "adaptive")]


def _pct(x):
    return "n/a" if x is None else f"{round(100 * x)}%"


def build_results_md(ev: dict, led: dict, recs: list) -> str:
    runs = ev["runs"]
    L = [f"# Measured results ({ev['meta']['finished']})", "",
         f"Models used: {', '.join(ev['meta']['models']) or 'none (baseline only)'}  ",
         f"Scenarios: {len(ev['meta']['scenarios'])}, repeats: {ev['meta']['repeats']}. Numbers below are recorded runs, not estimates.", "",
         "## Outcome by condition", "| condition | success | root cause correct | recovered | blocked unsafe candidates | red-team blocked |", "|---|---|---|---|---|---|"]
    for c, s in ev["summary"].items():
        L.append(f"| {c} | {_pct(s['success_rate'])} | {_pct(s['root_cause_accuracy'])} | {_pct(s['recovery_rate'])} | {s['candidates_blocked']}/{s['candidates_total']} | {_pct(s['probe_block_rate'])} |")
    L += ["", "## Tavily: effect and cost, by log style",
          "Plain = explicit config-change lines in the logs. Vendor-style = real-looking vendor errors (SQLSTATE, Redis, JVM, DICOM, OpenSSL) with no config-change line, so the cause has to be looked up.", "",
          "| condition | logs | incidents | root cause correct | Tavily searches issued | billed (live) | correct root causes per search |", "|---|---|---|---|---|---|---|"]
    for c in ev["summary"]:
        for label, vendor in (("plain", False), ("vendor-style", True)):
            m = [r["metrics"] for r in runs if r["condition"] == c and r["scenario"].endswith("__vendor") == vendor]
            if not m:
                continue
            rc = [x["root_cause_correct"] for x in m if x["root_cause_correct"] is not None]
            sr = sum(x["tavily_searches"] for x in m)
            L.append(f"| {c} | {label} | {len(m)} | {_pct(sum(rc) / len(rc)) if rc else 'n/a'} | {sr} | {sum(x['tavily_live'] for x in m)} | "
                     f"{round(sum(rc) / sr, 2) if rc and sr else 'n/a'} |")

    def acc(cond, vendor):
        m = [r["metrics"]["root_cause_correct"] for r in runs if r["condition"] == cond and r["scenario"].endswith("__vendor") == vendor and r["metrics"]["root_cause_correct"] is not None]
        return (sum(m) / len(m), len(m)) if m else None
    L += ["", "## Reading the Tavily comparison (generated from the numbers above)"]
    for label, vendor in (("plain", False), ("vendor-style", True)):
        a, b = acc("ai_no_research", vendor), acc("ai_research", vendor)
        if a and b:
            d = round(100 * (b[0] - a[0]))
            L.append(f"- {label} logs: root-cause accuracy {_pct(a[0])} without research vs {_pct(b[0])} with research (n={b[1]}), a difference of {d:+d} points.")
    ad = [r["metrics"] for r in runs if r["condition"] == "ai_adaptive"]
    al = [r["metrics"] for r in runs if r["condition"] == "ai_research"]
    if ad and al:
        L.append(f"- Adaptive research issued {sum(x['tavily_searches'] for x in ad)} searches versus {sum(x['tavily_searches'] for x in al)} for always-on research, "
                 f"skipping research in {sum(x['research_status'] == 'skipped' for x in ad)} of {len(ad)} incidents.")
    L += ["- Small samples: treat differences of a few points as noise. The sample is small and the scenarios are simulated.", "",
          "## Real API spend (cumulative ledger on this machine)",
          f"- Nebius Token Factory: {led.get('nebius_calls', 0)} calls, {led.get('nebius_tokens', 0)} tokens, {led.get('ai_incidents', 0)} AI incidents",
          f"- Tavily: {led.get('tavily_live_searches', 0)} live (billed) searches; cache hits are free and repeated runs reuse them",
          "", "## Recorded live runs available for free replay", *([f"- {r['scenario']} ({r['condition']}), {r['recorded_at']}" for r in recs] or ["- none"])]
    return "\n".join(L) + "\n"


def step(title):
    print(f"\n=== {title} ===", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--skip-record", action="store_true")
    a = ap.parse_args()
    s = get_settings()

    step("1/4 smoke test")
    if subprocess.call([sys.executable, "scripts/smoke_live.py"], cwd=ROOT) != 0:
        sys.exit("Smoke test failed. Fix that first (paste its output to Claude; it never prints your keys).")

    if not a.skip_record:
        step("2/4 recording live demo runs")
        llm = NebiusClient(s.nebius_key, s.nebius_base, s.model_fast, s.model_reason, model_heavy=s.model_heavy)
        tav = Tavily(s.tavily_key, s.tavily_base, s.tavily_cache, s.tavily_mode, credit_budget=s.tavily_budget)
        for sid, mode in (QUICK_RECORD if a.quick else FULL_RECORD):
            r = Run(sid, "ai", mode, llm=llm, tavily=tav).execute()
            m = r["metrics"]
            if m["degraded"]:
                print(f"  SKIPPED {sid}: AI run degraded (not recording a failed run)")
                continue
            recordings.save(r)
            print(f"  recorded {sid} [{mode}] recovered={m['recovered']} success={m['success']} rc={m['root_cause_correct']} "
                  f"tavily={m['tavily_searches']} searches ({m['tavily_live']} billed)", flush=True)

    step("3/4 evaluation")
    from aegismesh import eval as ev
    argv = ["--repeats", str(a.repeats), "--scenarios", "vendor" if a.quick else "all"]
    if ev.main(argv) != 0:
        sys.exit("evaluation produced no results")

    step("4/4 deliverables/RESULTS.md")
    data = json.loads((ROOT / "results" / "eval_latest.json").read_text(encoding="utf-8"))
    out = ROOT / "deliverables" / "RESULTS.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(build_results_md(data, usage.snapshot(), recordings.index()), encoding="utf-8")
    print(f"wrote {out}\n\nNext: open deliverables/00_START_HERE.md")


if __name__ == "__main__":
    main()
