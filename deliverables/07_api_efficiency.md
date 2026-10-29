# How AegisMesh uses its API keys efficiently
Every number in `RESULTS.md` is measured by the evaluation harness from real runs and the cumulative ledger (`results/usage_ledger.json`).

## Tavily
| Technique | What it does |
|---|---|
| Adaptive research (`research=adaptive`) | Skips Tavily when the Investigator's log evidence is already decisive (confidence at least 0.85, two or more supporting log lines, runner-up at most 0.25). Spend goes to ambiguous incidents. |
| Query cap | At most 2 queries per incident (`AEGIS_MAX_QUERIES`). |
| Near-duplicate dropping | Queries with 70%+ word overlap are merged before any search is issued. |
| Basic depth, 3 results | `search_depth=basic` (1 credit) and `AEGIS_TAVILY_RESULTS=3`: fewer credits and fewer tokens for the models to read. |
| Disk cache | Every answer is stored by normalized query. Repeats, re-runs, evaluation and recordings cost 0 credits. |
| Credit budget | `TAVILY_CREDIT_BUDGET` caps cumulative live searches; beyond it the app serves cache only and says so. |
| Recorded replays | The hosted demo falls back to real recorded runs, so judges can always see research without spending credits. |
| Evidence discipline | Quotes are verified against retrieved text; unverifiable citations are ignored. No credit is spent on decoration. |
| Measured value | The evaluation compares no research, always-on research and adaptive research on plain and vendor-style logs, and reports correct root causes per search. |

## Nebius Token Factory
- Tiered models by role (fast / mid / heavy), so tokens go to the hardest reasoning only.
- At most about five model calls per incident; one planning retry only if no candidate is viable.
- Strict JSON, capped output tokens, one repair retry. No retry storms: transient errors back off three times then degrade to a deterministic planner.
- The baseline and replay modes make zero calls.
- Live AI runs in the hosted demo are capped (`AEGIS_LIVE_BUDGET`) with a per-visitor cooldown.
- Tokens and calls are recorded per run and in the ledger, and shown live on the dashboard.
