"""Settings from environment / .env. Keys are never logged or written to results."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path | None = None) -> None:
    p = path or ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


@dataclass
class Settings:
    nebius_key: str
    nebius_base: str
    model_fast: str
    model_reason: str
    model_heavy: str
    tavily_key: str
    tavily_base: str
    tavily_cache: str
    tavily_mode: str   # live | replay | off
    tavily_budget: int  # max live Tavily searches ever (cumulative ledger); 0 = unlimited


def get_settings() -> Settings:
    load_dotenv()
    e = os.environ.get
    return Settings(
        nebius_key=e("NEBIUS_API_KEY", ""),
        nebius_base=e("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/"),
        model_fast=e("NEBIUS_MODEL_FAST", ""),
        model_reason=e("NEBIUS_MODEL_REASON", ""),
        model_heavy=e("NEBIUS_MODEL_HEAVY", ""),
        tavily_key=e("TAVILY_API_KEY", ""),
        tavily_base=e("TAVILY_BASE_URL", "https://api.tavily.com"),
        tavily_cache=e("TAVILY_CACHE", str(ROOT / "results" / "tavily_cache.json")),
        tavily_mode=e("TAVILY_MODE", "live"),
        tavily_budget=int(e("TAVILY_CREDIT_BUDGET", "150")),
    )
