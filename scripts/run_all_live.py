"""One command to test everything with your real keys, spending as little as possible.

    python scripts/run_all_live.py            # smoke test, then 1 repeat of every condition
    python scripts/run_all_live.py --repeats 2

Efficiency: Tavily answers are cached to results/tavily_cache.json, so re-runs cost 0 Tavily credits
and are reproducible; research is capped at 2 queries per incident; the baseline condition uses no keys.
"""
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
rep = sys.argv[sys.argv.index("--repeats") + 1] if "--repeats" in sys.argv else "1"
steps = [[sys.executable, "scripts/smoke_live.py"], [sys.executable, "-m", "aegismesh.eval", "--repeats", rep],
         [sys.executable, "-m", "tests.run_all"]]
for cmd in steps:
    print("\n$", " ".join(cmd[1:]))
    if subprocess.call(cmd, cwd=root) != 0:
        sys.exit(f"stopped: {' '.join(cmd[1:])} failed. Paste the output above (it never contains your keys).")
print("\nAll done. Open results/eval_latest.md for the recorded numbers and API usage.")
