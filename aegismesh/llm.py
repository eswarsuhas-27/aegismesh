"""Nebius Token Factory client (OpenAI-compatible REST, stdlib only).

Only NVIDIA open models are ever selected. Model ids are discovered from
GET /models at runtime because Token Factory retires and adds models.
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.request
from typing import Dict, List, Optional, Tuple

REASON_PREF = ["nvidia/nemotron-3-super-120b-a12b", "nvidia/nvidia-nemotron-3-nano-30b-a3b",
               "nvidia/nemotron-3_5-lightning", "nvidia/llama-3_1-nemotron-ultra-253b-v1"]
FAST_PREF = ["nvidia/nvidia-nemotron-3-nano-30b-a3b", "nvidia/nemotron-3_5-lightning",
             "nvidia/nemotron-3-super-120b-a12b", "nvidia/nemotron-nano-v2-12b"]
_EXCLUDE = ("vl", "omni", "embed", "reward", "guard", "safety", "cosmos", "parse")
FAST_ROLES = {"researcher_queries", "researcher_findings"}   # small, quick Nemotron (Nano)
HEAVY_ROLES = {"skeptic"}                                    # hardest reasoning: Nemotron Ultra when available
# Investigator and Planner use the mid tier (Super).


def pick_heavy(ids: List[str], mid: str) -> str:
    ultra = [i for i in ids if "nemotron" in i.lower() and "ultra" in i.lower() and not any(x in i.lower() for x in _EXCLUDE)]
    ultra.sort(key=lambda i: ("nemotron-3" not in i.lower(), i))
    return ultra[0] if ultra else mid


class LLMError(Exception):
    pass


def extract_json(text: str) -> dict:
    """Parse the first JSON object in model output (handles <think>, fences, chatter)."""
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    text = text.replace("```json", "```")
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{", text):
        try:
            obj, _ = dec.raw_decode(text[m.start():])
        except ValueError:
            continue
        if isinstance(obj, dict):
            return obj
    raise ValueError("no JSON object found in model output")


def pick_models(ids: List[str]) -> Tuple[str, str]:
    low = {i.lower(): i for i in ids}

    def first(pref):
        for p in pref:
            if p in low:
                return low[p]
        return None
    nem = [i for i in ids if "nemotron" in i.lower() and not any(x in i.lower() for x in _EXCLUDE)]
    reason = first(REASON_PREF) or (nem[0] if nem else None)
    fast = first(FAST_PREF) or reason
    if not reason:
        raise LLMError("No NVIDIA Nemotron text model is available on this Token Factory account")
    return fast, reason


class NebiusClient:
    def __init__(self, api_key: str, base_url: str, model_fast: str = "", model_reason: str = "",
                 timeout: float = 90, retries: int = 3, model_heavy: str = ""):
        if not api_key:
            raise LLMError("NEBIUS_API_KEY is not set")
        self.api_key, self.base = api_key, base_url.rstrip("/")
        self.timeout, self.retries = timeout, retries
        self.model_fast, self.model_reason, self.model_heavy = model_fast, model_reason, model_heavy
        self._json_mode = True
        self._lock = threading.Lock()
        self.available: List[str] = []

    # -- transport
    def _request(self, path: str, payload: Optional[dict] = None) -> dict:
        url = f"{self.base}/{path.lstrip('/')}"
        data = json.dumps(payload).encode() if payload is not None else None
        last: Exception = LLMError("request failed")
        for attempt in range(self.retries):
            req = urllib.request.Request(url, data=data, method="POST" if data else "GET", headers={
                "Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                body = e.read().decode(errors="replace")[:500]
                if e.code in (429, 500, 502, 503, 504) and attempt < self.retries - 1:
                    time.sleep(1.5 * (attempt + 1)); last = LLMError(f"HTTP {e.code}: {body}"); continue
                raise LLMError(f"HTTP {e.code} from {path}: {body}")
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last = LLMError(f"network error: {e}")
                if attempt < self.retries - 1:
                    time.sleep(1.5 * (attempt + 1)); continue
        raise last

    def list_models(self) -> List[str]:
        return [m["id"] for m in self._request("models").get("data", []) if "id" in m]

    def resolve_models(self) -> Tuple[str, str]:
        if self.model_fast and self.model_reason:
            self.model_heavy = self.model_heavy or self.model_reason
            return self.model_fast, self.model_reason
        try:
            self.available = self.list_models()
            fast, reason = pick_models(self.available)
        except LLMError:
            if not (self.model_fast or self.model_reason):
                fast, reason = FAST_PREF[0], REASON_PREF[0]  # catalog listing unavailable: try known ids
            else:
                raise
        self.model_fast = self.model_fast or fast
        self.model_reason = self.model_reason or reason
        self.model_heavy = self.model_heavy or pick_heavy(self.available, self.model_reason)
        return self.model_fast, self.model_reason

    # -- chat
    def chat(self, model: str, system: str, user: str, max_tokens: int, temperature: float) -> Tuple[str, dict]:
        payload = {"model": model, "temperature": temperature, "max_tokens": max_tokens,
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if self._json_mode:
            payload["response_format"] = {"type": "json_object"}
        t0 = time.time()
        try:
            resp = self._request("chat/completions", payload)
        except LLMError as e:
            if self._json_mode and "response_format" in str(e):
                self._json_mode = False
                payload.pop("response_format", None)
                resp = self._request("chat/completions", payload)
            else:
                raise
        msg = (resp.get("choices") or [{}])[0].get("message", {})
        text = msg.get("content") or ""
        if not text.strip() and self._json_mode:
            self._json_mode = False
            payload.pop("response_format", None)
            try:
                resp = self._request("chat/completions", payload)
                msg = (resp.get("choices") or [{}])[0].get("message", {})
                text = msg.get("content") or ""
            except LLMError:
                pass
        if not text.strip():
            r_text = msg.get("reasoning") or msg.get("reasoning_content") or ""
            if "{" in r_text:
                text = r_text
            else:
                raise LLMError("empty completion")
        u = resp.get("usage") or {}
        return text, {"model": resp.get("model", model), "latency_s": round(time.time() - t0, 2),
                      "prompt_tokens": u.get("prompt_tokens", 0), "completion_tokens": u.get("completion_tokens", 0)}

    def chat_json(self, role: str, system: str, user: str, max_tokens: int = 1800) -> Tuple[dict, dict]:
        fast, reason = self.resolve_models()
        model = fast if role in FAST_ROLES else (self.model_heavy or reason) if role in HEAVY_ROLES else reason
        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        latency, err = 0.0, ""
        for attempt in range(2):
            cur_model = reason if (attempt > 0 and model == fast) else model
            cur_tokens = max(max_tokens, 2500) if attempt > 0 else max_tokens
            u = user if not err else f"{user}\n\nYour previous reply was invalid ({err}). Reply with ONE valid JSON object only."
            try:
                text, meta = self.chat(cur_model, system, u, cur_tokens, 0.2)
                latency += meta["latency_s"]
                for k in usage:
                    usage[k] += meta[k]
                data = extract_json(text)
                return data, {"role": role, "model": meta["model"], "latency_s": round(latency, 2), "attempts": attempt + 1, **usage}
            except (ValueError, LLMError) as e:
                err = str(e)
                if attempt == 1:
                    raise LLMError(f"{role}: {e}")
        raise LLMError(f"{role}: model did not return valid JSON")
