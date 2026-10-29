"""Rule-based baseline planner (no LLM). Enumerates candidates, simulates each,
runs policy, and picks the least costly allowed action that resolves the incident.

The LLM planner will later replace `generate_candidates`; simulation, policy and
selection stay exactly as they are.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from . import policy, twin
from .twin import Action, Outcome, World


@dataclass
class Candidate:
    action: Action
    outcome: Optional[Outcome]
    verdict: policy.Verdict

    @property
    def viable(self) -> bool:
        return self.verdict.allowed and self.outcome is not None and self.outcome.resolved

    def cost(self):
        o = self.outcome
        return (1 if o.recurrence_in_ticks is not None else 0, o.shed_pct, o.replicas_added, o.clinical_risk_after)


def generate_candidates(w: World) -> List[Action]:
    return w.profile.candidates(w)


def evaluate(w: World, actions: List[Action]) -> List[Candidate]:
    out = []
    for a in actions:
        verdict, outcome = policy.review(w, a)
        out.append(Candidate(a, outcome, verdict))
    return out


def select(cands: List[Candidate]) -> Optional[Candidate]:
    viable = [c for c in cands if c.viable]
    return min(viable, key=lambda c: c.cost()) if viable else None
