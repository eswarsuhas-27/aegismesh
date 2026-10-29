"""Deterministic digital twin engine. Domain rules live in a Profile.

Everything here is plain rules: no LLM, no randomness. The twin is the single
source of truth for what an incident looks like and what an action does.

    simulate(world, action) -> Outcome   # counterfactual, never mutates `world`
    apply(world, action)    -> Outcome   # mutates `world` (the "real" run)
    verify(predicted, world)             # compares predicted vs observed state

Two profiles ship: IT (cloud microservices, here) and HOSPITAL (hospital.py).
All data is synthetic; nothing touches real infrastructure.
"""
from __future__ import annotations

import copy
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional

HEALTHY, DEGRADED, DOWN = "healthy", "degraded", "down"
_RANK = {HEALTHY: 0, DEGRADED: 1, DOWN: 2}
_NAME = {v: k for k, v in _RANK.items()}
LEAK_DEGRADED_RATIO = 0.6
LEAK_DOWN_RATIO = 0.9


@dataclass
class Profile:
    name: str
    title: str
    context: str                 # shown to the agents
    topology: dict               # service -> [(dependency, hard)]
    order: list                  # dependencies first
    baseline_config: dict
    baseline_replicas: dict
    layout: dict                 # service -> [x, y] for the dashboard graph
    known_kinds: set             # kinds the twin can simulate
    allowed_kinds: set           # kinds policy permits
    protected: set               # restarts need human approval
    grammar: str                 # action grammar given to the Planner
    own: Callable = None         # (w, name) -> status
    message: Callable = None     # (w, name) -> log message for an own fault
    info: Callable = None        # (w, name) -> optional INFO log for a healthy service
    on_tick: Callable = None
    init: Callable = None
    restart: Callable = None     # (w, service) side effect of a restart
    execute_extra: Callable = None
    metrics: Callable = None
    impact: Callable = None      # (w, health) -> {"score": float, "items": [str]}
    recurrence: Callable = None  # (w) -> ticks until a persisting fault returns, or None
    candidates: Callable = None
    mitigations: Callable = None
    probes: Callable = None


@dataclass
class LogEvent:
    t: int
    service: str
    level: str
    message: str

    def line(self) -> str:
        return f"[t={self.t:02d}] {self.level:<5} {self.service:<16} {self.message}"


@dataclass
class Service:
    name: str
    config: dict
    replicas: int
    leak_mb: float = 0.0        # generic gauge: heap, queue backlog, disk % (profile decides)
    leak_rate_mb: float = 0.0


@dataclass
class World:
    t: int = 0
    load: int = 600
    block_pct: float = 0.0
    services: Dict[str, Service] = field(default_factory=dict)
    logs: List[LogEvent] = field(default_factory=list)
    flags: dict = field(default_factory=dict)
    profile: Any = None

    def __post_init__(self):
        if self.profile is None:
            self.profile = IT


@dataclass
class Action:
    kind: str
    target: str
    params: dict = field(default_factory=dict)

    def label(self) -> str:
        p = ", ".join(f"{k}={v}" for k, v in self.params.items())
        return f"{self.kind}({self.target}{', ' + p if p else ''})"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Outcome:
    action: Action
    health_before: Dict[str, str]
    health_after: Dict[str, str]
    resolved: bool
    newly_degraded: List[str]       # worse than BOTH the current state and doing nothing
    collateral: List[str]           # healthy services hit by a transient restart outage
    shed_pct: float
    replicas_added: int
    recurrence_in_ticks: Optional[int]
    clinical_risk_before: float = 0.0
    clinical_risk_after: float = 0.0
    clinical_risk_noop: float = 0.0   # risk if nothing were done this tick
    impact_after: list = field(default_factory=list)
    data_loss: int = 0                # queued messages destroyed by the action

    def to_dict(self) -> dict:
        d = asdict(self)
        d["action"] = self.action.to_dict()
        return d


def new_world(profile: Optional[Profile] = None) -> World:
    p = profile or IT
    w = World(profile=p)
    for name, cfg in p.baseline_config.items():
        w.services[name] = Service(name, dict(cfg), p.baseline_replicas[name])
    if p.init:
        p.init(w)
    return w


# ---------------------------------------------------------------- health ---
def health(w: World, forced_down=frozenset()) -> Dict[str, str]:
    P, out = w.profile, {}
    for name in P.order:
        r = 2 if name in forced_down else _RANK[P.own(w, name)]
        for dep, hard in P.topology[name]:
            d = _RANK[out[dep]]
            r = max(r, d if hard else (1 if d == 2 else 0))
        out[name] = _NAME[r]
    return out


def _emit_logs(w: World) -> None:
    P = w.profile
    h = health(w)
    for name in P.order:
        if h[name] == HEALTHY:
            msg = P.info(w, name) if P.info else None
            if msg:
                w.logs.append(LogEvent(w.t, name, "INFO", msg))
            continue
        level = "ERROR" if h[name] == DOWN else "WARN"
        if P.own(w, name) != HEALTHY:
            w.logs.append(LogEvent(w.t, name, level, P.message(w, name)))
            continue
        for dep, hard in P.topology[name]:
            if h[dep] != HEALTHY and (hard or h[dep] == DOWN):
                w.logs.append(LogEvent(w.t, name, level, f"upstream {dep} {h[dep]}: requests failing, circuit breaker open"))
                break


def tick(w: World) -> None:
    w.t += 1
    w.profile.on_tick(w)
    _emit_logs(w)


def shed_pct(w: World) -> float:
    return round(gateway_stats(w)[2], 1) if "gateway" in w.services else 0.0


def leak_recurrence(w: World, specs: dict) -> Optional[int]:
    """Ticks until a persisting gauge fault returns. specs: service -> threshold(service)."""
    h, best = health(w), None
    for name, thr in specs.items():
        s = w.services[name]
        if s.leak_rate_mb <= 0 or h[name] != HEALTHY:
            continue
        n = max(0, math.floor((thr(s) - s.leak_mb) / s.leak_rate_mb)) + 1
        best = n if best is None else min(best, n)
    return best


# --------------------------------------------------------------- actions ---
def _execute(w: World, a: Action) -> None:
    P = w.profile
    if a.kind not in P.known_kinds:
        raise ValueError(f"unknown action kind: {a.kind}")
    if a.target not in w.services:
        raise ValueError(f"unknown service: {a.target}")
    s, p = w.services[a.target], a.params
    if a.kind == "revert_config":
        try:
            s.config[p["key"]] = P.baseline_config[a.target][p["key"]]
        except KeyError:
            raise ValueError(f"{a.target} has no baseline config key {p.get('key')}")
    elif a.kind == "set_config":
        s.config[p["key"]] = p["value"]
    elif a.kind == "restart_service":
        P.restart(w, s)
    else:
        P.execute_extra(w, a)


def _run(w: World, a: Action) -> Outcome:
    P = w.profile
    before = health(w)
    risk_before = P.impact(w, before)["score"]
    noop = copy.deepcopy(w)
    tick(noop)
    noop_h = health(noop)
    risk_noop = P.impact(noop, noop_h)["score"]
    old_replicas = w.services[a.target].replicas if a.target in w.services else 0
    dl_before = w.flags.get("data_loss", 0)
    _execute(w, a)
    collateral: List[str] = []
    if a.kind == "restart_service":
        peak = health(w, forced_down={a.target})
        collateral = [n for n in P.order if before[n] == HEALTHY and peak[n] != HEALTHY]
    w.logs.append(LogEvent(w.t, "aegismesh", "ACTION", a.label()))
    tick(w)
    after = health(w)
    imp = P.impact(w, after)
    return Outcome(
        action=a, health_before=before, health_after=after,
        resolved=all(v == HEALTHY for v in after.values()),
        newly_degraded=[n for n in P.order if _RANK[after[n]] > max(_RANK[before[n]], _RANK[noop_h[n]])],
        collateral=collateral, shed_pct=shed_pct(w),
        replicas_added=max(0, w.services[a.target].replicas - old_replicas),
        recurrence_in_ticks=P.recurrence(w),
        clinical_risk_before=risk_before, clinical_risk_after=imp["score"], clinical_risk_noop=risk_noop,
        impact_after=imp["items"], data_loss=w.flags.get("data_loss", 0) - dl_before,
    )


def simulate(world: World, action: Action) -> Outcome:
    """Counterfactual: run the action on a deep copy. `world` is untouched."""
    return _run(copy.deepcopy(world), action)


def apply(world: World, action: Action) -> Outcome:
    """Execute the action on the live simulated world."""
    return _run(world, action)


def verify(predicted: Outcome, world: World) -> dict:
    """Observed state vs. the earlier prediction. Never trusts a prediction as proof."""
    observed = health(world)
    order = world.profile.order
    mismatches = {n: (predicted.health_after[n], observed[n]) for n in order if predicted.health_after[n] != observed[n]}
    return {
        "observed_health": observed, "predicted_health": predicted.health_after,
        "prediction_matches": not mismatches, "mismatches": mismatches,
        "recovered": all(v == HEALTHY for v in observed.values()),
        "impact": world.profile.impact(world, observed),
    }


# ============================================================= IT profile ===
TOPOLOGY: Dict[str, List[tuple]] = {
    "gateway": [("auth", True), ("orders", True)],
    "auth": [("cache", False)],
    "orders": [("db", True), ("cache", False), ("payments", False)],
    "payments": [("db", True)],
    "db": [], "cache": [],
}
ORDER = ["db", "cache", "payments", "auth", "orders", "gateway"]
BASELINE_CONFIG = {
    "gateway": {"rate_limit_rps": 2000}, "auth": {"token_ttl_s": 3600}, "orders": {"heap_limit_mb": 1024},
    "payments": {"upstream_timeout_ms": 2000}, "db": {"max_connections": 100}, "cache": {"maxmemory_mb": 512},
}
BASELINE_REPLICAS = {"gateway": 2, "auth": 2, "orders": 2, "payments": 2, "db": 1, "cache": 1}
CAPACITY_PER_REPLICA = 400
NORMAL_LOAD = 600
KNOWN_KINDS = {"revert_config", "set_config", "restart_service", "scale_up", "scale_down", "rate_limit", "block_traffic"}


def gateway_stats(w: World):
    gw = w.services["gateway"]
    admitted = min(w.load, gw.config["rate_limit_rps"]) * (1 - w.block_pct / 100)
    capacity = gw.replicas * CAPACITY_PER_REPLICA
    shed = 0.0 if w.load == 0 else 100 * (1 - admitted / w.load)
    return admitted, capacity, shed


def gauge_status(s: Service, limit: float) -> str:
    r = s.leak_mb / limit
    return DOWN if r > LEAK_DOWN_RATIO else DEGRADED if r > LEAK_DEGRADED_RATIO else HEALTHY


def _it_own(w: World, name: str) -> str:
    s, c = w.services[name], w.services[name].config
    if name == "db":
        return DOWN if c["max_connections"] < 10 else DEGRADED if c["max_connections"] < 50 else HEALTHY
    if name == "cache":
        return DOWN if c["maxmemory_mb"] < 32 else DEGRADED if c["maxmemory_mb"] < 128 else HEALTHY
    if name == "orders":
        return gauge_status(s, c["heap_limit_mb"])
    if name == "payments":
        return DEGRADED if c["upstream_timeout_ms"] < 300 else HEALTHY
    if name == "gateway":
        admitted, cap, _ = gateway_stats(w)
        return DOWN if admitted > cap * 1.5 else DEGRADED if admitted > cap else HEALTHY
    return HEALTHY


_IT_CRYPTIC = {
    "db": "FATAL: sorry, too many clients already (SQLSTATE 53300)",
    "cache": "OOM command not allowed when used memory > 'maxmemory'.",
    "orders": "java.lang.OutOfMemoryError: GC overhead limit exceeded",
    "payments": "java.net.SocketTimeoutException: Read timed out (acquirer-client)",
    "gateway": "upstream connect error or disconnect/reset before headers. reset reason: overflow",
}


def _it_message(w: World, name: str) -> str:
    if w.flags.get("cryptic"):   # vendor-style text: the cause must be looked up, not read
        return _IT_CRYPTIC[name]
    s, c = w.services[name], w.services[name].config
    if name == "db":
        return f"connection pool exhausted: max_connections={c['max_connections']}, clients queueing"
    if name == "cache":
        return f"OOM: used_memory exceeds maxmemory ({c['maxmemory_mb']}MB), evicting keys aggressively"
    if name == "orders":
        return f"heap pressure {s.leak_mb:.0f}/{c['heap_limit_mb']}MB retained, GC overhead limit near"
    if name == "payments":
        return f"acquirer call timed out after {c['upstream_timeout_ms']}ms, retries exhausted"
    admitted, cap, shed = gateway_stats(w)
    return f"admitted {admitted:.0f} rps exceeds capacity {cap} rps, p99 latency rising (shed {shed:.0f}%)"


def _it_info(w: World, name: str):
    if w.flags.get("cryptic"):
        return None
    s = w.services[name]
    if name == "orders" and s.leak_rate_mb > 0:
        return f"retained heap {s.leak_mb:.0f}/{s.config['heap_limit_mb']}MB (+{s.leak_rate_mb:.0f}MB/tick)"
    return None


def _grow(w: World) -> None:
    for s in w.services.values():
        s.leak_mb += s.leak_rate_mb


def _restart_reset(w: World, s: Service) -> None:
    s.leak_mb = 0.0


def _it_extra(w: World, a: Action) -> None:
    s, p = w.services[a.target], a.params
    if a.kind in ("scale_up", "scale_down"):
        s.replicas = int(p["replicas"])
    elif a.kind == "rate_limit":
        s.config["rate_limit_rps"] = int(p["rps"])
    elif a.kind == "block_traffic":
        w.block_pct = float(p["percent"])


def _it_metrics(w: World) -> dict:
    admitted, cap, shed = gateway_stats(w)
    return {"load_rps": w.load, "admitted_rps": round(admitted), "gateway_capacity_rps": cap, "shed_pct": round(shed, 1)}


def _no_impact(w: World, h: dict) -> dict:
    return {"score": 0.0, "items": []}


def _it_candidates(w: World) -> List[Action]:
    acts: List[Action] = []
    for name, s in w.services.items():
        for k, v in s.config.items():
            if v != BASELINE_CONFIG[name][k]:
                acts.append(Action("revert_config", name, {"key": k}))
        acts.append(Action("restart_service", name))
    gw = w.services["gateway"].replicas
    acts += [Action("scale_up", "gateway", {"replicas": gw + n}) for n in (1, 2, 6)]
    acts += [Action("rate_limit", "gateway", {"rps": 700}), Action("block_traffic", "gateway", {"percent": 100}),
             Action("set_config", "db", {"key": "max_connections", "value": 1000}), Action("scale_down", "orders", {"replicas": 1})]
    return acts


IT_GRAMMAR = """ revert_config  target=<service> params={"key":"<config key>"}   restores that key to its known-good baseline
 restart_service target=<service>
 scale_up       target="gateway" params={"replicas":<int>}      absolute replica count
 rate_limit     target="gateway" params={"rps":<int>}
 block_traffic  target="gateway" params={"percent":<number>}"""

IT = Profile(
    name="it", title="Cloud services", context="a simulated cloud microservice environment (gateway, auth, orders, payments, db, cache)",
    topology=TOPOLOGY, order=ORDER, baseline_config=BASELINE_CONFIG, baseline_replicas=BASELINE_REPLICAS,
    layout={"gateway": [180, 28], "auth": [70, 95], "orders": [290, 95], "payments": [290, 185], "db": [180, 225], "cache": [60, 200]},
    known_kinds=KNOWN_KINDS, allowed_kinds={"revert_config", "restart_service", "scale_up", "rate_limit", "block_traffic"},
    protected={"db"}, grammar=IT_GRAMMAR, own=_it_own, message=_it_message, info=_it_info, on_tick=_grow, init=lambda w: None,
    restart=_restart_reset, execute_extra=_it_extra, metrics=_it_metrics, impact=_no_impact,
    recurrence=lambda w: leak_recurrence(w, {"orders": lambda s: LEAK_DEGRADED_RATIO * s.config["heap_limit_mb"]}),
    candidates=_it_candidates, mitigations=lambda w: [],
    probes=lambda: [Action("block_traffic", "gateway", {"percent": 100}), Action("set_config", "db", {"key": "max_connections", "value": 1000}),
                    Action("scale_down", "orders", {"replicas": 1}), Action("restart_service", "db"),
                    Action("scale_up", "gateway", {"replicas": 20}), Action("rate_limit", "gateway", {"rps": 100})],
)
