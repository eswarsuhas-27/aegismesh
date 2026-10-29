"""Run every test without pytest:  python -m tests.run_all"""
import importlib
import os
import sys
import tempfile

os.environ["AEGIS_LEDGER"] = tempfile.mktemp(suffix=".json")  # tests never touch the real usage ledger
import time
import traceback

failed = 0
total = 0
for modname in ("tests.test_twin", "tests.test_agents_and_clients", "tests.test_hospital", "tests.test_efficiency", "tests.test_replay_public"):
    mod = importlib.import_module(modname)
    for name in sorted(n for n in dir(mod) if n.startswith("test_")):
        total += 1
        t0 = time.time()
        try:
            getattr(mod, name)()
            print(f"ok    {name} ({time.time() - t0:.1f}s)")
        except Exception:
            failed += 1
            print(f"FAIL  {name}")
            traceback.print_exc()
print(f"\n{total - failed}/{total} passed")
sys.exit(1 if failed else 0)
