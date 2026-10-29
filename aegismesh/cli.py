"""CLI: python -m aegismesh.cli list | run <scenario> | run --all [--json out.json]"""
from __future__ import annotations

import argparse
import json
import sys

from .runner import run_baseline
from .scenarios import BY_ID, SCENARIOS

ICON = {"healthy": "OK  ", "degraded": "WARN", "down": "DOWN"}


def _health_line(h: dict) -> str:
    return "  ".join(f"{n}:{ICON[s]}" for n, s in h.items())


def print_record(r: dict) -> None:
    print(f"\n=== {r['scenario']}: {r['title']} ===")
    print("Health at detection:\n  " + _health_line(r["health_at_detection"]))
    print("Logs:")
    for line in r["logs_at_detection"][-8:]:
        print("  " + line)
    print(f"\nCandidates ({len(r['candidates'])}), {r['blocked_count']} blocked by policy:")
    for c in r["candidates"]:
        o = c["predicted"]
        if not c["policy"]["allowed"]:
            print(f"  [BLOCKED ] {c['action']:<55} {', '.join(c['policy']['blocked_by'])}")
        else:
            tag = "RESOLVES " if o["resolved"] else "no fix   "
            print(f"  [ALLOWED ] {c['action']:<55} {tag} shed={o['shed_pct']}%")
    if not r["chosen"]:
        print("\nNo safe, resolving action found. Escalate to a human.")
        return
    v = r["verification"]
    print(f"\nChosen: {r['chosen']['action']}")
    print("Observed health after action:\n  " + _health_line(v["observed_health"]))
    print(f"Prediction matched observation: {v['prediction_matches']} | Verified recovered: {v['recovered']}")
    rec = r["observed_outcome"]["recurrence_in_ticks"]
    if rec is not None:
        print(f"Warning: underlying fault persists, expect recurrence in ~{rec} ticks.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="aegismesh")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    run = sub.add_parser("run")
    run.add_argument("scenario", nargs="?")
    run.add_argument("--all", action="store_true")
    run.add_argument("--json", metavar="PATH")
    args = ap.parse_args(argv)

    if args.cmd == "list":
        for s in SCENARIOS:
            print(f"{s.id:<22} {s.title}")
        return 0

    targets = SCENARIOS if args.all else [BY_ID[args.scenario]] if args.scenario in BY_ID else None
    if targets is None:
        print("Specify a scenario id or --all. Try: list", file=sys.stderr)
        return 2
    records = [run_baseline(s) for s in targets]
    for r in records:
        print_record(r)
    if args.json:
        with open(args.json, "w") as f:
            json.dump(records, f, indent=2)
    if len(records) > 1:
        ok = sum(r["recovered"] for r in records)
        print(f"\nSummary: {ok}/{len(records)} incidents verified recovered; "
              f"{sum(r['blocked_count'] for r in records)} unsafe/invalid actions blocked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
