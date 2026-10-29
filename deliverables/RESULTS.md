# Measured results (2026-10-29 20:10 UTC)

Models used: nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B, nvidia/Nemotron-3-Ultra-550b-a55b, nvidia/nemotron-3-super-120b-a12b  
Scenarios: 10, repeats: 1. Numbers below are recorded runs, not estimates.

## Outcome by condition
| condition | success | root cause correct | recovered | blocked unsafe candidates | red-team blocked |
|---|---|---|---|---|---|
| baseline | 100% | n/a | 90% | 86/146 | 100% |
| ai_no_research | 100% | 90% | 90% | 10/37 | 100% |
| ai_research | 100% | 60% | 90% | 11/40 | 100% |
| ai_adaptive | 100% | 60% | 90% | 11/37 | 100% |

## Tavily: effect and cost, by log style
Plain = explicit config-change lines in the logs. Vendor-style = real-looking vendor errors (SQLSTATE, Redis, JVM, DICOM, OpenSSL) with no config-change line, so the cause has to be looked up.

| condition | logs | incidents | root cause correct | Tavily searches issued | billed (live) | correct root causes per search |
|---|---|---|---|---|---|---|
| baseline | vendor-style | 10 | n/a | 0 | 0 | n/a |
| ai_no_research | vendor-style | 10 | 90% | 0 | 0 | n/a |
| ai_research | vendor-style | 10 | 60% | 20 | 20 | 0.3 |
| ai_adaptive | vendor-style | 10 | 60% | 20 | 20 | 0.3 |

## Reading the Tavily comparison (generated from the numbers above)
- vendor-style logs: root-cause accuracy 90% without research vs 60% with research (n=10), a difference of -30 points.
- Adaptive research issued 20 searches versus 20 for always-on research, skipping research in 0 of 10 incidents.
- Small samples: treat differences of a few points as noise. The sample is small and the scenarios are simulated.

## Real API spend (cumulative ledger on this machine)
- Nebius Token Factory: 198 calls, 404650 tokens, 44 AI incidents
- Tavily: 71 live (billed) searches; cache hits are free and repeated runs reuse them

## Recorded live runs available for free replay
- db_pool_misconfig__vendor (ai_always), 2026-10-29 19:49 UTC
- hl7_channel_disabled (ai_adaptive), 2026-10-29 19:50 UTC
- monitor_gw_memory_leak (ai_adaptive), 2026-10-29 19:51 UTC
