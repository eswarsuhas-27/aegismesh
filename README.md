# AegisMesh

**Autonomous AI incident-response digital twin** · Nebius x NVIDIA Global AI Hackathon 2026 · Track: Best Apps and Agents · **License: MIT**

AegisMesh investigates an outage like an on-call team, then goes further: it **tests every candidate fix in a deterministic
simulator and an independent safety policy before it touches anything**, executes only a verified-safe action, and proves
recovery from the simulator's state, not from the model's word.

`incident -> evidence -> hypotheses challenged -> fixes simulated -> safe action chosen -> executed -> verified`

## How we use NVIDIA Nemotron, Token Factory and Tavily
| | |
|---|---|
| **NVIDIA Nemotron** | Four agents (Investigator, Researcher, Skeptic, Planner) run on Nemotron models, right-sized per role: Nano for query writing and evidence extraction, Super for investigation and planning, Ultra for the Skeptic when the account offers it. Only NVIDIA models are ever selected; ids are discovered at runtime. |
| **Nebius Token Factory** | Every agent call is a runtime request to the Token Factory OpenAI-compatible API (stdlib client, retries, JSON-mode fallback, per-call model/latency/token accounting shown in the dashboard). Token Factory's model catalog is what makes per-role right-sizing cheap. No other Nebius service is required. |
| **Tavily** | Real research inside the investigation: queries written from the live hypotheses, results linked to claims, every quote verified against the retrieved text. Used frugally: adaptive gating, query cap and dedupe, basic depth, disk cache, credit budget (see `deliverables/07_api_efficiency.md`). |

## Features
- **Digital twin** with two domains: cloud services and a **synthetic hospital** (EHR, lab, imaging, pharmacy, HL7 interface engine, bedside monitors). Outcomes come from rules, never from a model.
- **Independent policy engine** that judges (world, action) on the simulated result. Hospital rules: life-critical systems are never restarted without a human; purging queued clinical messages is forbidden; clinical impact must not increase.
- **Counterfactual loop**: model prediction vs simulator result vs policy verdict for every candidate; re-plan with simulator feedback if nothing is viable.
- **Escalation, not override**: if no safe fix exists, apply the safest mitigation, request human approval, say so.
- **Honest research**: unverifiable citations are downgraded to "inconclusive"; if Tavily is unavailable the run says so; vendor-style scenarios (SQLSTATE, Redis, JVM, DICOM, OpenSSL errors, no config-change line) are where research can matter.
- **Evaluation harness** (baseline vs AI vs AI+research vs adaptive) on 20 reproducible incidents; **recorded replays** of real live runs; hosted-demo **spending caps**.
- **Dashboard**: graph, timeline, hypotheses, sources, candidate ledger, clinical impact, verification, live API usage, evaluation.

## Setup (Python 3.10+, no third-party packages)
```bash
cp .env.example .env              # Windows: copy .env.example .env, then add NEBIUS_API_KEY and TAVILY_API_KEY
python scripts/smoke_live.py      # checks both keys end to end (about a minute)
python -m aegismesh.server        # dashboard at http://127.0.0.1:8000
python scripts/finalize_submission.py [--quick]   # records live demos, runs the evaluation, writes deliverables/RESULTS.md
python -m tests.run_all           # 39 tests, no keys needed
```
Without keys the dashboard still runs the rule-based baseline; AI mode is disabled and research is reported unavailable (nothing is faked).

## Hosted demo
`Dockerfile` + `AEGIS_PUBLIC=1`: live AI runs are capped (`AEGIS_LIVE_BUDGET`, `AEGIS_COOLDOWN`, `TAVILY_CREDIT_BUDGET`); beyond the cap visitors get a clearly labelled replay of a real recorded run. Guide: `deliverables/04_demo_hosting_guide.md`.

## Scenarios (each also in a vendor-style-logs variant)
Cloud: database pool misconfig, cache memory cap, payments timeout, orders memory leak, traffic surge.
Hospital: expired HL7 certificate, disabled lab-results channel, imaging archive filling, EHR database connection limit, monitor gateway memory leak (escalation case).
Traps: restarting the DB does not fix a config fault; throttling "fixes" the surge but sheds most traffic; purging the HL7 queue destroys clinical messages; restarting the interface engine interrupts the whole hospital.

## Honest limits
- The twin is small by design; outcomes are simulated. Samples are small; read differences of a few points as noise.
- Red-team probes are a fixed list of prohibited actions, not a full adversarial audit.
- `tests/` use mock Token Factory/Tavily servers; live behaviour is checked by `smoke_live.py` and the finalizer.
- **Simulation only. Synthetic data, no patient identifiers. Not a medical device and not clinical advice.**

## Layout
`aegismesh/`: `twin` (engine + cloud profile), `hospital`, `scenarios`, `policy`, `planner` (baseline), `agents`, `orchestrator`,
`llm`, `tavily`, `usage` (API ledger), `recordings`, `server`, `eval`, `static/index.html`. Also `scripts/`, `tests/`, `deliverables/`, `results/`.
