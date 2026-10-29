"""Cumulative API usage ledger (results/usage_ledger.json, or $AEGIS_LEDGER).

Counts billable Tavily searches and Nebius calls/tokens across processes, so budgets and the
efficiency report reflect real spend, not a single run.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from .config import ROOT

_lock = threading.Lock()


def _path() -> Path:
    return Path(os.environ.get("AEGIS_LEDGER", str(ROOT / "results" / "usage_ledger.json")))


def snapshot() -> dict:
    p = _path()
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except ValueError:
        return {}


def record(**counts) -> None:
    with _lock:
        d = snapshot()
        for k, v in counts.items():
            d[k] = d.get(k, 0) + v
        d["updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        p = _path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(d, indent=1), encoding="utf-8")
