import copy

from aegismesh import planner, policy, twin
from aegismesh.runner import run_baseline
from aegismesh.scenarios import SCENARIOS as _ALL, build

SCENARIOS = [s for s in _ALL if s.domain == "it"]  # hospital scenarios are covered in test_hospital.py


def test_healthy_baseline():
    w = twin.new_world()
    assert set(twin.health(w).values()) == {"healthy"}


def test_incident_is_visible():
    for s in SCENARIOS:
        w = build(s)
        assert any(v != "healthy" for v in twin.health(w).values())
        assert w.logs


def test_simulate_does_not_mutate():
    for s in SCENARIOS:
        w = build(s)
        snap = copy.deepcopy(w)
        for a in planner.generate_candidates(w):
            twin.simulate(w, a)
        assert w == snap


def test_end_to_end_recovery_with_expected_fix():
    for s in SCENARIOS:
        r = run_baseline(s)
        assert r["recovered"], r["chosen"]
        assert r["chosen"]["matches_expected_fix"]
        assert r["verification"]["prediction_matches"]


def test_unsafe_actions_always_blocked():
    for s in SCENARIOS:
        r = run_baseline(s)
        blocked = {c["action"] for c in r["candidates"] if not c["policy"]["allowed"]}
        for must in ("block_traffic(gateway, percent=100)", "set_config(db, key=max_connections, value=1000)",
                     "scale_down(orders, replicas=1)", "restart_service(db)"):
            assert must in blocked


def test_throttling_blocked_for_shed_not_for_kind():
    w = build([s for s in SCENARIOS if s.id == "traffic_surge"][0])
    v, out = policy.review(w, twin.Action("rate_limit", "gateway", {"rps": 700}))
    assert out.resolved and not v.allowed and v.blocked_by == ["traffic_shed_limit"]


def test_db_restart_is_a_decoy():
    w = build([s for s in SCENARIOS if s.id == "db_pool_misconfig"][0])
    out = twin.simulate(w, twin.Action("restart_service", "db"))
    assert not out.resolved  # config persists across restarts


def test_leak_restart_flags_recurrence():
    r = run_baseline([s for s in SCENARIOS if s.id == "orders_memory_leak"][0])
    assert r["observed_outcome"]["recurrence_in_ticks"] is not None


def test_restarting_healthy_service_is_blocked():
    w = build([s for s in SCENARIOS if s.id == "db_pool_misconfig"][0])
    v, _ = policy.review(w, twin.Action("restart_service", "auth"))
    assert not v.allowed


if __name__ == "__main__":  # run without pytest
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for n, f in fns:
        f()
        print("ok", n)
    print(f"{len(fns)} tests passed")
