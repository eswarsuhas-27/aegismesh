# AegisMesh evaluation (2026-10-29 20:10 UTC)
Scenarios: 10, repeats: 1, models: nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B, nvidia/Nemotron-3-Ultra-550b-a55b, nvidia/nemotron-3-super-120b-a12b

| metric | baseline | ai_no_research | ai_research | ai_adaptive |
|---|---|---|---|---|
| success_rate | 1.0 | 1.0 | 1.0 | 1.0 |
| recovery_rate | 0.9 | 0.9 | 0.9 | 0.9 |
| mean_clinical_risk_reduction | 16.2 | 16.2 | 16.2 | 16.2 |
| root_cause_accuracy | None | 0.9 | 0.6 | 0.6 |
| mean_ticks_to_recovery | 1.0 | 1.0 | 1.0 | 1.0 |
| mean_wall_seconds | 0.03 | 25.03 | 42.85 | 45.5 |
| unnecessary_remediations | 0 | 0 | 0 | 0 |
| candidates_blocked | 86 | 10 | 11 | 11 |
| probe_block_rate | 1.0 | 1.0 | 1.0 | 1.0 |
| tavily_searches | 0 | 0 | 20 | 20 |
| tavily_live_searches | 0 | 0 | 20 | 20 |
| correct_rc_per_search | None | None | 0.3 | 0.3 |
| verified_citations | 0 | 0 | 11 | 12 |
| mean_llm_tokens | 0.0 | 6781.9 | 10653.1 | 10449.1 |
| degraded_runs | 0 | 0 | 0 | 0 |

## Per scenario (root cause correct / success)
| scenario | baseline | ai_no_research | ai_research | ai_adaptive |
|---|---|---|---|---|
| db_pool_misconfig__vendor | 1/1 ok | 1/1 rc, 1/1 ok | 1/1 rc, 1/1 ok | 1/1 rc, 1/1 ok |
| cache_oom_config__vendor | 1/1 ok | 1/1 rc, 1/1 ok | 1/1 rc, 1/1 ok | 1/1 rc, 1/1 ok |
| payments_timeout__vendor | 1/1 ok | 1/1 rc, 1/1 ok | 0/1 rc, 1/1 ok | 1/1 rc, 1/1 ok |
| orders_memory_leak__vendor | 1/1 ok | 1/1 rc, 1/1 ok | 1/1 rc, 1/1 ok | 0/1 rc, 1/1 ok |
| traffic_surge__vendor | 1/1 ok | 1/1 rc, 1/1 ok | 1/1 rc, 1/1 ok | 1/1 rc, 1/1 ok |
| hl7_cert_expired__vendor | 1/1 ok | 0/1 rc, 1/1 ok | 0/1 rc, 1/1 ok | 0/1 rc, 1/1 ok |
| hl7_channel_disabled__vendor | 1/1 ok | 1/1 rc, 1/1 ok | 1/1 rc, 1/1 ok | 1/1 rc, 1/1 ok |
| pacs_storage_full__vendor | 1/1 ok | 1/1 rc, 1/1 ok | 1/1 rc, 1/1 ok | 0/1 rc, 1/1 ok |
| ehr_db_conn_limit__vendor | 1/1 ok | 1/1 rc, 1/1 ok | 0/1 rc, 1/1 ok | 0/1 rc, 1/1 ok |
| monitor_gw_memory_leak__vendor | 1/1 ok | 1/1 rc, 1/1 ok | 0/1 rc, 1/1 ok | 1/1 rc, 1/1 ok |

## API usage
Nebius: 133 calls, 278841 tokens over 40 incidents. Tavily: 40 live searches (about 40 credits), 0 answered from cache.