"""Headless check that the dashboard renders every scenario's real event stream (needs node):  python scripts/render_check.py"""
import os, tempfile
os.environ.setdefault("AEGIS_LEDGER", tempfile.mktemp(suffix=".json"))  # never pollute the real usage ledger
import json, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from aegismesh.orchestrator import Run
from aegismesh.scenarios import SCENARIOS
from tests.fakes import OracleLLM

runs = []
for s in SCENARIOS:
    runs.append(Run(s.id, "baseline", False).execute()["events"])
    runs.append(Run(s.id, "ai", False, llm=OracleLLM(s.id)).execute()["events"])
f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump(runs, f); f.close()
sys.exit(subprocess.call(["node", str(Path(__file__).with_name("render_check.js")), f.name]))
