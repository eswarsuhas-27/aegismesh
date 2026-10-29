# Commands to run and test everything (Windows PowerShell)

## 0. Unzip (zip saved in C:\UAI\Hackathon)
cd C:\UAI\Hackathon
Expand-Archive -Path .\aegismesh-final.zip -DestinationPath . -Force
cd .\aegismesh
dir -Force                                  # you should see .env in the list
$env:PYTHONUTF8 = "1"
python --version                            # needs 3.10 or newer (if "python" is not found, use "py" everywhere below)

## 1. Test everything that needs no keys (39 tests, about 15 seconds)
python -m tests.run_all

## 2. Test your real keys against Nebius Token Factory and Tavily
python scripts\smoke_live.py
# If it says HTTP 401 or 403 from Token Factory, the Nebius value is not a real API key.
# Create one in the Token Factory console (API keys), replace the NEBIUS_API_KEY line in .env, run again.

## 3. Run all simulations with your keys, record the demos, write deliverables\RESULTS.md
python scripts\finalize_submission.py --quick       # fewer API calls, 10 to 30 minutes
python scripts\finalize_submission.py               # full run, run this if time allows

## 4. Start the dashboard and try it yourself
python -m aegismesh.server
# open http://127.0.0.1:8000   (stop with Ctrl+C)
# Try: Mode "AI investigation", Tavily research "always", scenario "Database pool misconfiguration (vendor-style logs)"
# Then: Environment "Hospital IT" > "Bedside monitor gateway memory leak"
# Then: Mode "Replay a recorded live run" (zero API calls)

## Optional extras
python -m aegismesh.eval --conditions baseline      # evaluation with no keys
python -m aegismesh.eval --scenarios vendor         # AI conditions on vendor-style logs only
python scripts\render_check.py                      # needs Node.js: checks the dashboard renders every scenario
type results\usage_ledger.json                      # your real Nebius and Tavily usage so far
