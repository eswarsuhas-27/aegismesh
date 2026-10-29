# 3-minute demo video: script and shot list
Hard limit: under 3:00 (judges need not watch past it). Public on YouTube. No copyrighted music. Record at 1080p, browser zoom 110%.
Before recording: `python scripts/finalize_submission.py` done, dashboard open, one practice run so the first load is warm.
Use LIVE mode for the video (it must show the project really calling Token Factory). Keep the replay for the hosted demo.

| Time | On screen | Say (about) |
|---|---|---|
| 0:00-0:15 | Dashboard header, Hospital IT mode note | "When production breaks, the loud error is rarely the cause, and an AI that suggests an unvalidated fix can make it worse. In a hospital, that can hurt patients. AegisMesh tests every fix before it touches anything." |
| 0:15-0:40 | Cloud services, scenario "Database pool misconfiguration (vendor-style logs)", Tavily research = always. Press Inject. Point at gateway, orders, payments down, `db` ringed | "The logs only say SQLSTATE 53300. Four Nemotron agents on Nebius Token Factory investigate: gateway, orders and payments are victims, the database is the origin." |
| 0:40-1:10 | Hypotheses panel, click an evidence chip; Research panel with sources and a green verified quote; Token Factory calls panel showing model names per role | "Tavily looks up what the error means. A citation only counts if its quote appears in the page. Models are right-sized: small Nemotron for research, larger for the Skeptic and Planner." |
| 1:10-1:40 | Candidate table: model expected vs simulator result vs policy; point at a blocked action | "Every candidate runs in a deterministic twin. The model said this would work; the simulator and an independent policy decide. This one is blocked." |
| 1:40-2:00 | Execution and verification, banner "Recovered. Verified from simulator state" | "Recovery is checked against the simulator's state, not the model's word." |
| 2:00-2:35 | Switch to Hospital IT, "Bedside monitor gateway leak". Show approval request, mitigation, clinical impact dropping, banner "Mitigated, not fixed. Human approval required" | "The only technical fix restarts a life-critical monitor. The policy refuses, the agent applies the safe mitigation, asks a human, and does not override. Patient safety outranks speed." |
| 2:35-2:55 | Evaluation panel and the "API usage" line; mention adaptive research | "Recorded results compare baseline, AI, and AI with Tavily. Adaptive mode spends no search when the logs are decisive, and repeats come from cache." |
| 2:55-3:00 | Repo URL and demo URL on screen | "AegisMesh: open source, MIT, link below." |

Tips: rehearse once and time it. If a live run is slow, trim narration, not the run. Do not show `.env` or API keys on screen.
YouTube: Visibility = Public. Paste the link in the Devpost form and open it in a private window to confirm it plays.
