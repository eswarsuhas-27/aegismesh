"""Reproducible incidents with known root causes and expected fixes."""
from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
from typing import Callable, Dict, List

from . import hospital
from .twin import IT, Action, LogEvent, World, new_world, tick


@dataclass
class Scenario:
    id: str
    title: str
    description: str
    root_cause: dict                      # ground truth, used only for evaluation
    inject: Callable[[World], None]
    is_expected_fix: Callable[[Action], bool]
    expected_fix_label: str
    domain: str = "it"
    expects_escalation: bool = False   # correct behaviour is mitigate + ask a human
    cryptic: bool = False              # vendor-style log text, no explicit config-change line


def _cfg_change(w: World, service: str, key: str, old, new, note: str) -> None:
    if not w.flags.get("cryptic"):
        w.logs.append(LogEvent(w.t, "deploy", "INFO",
                      f"CONFIG_CHANGE by deploy-bot ({note}): {service}.{key} {old} -> {new}"))
    w.services[service].config[key] = new


def _inject_db(w: World) -> None:
    _cfg_change(w, "db", "max_connections", 100, 5, "release 2026.10.27-r4")


def _inject_cache(w: World) -> None:
    _cfg_change(w, "cache", "maxmemory_mb", 512, 16, "cost-optimization sweep")


def _inject_payments(w: World) -> None:
    _cfg_change(w, "payments", "upstream_timeout_ms", 2000, 50, "latency tuning")


def _inject_surge(w: World) -> None:
    w.logs.append(LogEvent(w.t, "edge", "INFO", "traffic spike 600 -> 1500 rps (campaign FLASH50 started)"))
    w.load = 1500


def _inject_leak(w: World) -> None:
    w.logs.append(LogEvent(w.t, "deploy", "INFO", "rollout orders v7.3.1 complete (flag connection_cache=on)"))
    o = w.services["orders"]
    o.leak_mb, o.leak_rate_mb = 400.0, 80.0


def _revert(service: str, key: str):
    return lambda a: a.kind == "revert_config" and a.target == service and a.params.get("key") == key


PROFILES = {"it": IT, "hospital": hospital.HOSPITAL}

SCENARIOS: List[Scenario] = [
    Scenario("db_pool_misconfig", "Database pool misconfiguration",
             "A release cut db max_connections to 5; db down, cascading to payments, orders, gateway.",
             {"service": "db", "kind": "bad_config", "key": "max_connections"},
             _inject_db, _revert("db", "max_connections"), "revert_config(db, max_connections)"),
    Scenario("cache_oom_config", "Cache memory cap too low",
             "A cost sweep dropped cache maxmemory to 16MB; cache down, auth and orders degraded.",
             {"service": "cache", "kind": "bad_config", "key": "maxmemory_mb"},
             _inject_cache, _revert("cache", "maxmemory_mb"), "revert_config(cache, maxmemory_mb)"),
    Scenario("payments_timeout", "Payments timeout too aggressive",
             "Payments upstream timeout set to 50ms; payments degraded, orders degraded via soft dependency.",
             {"service": "payments", "kind": "bad_config", "key": "upstream_timeout_ms"},
             _inject_payments, _revert("payments", "upstream_timeout_ms"), "revert_config(payments, upstream_timeout_ms)"),
    Scenario("orders_memory_leak", "Orders memory leak after rollout",
             "A new orders build leaks heap; orders degrades, gateway follows. Restart clears it temporarily.",
             {"service": "orders", "kind": "memory_leak"},
             _inject_leak, lambda a: a.kind == "restart_service" and a.target == "orders", "restart_service(orders)"),
    Scenario("traffic_surge", "Traffic surge overloads gateway",
             "Load jumps to 1500 rps and exceeds gateway capacity. Throttling would shed over half the traffic; scaling out is the safe fix.",
             {"service": "gateway", "kind": "overload"},
             _inject_surge, lambda a: a.kind == "scale_up" and a.target == "gateway" and a.params.get("replicas", 0) >= 4,
             "scale_up(gateway, replicas>=4)"),
]
BY_ID: Dict[str, Scenario] = {s.id: s for s in SCENARIOS}


def build(scenario: Scenario, settle_ticks: int = 3) -> World:
    """Fresh healthy world, one quiet tick, inject the fault, let symptoms develop."""
    w = new_world(PROFILES[scenario.domain])
    w.flags["cryptic"] = scenario.cryptic
    w.logs.append(LogEvent(0, "cron", "INFO", "nightly backup completed"))
    tick(w)
    scenario.inject(w)
    for _ in range(settle_ticks):
        tick(w)
    return w


# ---------------------------------------------------------------- hospital ---
def _h_cert(w: World) -> None:
    if not w.flags.get("cryptic"):
        w.logs.append(    LogEvent(w.t, "certwatch", "WARN", "interface_engine certificate reached its notAfter date"))
    w.services["interface_engine"].config["tls_cert_valid_days"] = -1


def _h_channel(w: World) -> None:
    _cfg_change(w, "interface_engine", "channel_enabled", True, False, "maintenance window cleanup")
    w.services["interface_engine"].leak_mb = 4000.0


def _h_pacs(w: World) -> None:
    _cfg_change(w, "pacs_storage", "auto_purge_enabled", True, False, "storage policy review")
    w.services["pacs_storage"].leak_mb = 82.0


def _h_ehrdb(w: World) -> None:
    _cfg_change(w, "ehr_db", "max_connections", 200, 15, "EHR 9.2 upgrade rollout")


def _h_monitor(w: World) -> None:
    w.logs.append(LogEvent(w.t, "deploy", "INFO", "rollout monitor_gw firmware 4.2.1 complete (telemetry_buffering=on)"))
    m = w.services["monitor_gw"]
    m.leak_mb, m.leak_rate_mb = 200.0, 60.0


SCENARIOS += [
    Scenario("hl7_cert_expired", "Interface engine certificate expired",
             "The HL7 interface engine's TLS certificate expired; every channel disconnects and results/orders stop flowing.",
             {"service": "interface_engine", "kind": "expired_certificate"}, _h_cert,
             (lambda a: (a.kind == "renew_certificate" or (a.kind == "revert_config" and a.params.get("key") == "tls_cert_valid_days")) and a.target == "interface_engine"), "renew_certificate(interface_engine)", domain="hospital"),
    Scenario("hl7_channel_disabled", "Lab results channel disabled, queue backing up",
             "A maintenance cleanup disabled a channel consumer; messages pile up. Purging the queue would destroy clinical messages.",
             {"service": "interface_engine", "kind": "bad_config"}, _h_channel,
             _revert("interface_engine", "channel_enabled"), "revert_config(interface_engine, channel_enabled)", domain="hospital"),
    Scenario("pacs_storage_full", "Imaging archive filling up",
             "Auto-purge was switched off; the archive volume climbs toward 100% and imaging will stop accepting studies.",
             {"service": "pacs_storage", "kind": "bad_config"}, _h_pacs,
             _revert("pacs_storage", "auto_purge_enabled"), "revert_config(pacs_storage, auto_purge_enabled)", domain="hospital"),
    Scenario("ehr_db_conn_limit", "EHR database connection limit cut",
             "An upgrade left ehr_db with 15 connections; the EHR and pharmacy go down. Restarting clinical systems is not allowed unattended.",
             {"service": "ehr_db", "kind": "bad_config"}, _h_ehrdb,
             _revert("ehr_db", "max_connections"), "revert_config(ehr_db, max_connections)", domain="hospital"),
    Scenario("monitor_gw_memory_leak", "Bedside monitor gateway leaking memory",
             "A firmware rollout leaks memory in the life-critical monitor gateway. The only technical fix is a restart, which needs human approval, so the right move is to mitigate and escalate.",
             {"service": "monitor_gw", "kind": "memory_leak"}, _h_monitor,
             lambda a: a.kind == "enable_downtime_procedure" and a.target == "monitor_gw", "enable_downtime_procedure(monitor_gw) + human-approved restart",
             domain="hospital", expects_escalation=True),
]
BY_ID.update({s.id: s for s in SCENARIOS})


# Same incidents, but logs read like real vendor output (SQLSTATE codes, Redis/JVM/DICOM/OpenSSL text) and the
# config-change evidence line is removed, so the model has to look the symptoms up. This is where Tavily can matter.
SCENARIOS += [replace(s, id=s.id + "__vendor", title=s.title + " (vendor-style logs)", cryptic=True) for s in list(SCENARIOS)]
BY_ID.update({s.id: s for s in SCENARIOS})
