# Hosting the demo URL
Rules: the demo must be reachable free of charge, without restriction, until the judging period ends (Dec 15, 2026).
That is why the app has a **public mode**: capped live AI runs plus free replay of recorded real runs.

## Option A (recommended): Render, free web service from your GitHub repo
1. Push the repo (see `05_github_repo_guide.md`). Commit `results/recordings/` and `results/tavily_cache.json` after running the finalizer.
2. render.com -> New -> Web Service -> connect the repo -> Runtime: Docker (it uses the included Dockerfile).
3. Environment variables (in Render's dashboard, **never in the repo**):
   - `NEBIUS_API_KEY` = your real Token Factory key
   - `TAVILY_API_KEY` = your Tavily key
   - `AEGIS_PUBLIC` = `1` (already set by the Dockerfile)
   - `AEGIS_LIVE_BUDGET` = `12` (live AI incidents the demo may run per server start)
   - `AEGIS_COOLDOWN` = `30` (seconds between live runs per visitor)
   - `TAVILY_CREDIT_BUDGET` = `60` (live Tavily searches before it serves cache only)
4. Deploy, open the URL, run one scenario live and one replay.
5. Free instances sleep when idle and counters reset on restart. Open the URL once a day during judging, and watch your Nebius and Tavily usage dashboards for the real spend.

## Option B: Hugging Face Spaces (Docker SDK)
Create a Docker Space from the same repo and add the same variables as Space secrets. The app reads `$PORT`.

## Option C: Nebius Serverless Endpoints
The track page encourages (but does not require) deploying on Nebius Serverless. If you do, follow Nebius's current docs and use the same Dockerfile and variables.

## Do not
Do not host from your laptop with a tunnel: it must stay up for six weeks. Do not put keys in the image, the repo, or screenshots.

## Why the hosted demo survives judging
Live runs are capped, repeats of Tavily queries are cache hits, and after the cap visitors get a clearly labelled replay of a real recorded run. The "Best Use of Tavily" requirement (a functional runtime Tavily call) is met by live runs within the budget.
