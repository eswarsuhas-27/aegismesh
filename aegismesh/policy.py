"""Independent safety policy. Knows nothing about LLMs; judges (world, action).

Every rule is evaluated against the twin's own simulation of the action, so a
persuasive recommendation cannot talk its way past it. Action permissions and
protected (human-approval) services come from the domain profile.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from . import twin

MAX_SHED_PCT = 30.0
MAX_REPLICAS = 6
MAX_REPLICAS_ADDED = 3
EPS = 1e-9


@dataclass
class Check:
    rule: str
    passed: bool
    detail: str


@dataclass
class Verdict:
    checks: List[Check] = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def blocked_by(self) -> List[str]:
        return [c.rule for c in self.checks if not c.passed]

    def to_dict(self) -> dict:
        return {"allowed": self.allowed, "blocked_by": self.blocked_by, "checks": [c.__dict__ for c in self.checks]}


def review(world: twin.World, action: twin.Action) -> Tuple[Verdict, Optional[twin.Outcome]]:
    P = world.profile
    v = Verdict()
    ok = action.kind in P.allowed_kinds
    v.checks.append(Check("action_kind_permitted", ok, f"'{action.kind}' is {'permitted' if ok else 'not on the permitted action list'}"))
    in_scope = action.target in world.services
    v.checks.append(Check("target_in_scope", in_scope, f"target '{action.target}' {'is' if in_scope else 'is not'} a managed service"))
    if not (ok and in_scope):
        return v, None

    if action.kind == "revert_config":
        key = action.params.get("key")
        known = key in P.baseline_config.get(action.target, {})
        v.checks.append(Check("revert_to_known_baseline", known, f"{key} {'has' if known else 'has no'} a recorded known-good baseline"))
    if action.kind == "restart_service":
        prot = action.target in P.protected
        v.checks.append(Check("protected_service_restart", not prot,
                              f"{action.target} is {'protected (life-critical or stateful: needs human approval)' if prot else 'not protected'}"))

    out = twin.simulate(world, action)
    v.checks.append(Check("traffic_shed_limit", out.shed_pct <= MAX_SHED_PCT, f"predicted shed {out.shed_pct}% (limit {MAX_SHED_PCT}%)"))
    replicas = world.services[action.target].replicas + out.replicas_added
    v.checks.append(Check("replica_budget", replicas <= MAX_REPLICAS and out.replicas_added <= MAX_REPLICAS_ADDED,
                          f"adds {out.replicas_added}, total {replicas} (max {MAX_REPLICAS}, +{MAX_REPLICAS_ADDED} per action)"))
    v.checks.append(Check("no_collateral_outage", not out.collateral, f"healthy services hit by restart outage: {out.collateral or 'none'}"))
    v.checks.append(Check("no_new_degradation", not out.newly_degraded, f"services made worse than doing nothing: {out.newly_degraded or 'none'}"))
    v.checks.append(Check("no_data_loss", out.data_loss == 0, f"queued messages destroyed: {out.data_loss}"))
    v.checks.append(Check("clinical_risk_not_increased", out.clinical_risk_after <= out.clinical_risk_noop + EPS,
                          f"clinical impact {out.clinical_risk_after} vs {out.clinical_risk_noop} if nothing is done"))
    return v, out
