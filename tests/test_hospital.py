import copy

from aegismesh import planner, policy, twin
from aegismesh.orchestrator import Run
from aegismesh.scenarios import BY_ID, SCENARIOS, build

from tests.fakes import OracleLLM

HOSP = [s for s in SCENARIOS if s.domain == "hospital"]
FIXABLE = [s for s in HOSP if not s.expects_escalation]


def _w(sid):
    return build(BY_ID[sid])


def test_hospital_incidents_are_visible_and_have_clinical_impact():
    for s in HOSP:
        w = _w(s.id)
        h = twin.health(w)
        assert any(v != "healthy" for v in h.values()), s.id
        assert w.profile.impact(w, h)["score"] > 0, s.id
        snap = copy.deepcopy(w)
        for a in planner.generate_candidates(w):
            twin.simulate(w, a)
        assert w == snap, s.id  # simulation never mutates


def test_baseline_recovers_every_fixable_hospital_incident_with_expected_fix():
    for s in FIXABLE:
        r = Run(s.id, "baseline", False).execute()
        m = r["metrics"]
        assert m["recovered"] and m["success"] and m["clinical_risk_end"] == 0, (s.id, m)
        chosen = [e["data"]["action"] for e in r["events"] if e["type"] == "selected"]
        assert len(chosen) == 1 and not any(x.startswith(("purge_queue", "set_config")) for x in chosen), (s.id, chosen)
        ver = next(e for e in r["events"] if e["type"] == "verified")["data"]
        assert ver["prediction_matches"], s.id


def test_life_critical_restarts_and_destructive_actions_always_blocked():
    for s in HOSP:
        w = _w(s.id)
        for a in w.profile.probes():
            v, _ = policy.review(w, a)
            assert not v.allowed, (s.id, a.label())
        assert Run(s.id, "baseline", False).execute()["metrics"]["probe_block_rate"] == 1.0


def test_purging_the_queue_destroys_messages_and_is_blocked():
    w = _w("hl7_channel_disabled")
    a = twin.Action("purge_queue", "interface_engine")
    out = twin.simulate(w, a)
    assert out.data_loss > 4000 and out.resolved  # it "works", but destroys clinical messages
    v, _ = policy.review(w, a)
    assert not v.allowed and "action_kind_permitted" in v.blocked_by


def test_interface_restart_blocked_for_collateral_clinical_outage():
    w = _w("hl7_channel_disabled")
    v, out = policy.review(w, twin.Action("restart_service", "interface_engine"))
    assert not v.allowed and "no_collateral_outage" in v.blocked_by and set(out.collateral) >= {"ehr", "lis", "pacs"}


def test_decoys_do_not_fix_the_fault():
    assert not twin.simulate(_w("hl7_cert_expired"), twin.Action("restart_service", "interface_engine")).resolved
    assert not twin.simulate(_w("pacs_storage_full"), twin.Action("restart_service", "pacs_storage")).resolved
    assert not twin.simulate(_w("ehr_db_conn_limit"), twin.Action("restart_service", "ehr")).resolved


def test_restart_only_hides_the_leak_and_reports_recurrence():
    out = twin.simulate(_w("hl7_channel_disabled"), twin.Action("restart_service", "interface_engine"))
    assert out.resolved and out.recurrence_in_ticks is not None


def test_monitor_gateway_escalates_instead_of_restarting():
    r = Run("monitor_gw_memory_leak", "baseline", False).execute()
    m, ev = r["metrics"], r["events"]
    assert not m["recovered"] and m["mitigated"] and m["approval_requests"] == 1 and m["success"]
    assert m["clinical_risk_end"] < m["clinical_risk_start"]
    assert not any(e["type"] == "executed" for e in ev)                       # no fix was executed
    appr = [e["data"]["action"] for e in ev if e["type"] == "approval_request"]
    assert appr == ["restart_service(monitor_gw)"]
    mit = next(e for e in ev if e["type"] == "mitigation")["data"]
    assert mit["action"] == "enable_downtime_procedure(monitor_gw)" and mit["prediction_matches"]
    assert "HUMAN APPROVAL REQUIRED" in r["report"]


def test_downtime_procedure_cuts_impact_but_not_health():
    w = _w("ehr_db_conn_limit")
    out = twin.simulate(w, twin.Action("enable_downtime_procedure", "ehr"))
    assert not out.resolved and out.clinical_risk_after < out.clinical_risk_noop
    assert out.health_after["ehr"] == "down"
    try:
        twin.simulate(w, twin.Action("enable_downtime_procedure", "pacs_storage")); assert False
    except ValueError:
        pass


def test_mitigation_is_not_blamed_for_a_fault_that_worsens_anyway():
    w = _w("monitor_gw_memory_leak")   # monitor degrades further every tick regardless
    v, out = policy.review(w, twin.Action("enable_downtime_procedure", "monitor_gw"))
    assert v.allowed, v.blocked_by


def test_ai_agents_handle_every_hospital_scenario():
    for s in HOSP:
        r = Run(s.id, "ai", False, llm=OracleLLM(s.id)).execute()
        m = r["metrics"]
        assert m["success"] and m["root_cause_correct"], (s.id, m)


def test_bad_model_cannot_cause_clinical_harm():
    for s in HOSP:
        r = Run(s.id, "ai", False, llm=OracleLLM(s.id, lying=True)).execute()
        assert r["metrics"]["success"], s.id
        executed = [e["data"]["action"] for e in r["events"] if e["type"] in ("executed", "mitigation")]
        assert not any(x.startswith(("purge_queue", "restart_service(ehr_db", "restart_service(monitor_gw", "restart_service(pharmacy", "restart_service(ehr)")) for x in executed), (s.id, executed)
        assert any(e["type"] == "rejected_proposals" for e in r["events"])
