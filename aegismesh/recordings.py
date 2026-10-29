"""Recorded real runs. A recording is the exact event stream of a live run (with your keys),
saved to results/recordings/ so the demo can be replayed later with zero API calls.
Replays are always labelled as replays in the dashboard."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import List, Optional

from .config import ROOT

DIR = ROOT / "results" / "recordings"
PREFERENCE = ["ai_always", "ai_adaptive", "ai_off", "baseline"]


def condition(metrics: dict, mode: str) -> str:
    return "baseline" if mode == "baseline" else f"ai_{metrics['research_mode'] if metrics['research_mode'] != 'off' else 'off'}"


def save(result: dict) -> Path:
    cond = condition(result["metrics"], result["mode"])
    DIR.mkdir(parents=True, exist_ok=True)
    p = DIR / f"{result['scenario']}__{cond}.json"
    p.write_text(json.dumps({
        "scenario": result["scenario"], "condition": cond, "recorded_at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "models": result["metrics"]["models"], "metrics": result["metrics"], "report": result["report"], "events": result["events"],
    }, indent=1), encoding="utf-8")
    return p


def index() -> List[dict]:
    out = []
    for p in sorted(DIR.glob("*.json")) if DIR.exists() else []:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            out.append({k: d[k] for k in ("scenario", "condition", "recorded_at", "models")})
        except (ValueError, KeyError):
            continue
    return out


def load(scenario: str) -> Optional[dict]:
    for cond in PREFERENCE:
        p = DIR / f"{scenario}__{cond}.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    return None
