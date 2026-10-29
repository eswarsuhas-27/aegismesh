# Run on Windows (PowerShell), folder C:\UAI\Hackathon
1. Extract the zip into C:\UAI\Hackathon, then:  cd C:\UAI\Hackathon\aegismesh
2. Make sure .env is in this folder (File Explorer > View > Show > Hidden items). Put your REAL Nebius API key on the NEBIUS_API_KEY line.
3. $env:PYTHONUTF8 = "1"
4. python scripts\smoke_live.py          (use `py` instead of `python` if python is not found)
5. python scripts\finalize_submission.py --quick     (then without --quick if time allows)
6. python -m aegismesh.server            then open http://127.0.0.1:8000
Paste the output of steps 4 and 5 to Claude if anything fails. It never prints your keys.
