"""Run one incident end to end and return a full, traceable record."""
from __future__ import annotations

from . import planner, twin
from .scenarios import Scenario, build


def run_baseline(scenario: Scenario) -> dict:
    w = build(scenario)
    health_start = twin.health(w)
    logs_at_detection = [e.line() for e in w.logs]
    cands = planner.evaluate(w, planner.generate_candidates(w))
    chosen = planner.select(cands)

    record = {
        "scenario": scenario.id,
        "title": scenario.title,
        "ground_truth": scenario.root_cause,
        "health_at_detection": health_start,
        "logs_at_detection": logs_at_detection,
        "candidates": [{"action": c.action.label(),
                        "predicted": c.outcome.to_dict() if c.outcome else None,
                        "policy": c.verdict.to_dict(), "viable": c.viable} for c in cands],
        "blocked_count": sum(1 for c in cands if not c.verdict.allowed),
        "chosen": None, "verification": None,
    }
    if chosen is None:
        record["recovered"] = False
        return record

    observed_outcome = twin.apply(w, chosen.action)
    ver = twin.verify(chosen.outcome, w)
    record["chosen"] = {"action": chosen.action.label(), "matches_expected_fix": scenario.is_expected_fix(chosen.action)}
    record["verification"] = ver
    record["observed_outcome"] = observed_outcome.to_dict()
    record["recovered"] = ver["recovered"]
    record["execution_log"] = [e.line() for e in w.logs[len(logs_at_detection):]]
    return record
