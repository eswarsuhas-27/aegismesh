"""Runs one incident through the full loop and streams every step as an event.

observe -> investigate -> research -> challenge -> plan -> simulate -> policy
-> select -> execute -> verify -> explain
If no safe action resolves the incident (for example a life-critical restart that needs a
human), it executes the safest mitigation, requests approval, and says so.
"""
from __future__ import annotations

import time
import uuid
from typing import Callable, List, Optional

from . import agents, planner, policy, twin, usage
from .llm import LLMError
from .scenarios import BY_ID, build
from .tavily import Tavily


class RunLLM:
    """Per-run wrapper: records and emits every Token Factory call."""
    def __init__(self, base, emit):
        self.base, self.emit, self.calls = base, emit, []

    def chat_json(self, role, system, user, **kw):
        try:
            data, meta = self.base.chat_json(role, system, user, **kw)
        except LLMError as e:
            self.emit("llm_call", role=role, ok=False, error=str(e)[:300]); raise
        self.calls.append(meta); self.emit("llm_call", ok=True, **meta)
        return data


def rc_correct(hyp: Optional[dict], gt: dict) -> bool:
    return bool(hyp) and hyp["service"] == gt["service"] and hyp["kind"] == gt["kind"]


class Run:
    def __init__(self, scenario_id: str, mode: str = "ai", research=True, llm=None,
                 tavily: Optional[Tavily] = None, on_event: Optional[Callable] = None):
        self.id = uuid.uuid4().hex[:8]
        # research: "always" (True) | "adaptive" (search only when log evidence is not decisive) | "off" (False)
        self.research_mode = ("always" if research else "off") if isinstance(research, bool) else research
        self.scenario_id, self.mode, self.research = scenario_id, mode, self.research_mode != "off"
        self.events: List[dict] = []
        self.on_event = on_event
        self.llm = RunLLM(llm, self.emit) if llm is not None else None
        self.tavily = tavily
        self.status, self.result = "running", None

    def emit(self, type_: str, **data) -> None:
        ev = {"i": len(self.events), "ts": round(time.time(), 2), "type": type_, "data": data}
        self.events.append(ev)
        if self.on_event:
            self.on_event(ev)

    def _evaluate(self, world, proposals: List[dict]) -> List[dict]:
        out = []
        for p in proposals:
            verdict, outcome = policy.review(world, p["action"])
            cand = planner.Candidate(p["action"], outcome, verdict)
            out.append({**p, "cand": cand})
            self.emit("candidate", action=p["action"].label(), kind=p["action"].kind, rationale=p.get("rationale", ""),
                      expected_effect=p.get("expected_effect", ""), llm_predicts_resolved=p.get("predicts_resolved"),
                      simulated=outcome.to_dict() if outcome else None, policy=verdict.to_dict(), viable=cand.viable)
        return out

    def execute(self) -> dict:
        t0 = time.time()
        sc = BY_ID[self.scenario_id]
        world = build(sc)
        P = world.profile
        t_detect = world.t
        self.emit("started", scenario=sc.id, title=sc.title, mode=self.mode, research=self.research_mode, domain=sc.domain,
                  expects_escalation=sc.expects_escalation)
        obs = agents.build_observation(world)
        self.emit("observation", **obs)
        risk_start = obs["impact"]["score"]
        tav0 = (self.tavily.live_calls, self.tavily.cache_hits) if self.tavily else (0, 0)

        hyps, leading, res, skep, rejected, degraded, err = [], None, {"status": "disabled", "findings": [], "sources": [], "queries": []}, None, [], False, ""
        rows: List[dict] = []
        try:
            if self.mode == "ai":
                if self.llm is None:
                    raise LLMError("no Token Factory client configured (set NEBIUS_API_KEY)")
                inv = agents.investigate(self.llm, obs)
                hyps = inv["hypotheses"]
                self.emit("hypotheses", hypotheses=hyps, timeline=inv["timeline"], warnings=inv["warnings"])
                ranked = sorted(hyps, key=lambda h: -h["confidence"])
                decisive = (len(ranked[0]["evidence"]) >= 2 and ranked[0]["confidence"] >= 0.85
                            and (len(ranked) == 1 or ranked[1]["confidence"] <= 0.25))
                if self.research_mode == "adaptive" and decisive:   # spend no Tavily credit when the logs already settle it
                    res = {"status": "skipped", "reason": f"adaptive: log evidence already decisive (confidence {ranked[0]['confidence']:.2f}, "
                           f"{len(ranked[0]['evidence'])} supporting log lines)", "queries": [], "sources": [], "findings": []}
                elif self.research:
                    res = agents.research(self.llm, self.tavily, hyps, self.emit)
                self.emit("research", **{k: res[k] for k in ("status", "queries", "sources", "findings")}, reason=res.get("reason", ""))
                skep = agents.skeptic(self.llm, obs, hyps, res)
                for h in hyps:
                    h["confidence"] = skep["confidence"][h["id"]]
                leading = skep["leading"]
                self.emit("skeptic", verdicts=skep["verdicts"], leading=leading, confidence=skep["confidence"])
                proposals, rejected = agents.plan(self.llm, obs, hyps, leading, profile=P)
                if rejected:
                    self.emit("rejected_proposals", items=rejected)
                rows = self._evaluate(world, proposals)
                if not any(r["cand"].viable for r in rows):  # counterfactual feedback loop
                    fb = "\n".join(f"- {r['action'].label()}: " + (f"policy blocked ({', '.join(r['cand'].verdict.blocked_by)})" if not r["cand"].verdict.allowed
                                   else f"simulated resolved={r['cand'].outcome.resolved}, health after={r['cand'].outcome.health_after}") for r in rows)
                    self.emit("replan", feedback=fb)
                    proposals2, _ = agents.plan(self.llm, obs, hyps, leading, feedback=fb, profile=P)
                    have = {r["action"].label() for r in rows}
                    rows += self._evaluate(world, [p for p in proposals2 if p["action"].label() not in have])
        except (LLMError, agents.AgentError) as e:
            err = str(e)
            degraded = True
            self.emit("agent_error", error=err, fallback="deterministic baseline planner")
        if self.mode == "baseline" or degraded:
            rows = self._evaluate(world, [{"action": a, "rationale": "exhaustive enumeration (no AI)", "expected_effect": "", "predicts_resolved": None}
                                          for a in planner.generate_candidates(world)])

        probes = P.probes()
        probe_blocked = 0
        for a in probes:  # red-team: fixed prohibited actions must always be blocked
            v, _ = policy.review(world, a)
            probe_blocked += (not v.allowed)
            self.emit("probe", action=a.label(), blocked=not v.allowed, blocked_by=v.blocked_by)

        # select -> execute -> verify (max 2 attempts)
        attempts, tried, recovered = [], set(), False
        for _ in range(2):
            viable = [r for r in rows if r["cand"].viable and r["action"].label() not in tried]
            if not viable:
                break
            best = min(viable, key=lambda r: r["cand"].cost() + (rows.index(r),))
            a = best["action"]
            tried.add(a.label())
            self.emit("selected", action=a.label(), reason="lowest-cost action that is policy-allowed and resolves the incident in simulation")
            observed = twin.apply(world, a)
            ver = twin.verify(best["cand"].outcome, world)
            attempts.append({"action": a.label(), "verification": ver})
            self.emit("executed", action=a.label(), log=[e.line() for e in world.logs[-4:]])
            self.emit("verified", action=a.label(), recurrence_in_ticks=observed.recurrence_in_ticks, **ver)
            if ver["recovered"]:
                recovered = True
                break
            rows = self._evaluate(world, [{"action": r["action"], "rationale": r.get("rationale", ""), "expected_effect": "",
                                           "predicts_resolved": r.get("predicts_resolved")} for r in rows if r["action"].label() not in tried])

        # nothing safe resolves it: mitigate, request human approval, never override policy
        mitigation, approvals = None, []
        if not attempts:
            self.emit("escalate", message="No candidate was both policy-allowed and predicted to resolve the incident. Nothing was executed to fix it.")
            have = {r["action"].label() for r in rows}
            rows += self._evaluate(world, [{"action": a, "rationale": "policy-safe mitigation while awaiting human approval", "expected_effect": "", "predicts_resolved": None}
                                           for a in P.mitigations(world) if a.label() not in have])
            for r in rows:
                c = r["cand"]
                if c.outcome and c.outcome.resolved and "protected_service_restart" in c.verdict.blocked_by:
                    approvals.append(r)
                    self.emit("approval_request", action=r["action"].label(), simulated=c.outcome.to_dict(),
                              message="Resolves the incident in simulation but needs human approval (protected clinical or stateful service).")
            helpful = [r for r in rows if r["cand"].verdict.allowed and r["cand"].outcome and
                       r["cand"].outcome.clinical_risk_after < r["cand"].outcome.clinical_risk_noop - 1e-9]
            if helpful:
                best = min(helpful, key=lambda r: (r["cand"].outcome.clinical_risk_after, rows.index(r)))
                a = best["action"]
                before_score = P.impact(world, twin.health(world))["score"]
                twin.apply(world, a)
                ver = twin.verify(best["cand"].outcome, world)
                mitigation = {"action": a.label(), "risk_before": before_score, "risk_after": ver["impact"]["score"], "verification": ver}
                self.emit("mitigation", action=a.label(), risk_before=before_score, risk_after=ver["impact"]["score"],
                          impact=ver["impact"], observed_health=ver["observed_health"], prediction_matches=ver["prediction_matches"],
                          note="Technical fault persists. This reduces clinical impact only." if not ver["recovered"] else "")

        lead = next((h for h in hyps if h["id"] == leading), None)
        cands = [r["cand"] for r in rows]
        pa = [(r.get("predicts_resolved") == r["cand"].outcome.resolved) for r in rows if r.get("predicts_resolved") is not None and r["cand"].outcome]
        ver_n = sum(f["quote_verified"] for f in res["findings"])
        calls = self.llm.calls if self.llm else []
        risk_end = P.impact(world, twin.health(world))["score"]
        mitigated = mitigation is not None
        success = (mitigated and bool(approvals) and not recovered) if sc.expects_escalation else recovered
        metrics = {
            "recovered": recovered, "success": success, "mitigated": mitigated, "approval_requests": len(approvals),
            "root_cause_correct": rc_correct(lead, sc.root_cause) if self.mode == "ai" and not degraded else None,
            "attempts": len(attempts), "unnecessary_remediations": len(attempts) - (1 if recovered else 0),
            "ticks_to_recovery": (world.t - t_detect) if recovered else None, "wall_seconds": round(time.time() - t0, 2),
            "research_mode": self.research_mode, "tavily_live": (self.tavily.live_calls - tav0[0]) if self.tavily else 0,
            "tavily_searches": ((self.tavily.live_calls - tav0[0]) + (self.tavily.cache_hits - tav0[1])) if self.tavily else 0,
            "candidates": len(cands), "blocked_by_policy": sum(not c.verdict.allowed for c in cands),
            "probe_block_rate": round(probe_blocked / len(probes), 2),
            "clinical_risk_start": risk_start, "clinical_risk_end": risk_end, "domain": sc.domain, "expects_escalation": sc.expects_escalation,
            "llm_calls": len(calls), "llm_tokens": sum(c.get("prompt_tokens", 0) + c.get("completion_tokens", 0) for c in calls),
            "models": sorted({c["model"] for c in calls}), "research_status": res["status"], "sources": len(res["sources"]),
            "verified_citations": ver_n, "unverified_citations": len(res["findings"]) - ver_n,
            "llm_prediction_accuracy": round(sum(pa) / len(pa), 2) if pa else None, "degraded": degraded,
        }
        if calls:
            usage.record(nebius_calls=len(calls), nebius_tokens=metrics["llm_tokens"], ai_incidents=1)
        report = self._report(sc, obs, lead, res, rows, attempts, recovered, metrics, err, mitigation, approvals)
        self.emit("report", markdown=report)
        self.emit("done", metrics=metrics)
        self.status = "done"
        self.result = {"id": self.id, "scenario": sc.id, "mode": self.mode, "research": self.research,
                       "metrics": metrics, "report": report, "events": self.events}
        return self.result

    def _report(self, sc, obs, lead, res, rows, attempts, recovered, m, err, mitigation, approvals) -> str:
        L = [f"# Incident report: {sc.title}", f"Mode: {self.mode}{' (degraded: ' + err + ')' if err else ''}; research: {res['status']}"]
        if sc.domain == "hospital":
            L.append("_Simulation with synthetic data. Not a medical device and not clinical advice._")
        L += ["", "## Impact at detection", ", ".join(f"{k}={v}" for k, v in obs["health"].items())]
        if sc.domain == "hospital":
            L += [f"Clinical impact score {obs['impact']['score']}:"] + [f"- {i}" for i in obs["impact"]["items"]]
        L.append("")
        if lead:
            L += ["## Likely root cause", f"**{lead['service']} / {lead['kind']}** (confidence {lead['confidence']:.2f}): {lead['statement']}",
                  "Evidence: " + ", ".join(lead["evidence"] or ["none cited"]), ""]
        good = [f for f in res["findings"] if f["quote_verified"]]
        if good:
            src = {s["id"]: s for s in res["sources"]}
            L += ["## External research (Tavily, quotes verified against retrieved text)"]
            L += [f"- {f['hypothesis']} {f['stance']}: {f['claim']} [{src[f['source']]['title']}]({src[f['source']]['url']})" for f in good]
            L += [""]
        elif res["status"] == "skipped":
            L += ["## External research", f"Skipped to save API credits ({res['reason']}).", ""]
        elif self.research and self.mode == "ai":
            L += ["## External research", f"Inconclusive or unavailable ({res.get('reason') or res['status']}). No citations were used.", ""]
        L += ["## Alternatives considered"]
        for r in rows:
            c = r["cand"]
            verdict = "blocked: " + ", ".join(c.verdict.blocked_by) if not c.verdict.allowed else ("resolves in simulation" if c.outcome.resolved else "does not resolve")
            L.append(f"- `{r['action'].label()}`: {verdict}")
        L += ["", "## Action and verified result"]
        for a in attempts:
            v = a["verification"]
            L.append(f"- Executed `{a['action']}`. Prediction matched observation: {v['prediction_matches']}. Observed recovered: {v['recovered']}.")
        for r in approvals:
            L.append(f"- **Human approval required** for `{r['action'].label()}`: resolves the incident in simulation but touches a protected system.")
        if mitigation:
            L.append(f"- Executed mitigation `{mitigation['action']}`: clinical impact {mitigation['risk_before']} -> {mitigation['risk_after']}. The technical fault persists.")
        if not attempts and not mitigation:
            L.append("- No safe resolving action found; escalated to a human. Nothing executed.")
        if recovered:
            L += ["", f"**Outcome: RECOVERED (verified from simulator state)** in {m['ticks_to_recovery']} tick(s), {m['unnecessary_remediations']} unnecessary remediation(s)."]
        elif mitigation and approvals:
            L += ["", "**Outcome: MITIGATED, HUMAN APPROVAL REQUIRED.** The system did not override the safety policy."]
        else:
            L += ["", "**Outcome: NOT RECOVERED.**"]
        return "\n".join(L)
