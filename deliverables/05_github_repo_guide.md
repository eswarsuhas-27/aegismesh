# Public GitHub repository
Requirements from the rules: public, an open-source license detectable in the About section, a README with setup and how Nemotron and Token Factory are used.
The README and `LICENSE` (MIT) are already in the project.

1. Edit `LICENSE`: replace "AegisMesh authors" with your name or team name.
2. In the project folder (PowerShell):
```
git init
git add .
git status        # CONFIRM .env is NOT listed. If it is, stop: run  git rm --cached .env
git commit -m "AegisMesh: autonomous incident-response digital twin"
git branch -M main
git remote add origin https://github.com/⟦your-username⟧/aegismesh.git
git push -u origin main
```
3. On github.com create the repo first (Public, no README/license added there). After pushing, open the repo page and check that the About box on the right shows "MIT license". Add topics: `nvidia-nemotron`, `nebius`, `token-factory`, `tavily`, `ai-agents`, `incident-response`.
4. Run `python scripts/finalize_submission.py` BEFORE committing so `results/recordings/`, `results/tavily_cache.json`, `results/eval_latest.*` and `deliverables/RESULTS.md` are included.
5. `.gitignore` already excludes `.env`. If a key ever lands in a commit, delete the key in the provider console and create a new one, then rewrite history.
