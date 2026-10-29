"""AegisMesh agents: Investigator, Researcher, Skeptic, Planner.

Each agent is a prompt plus a strict validator. Model output is never trusted:
unknown log ids are dropped, citations must quote their source verbatim, and
actions are parsed into the twin's action grammar before the policy engine sees them.
"""
from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Tuple

from . import twin
from .twin import Action, World

KINDS = ["bad_config", "memory_leak", "overload", "expired_certificate", "dependency_failure", "other"]
COMMON = ("You are one component of AegisMesh, an incident-response system working on a SIMULATED "
          "environment (synthetic data, nothing real). Reply with ONE JSON object only: no prose, no markdown.")


MAX_QUERIES = int(os.environ.get("AEGIS_MAX_QUERIES", "2"))   # each live Tavily query costs one credit


class AgentError(Exception):
    pass


# ------------------------------------------------------------ observation ---
def build_observation(w: World) -> dict:
    seen: Dict[tuple, dict] = {}
    for e in w.logs:
        k = (e.service, e.level, e.message)
        if k in seen:
            seen[k]["t_last"], seen[k]["count"] = e.t, seen[k]["count"] + 1
        else:
            seen[k] = {"t": e.t, "t_last": e.t, "count": 1, "service": e.service, "level": e.level, "message": e.message}
    logs = [dict(id=f"L{i + 1}", **v) for i, v in enumerate(seen.values())]
    P = w.profile
    h = twin.health(w)
    return {
        "domain": P.name, "title": P.title, "context": P.context, "layout": P.layout,
        "impact": P.impact(w, h),
        "health": h,
        "logs": logs,
        "config": {n: dict(s.config, replicas=s.replicas) for n, s in w.services.items()},
        "metrics": P.metrics(w),
        "topology": {n: [(d, "hard" if hd else "soft") for d, hd in deps] for n, deps in P.topology.items()},
        "tick": w.t,
    }


def render_observation(o: dict) -> str:
    out = [f"ENVIRONMENT: {o['context']}", "SERVICE HEALTH: " + ", ".join(f"{k}={v}" for k, v in o["health"].items()),
           "DEPENDENCIES (service -> dependency): " + "; ".join(
               f"{s}->{d}({k})" for s, deps in o["topology"].items() for d, k in deps),
           "METRICS: " + ", ".join(f"{k}={v}" for k, v in o["metrics"].items()),
           f"CLINICAL IMPACT SCORE (0 = none): {o['impact']['score']}" + ("; " + "; ".join(o["impact"]["items"]) if o["impact"]["items"] else "")
           if o["domain"] == "hospital" else "",
           "CURRENT CONFIG: " + "; ".join(f"{s}: " + ", ".join(f"{k}={v}" for k, v in c.items()) for s, c in o["config"].items()),
           "LOGS (id, first-last tick, count, service, level, message):"]
    for l in o["logs"]:
        span = f"t={l['t']}" if l["t"] == l["t_last"] else f"t={l['t']}-{l['t_last']}"
        out.append(f"{l['id']} {span} x{l['count']} {l['service']} {l['level']} {l['message']}")
    return "\n".join(x for x in out if x)


def _clamp(x, default=0.5) -> float:
    try:
        return max(0.0, min(1.0, float(x)))
    except (TypeError, ValueError):
        return default


def _ids(items, valid) -> List[str]:
    return [i for i in (items or []) if isinstance(i, str) and i in valid]


# ------------------------------------------------------------ investigator ---
SYS_INV = COMMON + """
Role: Investigator. Build a short timeline from the logs and propose 2-4 competing root-cause hypotheses.
A root cause is where the failure ORIGINATED, not the loudest symptom: a service that only reports
'upstream X failing' is a victim. Cite only log ids that appear in the input.
Schema: {"timeline":[{"log":"L1","summary":"..."}],
"hypotheses":[{"id":"H1","service":"<service name>","kind":"bad_config|memory_leak|overload|dependency_failure|other",
"statement":"...","confidence":0.0,"evidence":["L3"],"unknowns":["..."]}]}"""


def investigate(llm, obs: dict) -> dict:
    raw = llm.chat_json("investigator", SYS_INV, render_observation(obs))
    log_ids = {l["id"] for l in obs["logs"]}
    hyps, warnings, used = [], [], set()
    for i, h in enumerate(raw.get("hypotheses") or []):
        if not isinstance(h, dict) or h.get("service") not in obs["health"]:
            warnings.append(f"dropped hypothesis with unknown service: {h.get('service') if isinstance(h, dict) else h}")
            continue
        hid = h.get("id") if isinstance(h.get("id"), str) and h.get("id") not in used else f"H{i + 1}"
        used.add(hid)
        ev = _ids(h.get("evidence"), log_ids)
        if len(ev) < len(h.get("evidence") or []):
            warnings.append(f"{hid}: dropped citations to non-existent log ids")
        hyps.append({"id": hid, "service": h["service"], "kind": h.get("kind") if h.get("kind") in KINDS else "other",
                     "statement": str(h.get("statement", ""))[:400], "confidence": _clamp(h.get("confidence")),
                     "evidence": ev, "unknowns": [str(u)[:200] for u in (h.get("unknowns") or [])][:4]})
    if not hyps:
        raise AgentError("Investigator produced no valid hypotheses")
    timeline = [{"log": t["log"], "summary": str(t.get("summary", ""))[:200]} for t in (raw.get("timeline") or [])
                if isinstance(t, dict) and t.get("log") in log_ids]
    return {"hypotheses": hyps, "timeline": timeline, "warnings": warnings}


# -------------------------------------------------------------- researcher ---
SYS_RQ = COMMON + """
Role: Researcher. Write up to 2 web search queries that would retrieve authoritative documentation or
troubleshooting guidance to CONFIRM or REFUTE the hypotheses. Use generic technical vocabulary
(software, error text, symptom), not our service names. Schema:
{"queries":[{"query":"...","hypothesis":"H1","purpose":"confirm|refute"}]}"""

SYS_RF = COMMON + """
Role: Researcher. You receive retrieved sources (id, title, url, content). For each hypothesis the sources
bear on, say whether they support it, challenge it, or are inconclusive. EVERY finding needs "source" (a
source id from the input) and "quote": an exact verbatim excerpt (max 25 words) copied from that source's
content. If sources do not help, return no finding for that hypothesis. Outside knowledge is not a citation.
Schema: {"findings":[{"hypothesis":"H1","stance":"supports|challenges|inconclusive","claim":"...","source":"S1","quote":"..."}]}"""


def _squash(s: str) -> str:
    return re.sub(r"[\s\"'`“”‘’]+", " ", s.lower()).strip()


def research(llm, tavily, hyps: List[dict], emit) -> dict:
    """Returns {status, queries, sources, findings}. Never fabricates sources."""
    if tavily is None or not tavily.available:
        reason = tavily.status() if tavily else "no Tavily client configured"
        return {"status": "unavailable", "reason": reason, "queries": [], "sources": [], "findings": []}
    summary = "\n".join(f"{h['id']} [{h['service']}/{h['kind']}] {h['statement']}" for h in hyps)
    qs = llm.chat_json("researcher_queries", SYS_RQ, summary).get("queries") or []
    queries, toks = [], []
    for q in qs:   # drop empty and near-duplicate queries: every live query costs a Tavily credit
        if not (isinstance(q, dict) and isinstance(q.get("query"), str) and q["query"].strip()):
            continue
        t = set(re.findall(r"[a-z0-9_]+", q["query"].lower()))
        if any(len(t & u) / max(1, len(t | u)) >= 0.7 for u in toks):
            continue
        toks.append(t)
        queries.append(q)
    queries = queries[:MAX_QUERIES]
    sources, seen_urls, errors = [], set(), []
    for q in queries:
        try:
            res = tavily.search(q["query"])
        except Exception as e:  # TavilyUnavailable and network errors
            errors.append(str(e)); emit("research_query", query=q["query"], error=str(e)); continue
        added = 0
        for r in res["results"]:
            if r["url"] and r["url"] not in seen_urls:
                seen_urls.add(r["url"])
                sources.append({"id": f"S{len(sources) + 1}", "title": r["title"], "url": r["url"],
                                "content": r["content"][:700], "query": q["query"]})
                added += 1
        emit("research_query", query=q["query"], hypothesis=q.get("hypothesis"), results=added, from_cache=res["from_cache"])
    if not sources:
        return {"status": "inconclusive", "reason": "; ".join(errors) or "no results returned",
                "queries": queries, "sources": [], "findings": []}
    src_txt = "\n\n".join(f"[{s['id']}] {s['title']} ({s['url']})\n{s['content']}" for s in sources)
    raw = llm.chat_json("researcher_findings", SYS_RF, f"HYPOTHESES:\n{summary}\n\nSOURCES:\n{src_txt}", max_tokens=2500)
    by_id = {s["id"]: s for s in sources}
    hyp_ids = {h["id"] for h in hyps}
    findings = []
    for f in raw.get("findings") or []:
        if not isinstance(f, dict) or f.get("hypothesis") not in hyp_ids or f.get("source") not in by_id:
            continue
        quote = str(f.get("quote", ""))
        verified = len(_squash(quote)) >= 12 and _squash(quote) in _squash(by_id[f["source"]]["content"])
        stance = f.get("stance") if f.get("stance") in ("supports", "challenges", "inconclusive") else "inconclusive"
        findings.append({"hypothesis": f["hypothesis"], "stance": stance if verified else "inconclusive",
                         "claim": str(f.get("claim", ""))[:300], "source": f["source"], "quote": quote[:300],
                         "quote_verified": verified})
    return {"status": "ok" if any(f["quote_verified"] for f in findings) else "inconclusive",
            "reason": "", "queries": queries, "sources": sources, "findings": findings}


# ----------------------------------------------------------------- skeptic ---
SYS_SK = COMMON + """
Role: Skeptic. Challenge each hypothesis. Separate confirmed_facts (ids of logs 'L..' or VERIFIED sources 'S..')
from assumptions, name the strongest alternative explanation, say what observation would refute it, and give a
calibrated confidence (hypotheses compete, so confidences should roughly sum to <= 1). Findings marked
quote_verified=false are NOT evidence. Schema:
{"verdicts":[{"hypothesis":"H1","confidence":0.0,"confirmed_facts":["L2"],"assumptions":["..."],
"alternative":"...","would_refute":"...","challenge":"one sentence"}],"leading":"H1"}"""


def skeptic(llm, obs: dict, hyps: List[dict], res: dict) -> dict:
    fnd = "\n".join(f"- {f['hypothesis']} {f['stance']} via {f['source']} verified={f['quote_verified']}: {f['claim']}"
                    for f in res["findings"]) or "(no external research available)"
    hyp_txt = "\n".join(f"{h['id']} [{h['service']}/{h['kind']}] conf={h['confidence']} evidence={h['evidence']}: {h['statement']}" for h in hyps)
    raw = llm.chat_json("skeptic", SYS_SK, f"{render_observation(obs)}\n\nHYPOTHESES:\n{hyp_txt}\n\nRESEARCH FINDINGS:\n{fnd}")
    valid_ids = {l["id"] for l in obs["logs"]} | {s["id"] for s in res["sources"]}
    verdicts, hmap = [], {h["id"]: h for h in hyps}
    for v in raw.get("verdicts") or []:
        if isinstance(v, dict) and v.get("hypothesis") in hmap:
            verdicts.append({"hypothesis": v["hypothesis"], "confidence": _clamp(v.get("confidence"), hmap[v["hypothesis"]]["confidence"]),
                             "confirmed_facts": _ids(v.get("confirmed_facts"), valid_ids),
                             "assumptions": [str(a)[:200] for a in (v.get("assumptions") or [])][:4],
                             "alternative": str(v.get("alternative", ""))[:300], "would_refute": str(v.get("would_refute", ""))[:300],
                             "challenge": str(v.get("challenge", ""))[:300]})
    conf = {h["id"]: h["confidence"] for h in hyps}
    conf.update({v["hypothesis"]: v["confidence"] for v in verdicts})
    leading = raw.get("leading") if raw.get("leading") in hmap else max(conf, key=conf.get)
    if conf[leading] < max(conf.values()):  # trust the numbers over a contradictory label
        leading = max(conf, key=conf.get)
    return {"verdicts": verdicts, "leading": leading, "confidence": conf}


# ----------------------------------------------------------------- planner ---
def system_planner(grammar: str) -> str:
    return COMMON + """
Role: Planner. Propose 3-4 candidate recovery actions, most preferred first, including at least one
alternative approach (for example a mitigation versus a root-cause fix). Prefer the least disruptive action
that addresses the root cause. A separate policy engine and simulator will judge every action; do not self-censor.
Allowed action grammar:
""" + grammar + """
Schema: {"candidates":[{"action":{"kind":"...","target":"...","params":{}},"rationale":"...",
"expected_effect":"...","predicts_resolved":true}]}"""


def parse_action(d, profile=None) -> Action:
    P = profile or twin.IT
    if not isinstance(d, dict):
        raise ValueError("action is not an object")
    kind, target, params = d.get("kind"), d.get("target"), d.get("params") or {}
    if kind not in P.known_kinds:
        raise ValueError(f"unknown action kind '{kind}'")
    if target not in P.baseline_config:
        raise ValueError(f"unknown target '{target}'")
    if not isinstance(params, dict):
        raise ValueError("params must be an object")
    need = {"revert_config": "key", "scale_up": "replicas", "scale_down": "replicas", "rate_limit": "rps",
            "block_traffic": "percent", "set_config": "key"}.get(kind)
    if need and need not in params:
        raise ValueError(f"{kind} requires params.{need}")
    if kind == "revert_config" and params["key"] not in P.baseline_config[target]:
        raise ValueError(f"{target} has no config key '{params['key']}'")
    try:
        if "replicas" in params: params["replicas"] = int(params["replicas"])
        if "rps" in params: params["rps"] = int(params["rps"])
        if "percent" in params: params["percent"] = float(params["percent"])
    except (TypeError, ValueError):
        raise ValueError("non-numeric parameter")
    return Action(kind, target, dict(params))


def plan(llm, obs: dict, hyps: List[dict], leading: str, feedback: Optional[str] = None, profile=None) -> Tuple[List[dict], List[dict]]:
    hyp_txt = "\n".join(f"{h['id']}{' (LEADING)' if h['id'] == leading else ''} [{h['service']}/{h['kind']}] conf={h['confidence']:.2f}: {h['statement']}" for h in hyps)
    user = f"{render_observation(obs)}\n\nHYPOTHESES:\n{hyp_txt}"
    if feedback:
        user += f"\n\nPREVIOUS ROUND: none of these worked when simulated. Propose different actions.\n{feedback}"
    P = profile or twin.IT
    raw = llm.chat_json("planner", system_planner(P.grammar), user)
    props, rejected, seen = [], [], set()
    for c in (raw.get("candidates") or [])[:6]:
        try:
            a = parse_action(c.get("action") if isinstance(c, dict) else None, P)
        except ValueError as e:
            rejected.append({"raw": str(c)[:200], "reason": str(e)}); continue
        if a.label() in seen:
            continue
        seen.add(a.label())
        props.append({"action": a, "rationale": str(c.get("rationale", ""))[:300],
                      "expected_effect": str(c.get("expected_effect", ""))[:300],
                      "predicts_resolved": c.get("predicts_resolved") if isinstance(c.get("predicts_resolved"), bool) else None})
    if not props:
        raise AgentError("Planner produced no valid actions")
    return props, rejected
