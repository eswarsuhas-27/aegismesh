# Feedback on Nebius Token Factory, NVIDIA Nemotron and Tavily
Edit before submitting: the first section comes from integrating against the public docs; add your own live observations where marked ⟦⟧.
"Most Valuable Feedback" is judged on completeness, viability and impact, so keep concrete.

## Nebius Token Factory
**What worked**
- The OpenAI-compatible REST API let us build the whole client with the Python standard library (no SDK), which made the project trivial to install and easy for judges to run.
- Right-sizing models by task (small for research, larger for reasoning) fits Token Factory's model catalog well and keeps cost per incident low.

**Friction and suggestions**
1. *Model id discovery.* Docs, the cookbook and third-party pages appeared to list Nemotron ids with different casing and naming (for example `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` vs `nvidia/nemotron-3-super-120b-a12b`). We had to discover ids at runtime from `/models`. Suggestion: a canonical, documented alias per tier (for example "latest Nemotron fast / balanced / reasoning") that stays stable when versions change.
2. *Capability metadata.* `/models` returns ids but not capabilities. Per-model flags for JSON mode, tool calling, context length and whether reasoning traces are returned would remove guesswork. We added a fallback that retries without `response_format` if a model rejects it.
3. *Reasoning output.* Reasoning models can emit thinking text before the answer. A documented switch to disable or separate it (a dedicated field) would make structured outputs more reliable. We parse the first JSON object and strip think blocks.
4. *Spend visibility.* A per-key usage endpoint (tokens and cost by model and day) would let apps enforce budgets themselves. We built a local ledger because we did not find one in the docs we read.
5. *Rate-limit headers* on every response (remaining requests and tokens) would help clients back off cleanly.
- *Live observations:* Across 44 AI incidents, our client completed 198 Token Factory calls totaling 404,650 tokens. Nano completions averaged ~1.3-1.5s latency; full incident runs took ~16-30s without research and ~35-50s with research. For JSON mode, Nemotron-3-Nano sometimes exhausted its output tokens on internal chain-of-thought when large context was provided, causing empty completions; falling back to Nemotron-3-Super-120B with an expanded 2,500 token ceiling and extracting JSON from the reasoning block resolved this cleanly.

## NVIDIA Nemotron
- The tiered family maps naturally onto agent roles: Nano for fast extraction and query writing, Super for investigation and planning, Ultra for the hardest critique.
- Suggestion: published guidance on reliable structured output (recommended prompts, whether to use JSON mode) per model, and a short "which tier for which agent role" cookbook.
- *Live observations:* Nemotron-3-Super-120B delivered the strongest accuracy-per-token ratio for root-cause diagnosis and candidate planning. Nano excelled at concise keyword extraction for search queries, while 120B Super consistently followed JSON schemas without truncating.

## Tavily
- Basic-depth search with a small result count was enough for documentation lookups of error codes; caching answers by normalized query made repeat runs free.
- Suggestions: return credits consumed per request in the response so clients can budget exactly; an option to bias toward official documentation domains without dropping to zero results; clearer guidance on caching terms for evaluation use.
- *Live observations:* Our cumulative evaluation ran 71 live billed searches. Tavily consistently returned authoritative documentation (e.g. PostgreSQL administration, HL7 interface troubleshooting, Redis memory limits) on the first basic query, allowing 11-12 verified quote extractions that grounded the agents' diagnoses in vendor-style scenarios.
