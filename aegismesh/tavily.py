"""Tavily search client with record/replay cache (stdlib only).

live   : call the Tavily API (needs TAVILY_API_KEY); every response is cached to disk
replay : answer only from the cache file (deterministic demos, offline evals)
off    : unavailable. The investigation reports it honestly; nothing is invented.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import List, Optional

from . import usage


class TavilyUnavailable(Exception):
    pass


def _norm(q: str) -> str:
    return re.sub(r"\s+", " ", q.strip().lower())


class Tavily:
    def __init__(self, api_key: str = "", base_url: str = "https://api.tavily.com", cache_path: str = "",
                 mode: str = "live", timeout: float = 30, credit_budget: int = 0):
        self.key, self.base, self.timeout = api_key, base_url.rstrip("/"), timeout
        self.cache_path = Path(cache_path) if cache_path else None
        self.mode = mode
        self.credit_budget = credit_budget
        self.max_results = int(os.environ.get("AEGIS_TAVILY_RESULTS", "3"))   # fewer results: fewer tokens for the models to read
        self.live_calls = 0   # billable searches this process
        self.cache_hits = 0   # searches answered free from the cache
        self.cache = {}
        if self.cache_path and self.cache_path.exists():
            try:
                self.cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
            except ValueError:
                self.cache = {}
        if self.mode == "live" and not self.key:
            self.mode = "replay" if self.cache else "off"

    @property
    def available(self) -> bool:
        return self.mode in ("live", "replay")

    def status(self) -> str:
        return {"live": f"live (Tavily API, search_depth=basic, {self.max_results} results, budget {self.credit_budget or 'unlimited'})", "replay": f"replay ({len(self.cache)} cached queries)",
                "off": "unavailable: no TAVILY_API_KEY and no cache"}[self.mode]

    def search(self, query: str, max_results: int = 0) -> dict:
        """Returns {"results":[{title,url,content,score}], "from_cache":bool, "latency_s":float}."""
        key = hashlib.sha1(_norm(query).encode()).hexdigest()
        if key in self.cache:
            self.cache_hits += 1
            return {"results": self.cache[key]["results"], "from_cache": True, "latency_s": 0.0}
        if self.mode != "live":
            raise TavilyUnavailable(f"no cached result for this query and Tavily mode is '{self.mode}'")
        if self.credit_budget and usage.snapshot().get("tavily_live_searches", 0) >= self.credit_budget:
            raise TavilyUnavailable(f"Tavily credit budget of {self.credit_budget} live searches is used up; serving cache only")
        max_results = max_results or self.max_results
        body = json.dumps({"query": query, "search_depth": "basic", "max_results": max_results,
                           "include_answer": False}).encode()
        req = urllib.request.Request(f"{self.base}/search", data=body, method="POST", headers={
            "Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
        t0 = time.time()
        self.live_calls += 1
        usage.record(tavily_live_searches=1)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            raise TavilyUnavailable(f"Tavily HTTP {e.code}: {e.read().decode(errors='replace')[:200]}")
        except (urllib.error.URLError, TimeoutError) as e:
            raise TavilyUnavailable(f"Tavily network error: {e}")
        results = [{"title": x.get("title", ""), "url": x.get("url", ""), "content": x.get("content", ""),
                    "score": x.get("score")} for x in data.get("results", [])][:max_results]
        self.cache[key] = {"query": query, "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                           "results": results}
        if self.cache_path:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(self.cache, indent=1), encoding="utf-8")
        return {"results": results, "from_cache": False, "latency_s": round(time.time() - t0, 2)}
