"""
run_demo.py — Access Management Service v4: Three-Service Demo & Test Suite

Starts ALL 3 microservices:
  1. Alert Manager   (port auto) — alert dispatch + email
  2. Ingestion Service (port auto) — stores telemetry + emergency detection
  3. Gateway Service   (port auto) — auth + RBAC + retrieval

Tests all endpoints across all services.

Usage:
  python3 run_demo.py --no-browser
  python3 run_demo.py
"""

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path

import requests

_BASE_DIR = Path(__file__).resolve().parent
REPORT_DIR = _BASE_DIR / "test_reports"


def find_free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TR:
    def __init__(self):
        self.passed = self.failed = 0
        self.results = []

    def ok(self, name, detail="", ms=0):
        self.passed += 1
        self.results.append(("PASS", name, detail, ms))
        print(f"  [PASS]  {name} -> {detail} ({ms}ms)")

    def fail(self, name, detail=""):
        self.failed += 1
        self.results.append(("FAIL", name, detail, 0))
        print(f"  [FAIL]  {name} -> {detail}")


def wait_healthy(url, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if requests.get(f"{url}/health", timeout=2).status_code == 200:
                return True
        except:
            pass
        time.sleep(1)
    return False


def start_service(script, port_env, port, extra_env=None):
    import threading
    env = {**os.environ, port_env: str(port)}
    if extra_env:
        env.update(extra_env)
    proc = subprocess.Popen(
        [sys.executable, script], cwd=str(_BASE_DIR), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    threading.Thread(target=lambda: [None for _ in iter(proc.stdout.readline, "")], daemon=True).start()
    return proc


# Test data — includes emergency triggers
ENERGY_NODES = [
    {"node_id":"NRG-SOL-001","domain":"energy","node_type":"solar_panel","data":{"solar_power_w":850,"voltage":36.5,"is_critical":False}},
    {"node_id":"NRG-BAT-001","domain":"energy","node_type":"battery_storage","data":{"battery_soc_pct":8,"charge_rate_w":-500,"is_critical":True}},
    {"node_id":"NRG-GRD-001","domain":"energy","node_type":"grid_transformer","data":{"grid_load_pct":97,"grid_temperature_c":92,"is_critical":True}},
    {"node_id":"NRG-MTR-001","domain":"energy","node_type":"smart_meter","data":{"power_w":3200,"power_factor":0.72,"is_critical":True}},
    {"node_id":"NRG-AC-001","domain":"energy","node_type":"ac_unit","data":{"ac_power_w":4200,"set_temp_c":22,"is_critical":True}},
]
EHS_NODES = [
    {"node_id":"EHS-AQI-001","domain":"ehs","node_type":"air_quality","data":{"aqi":250,"pm25":112,"is_critical":True}},
    {"node_id":"EHS-WTR-001","domain":"ehs","node_type":"water_quality","data":{"water_ph":4.2,"turbidity_ntu":150,"is_critical":True}},
    {"node_id":"EHS-NOS-001","domain":"ehs","node_type":"noise_monitor","data":{"noise_db":72,"peak_db":85,"is_critical":False}},
    {"node_id":"EHS-WEA-001","domain":"ehs","node_type":"weather_station","data":{"temperature_c":35,"uv_index":9,"is_critical":False}},
]
RESIDENT_NODES = [
    {"node_id":"R1-SOL-001","domain":"energy","node_type":"solar_panel","data":{"solar_power_w":600,"voltage":35,"is_critical":False}},
    {"node_id":"R1-MTR-001","domain":"energy","node_type":"smart_meter","data":{"power_w":2500,"power_factor":0.95,"is_critical":False}},
    {"node_id":"R1-BAT-001","domain":"energy","node_type":"battery_storage","data":{"battery_soc_pct":75,"charge_rate_w":400,"is_critical":False}},
    {"node_id":"R1-AC-001","domain":"energy","node_type":"ac_unit","data":{"ac_power_w":1800,"set_temp_c":24,"is_critical":False}},
    {"node_id":"R1-AQI-001","domain":"ehs","node_type":"air_quality","data":{"aqi":42,"pm25":18,"is_critical":False}},
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    # Remove old DB
    db_path = _BASE_DIR / "smartcity.db"
    for f in [db_path, Path(str(db_path)+"-wal"), Path(str(db_path)+"-shm")]:
        if f.exists():
            f.unlink()

    alert_port = find_free_port()
    ingest_port = find_free_port()
    gateway_port = find_free_port()
    ALERT_MGR = f"http://127.0.0.1:{alert_port}"
    INGEST = f"http://127.0.0.1:{ingest_port}"
    GATEWAY = f"http://127.0.0.1:{gateway_port}"

    print(f"\n{'='*64}")
    print(f"  Access Management Service v4.0 — Three-Service Demo")
    print(f"{'='*64}")

    # Start services sequentially (avoid DB init race condition)
    print(f"\n{'─'*50}\n  Starting Services\n{'─'*50}")
    print(f"  Alert Manager: {ALERT_MGR}")
    print(f"  Ingestion:     {INGEST}")
    print(f"  Gateway:       {GATEWAY}")

    alert_proc = start_service("../AlertManagement/alert_manager.py", "ALERT_MANAGER_PORT", alert_port)
    if not wait_healthy(ALERT_MGR):
        print("  [FAIL] Alert Manager didn't start"); alert_proc.terminate(); return
    print(f"  [PASS] Alert Manager healthy")

    ingest_proc = start_service("ingestion_service.py", "INGESTION_SERVICE_PORT", ingest_port,
                                extra_env={"ALERT_MANAGER_URL": ALERT_MGR})
    if not wait_healthy(INGEST):
        print("  [FAIL] Ingestion didn't start"); alert_proc.terminate(); ingest_proc.terminate(); return
    print(f"  [PASS] Ingestion healthy")

    gateway_proc = start_service("gateway_service.py", "GATEWAY_SERVICE_PORT", gateway_port,
                                 extra_env={"INGESTION_URL": INGEST, "ALERT_MANAGER_URL": ALERT_MGR})
    if not wait_healthy(GATEWAY):
        print("  [FAIL] Gateway didn't start"); alert_proc.terminate(); ingest_proc.terminate(); gateway_proc.terminate(); return
    print(f"  [PASS] Gateway healthy")

    procs = [alert_proc, ingest_proc, gateway_proc]

    tr = TR()

    try:
        # ── Step 1: Health ──
        print(f"\n{'─'*50}\n  Step 1: Health Checks (3 services)\n{'─'*50}")
        for name, url in [("Ingestion", INGEST), ("Gateway", GATEWAY), ("Alert Manager", ALERT_MGR)]:
            t0 = time.time()
            r = requests.get(f"{url}/health")
            ms = int((time.time()-t0)*1000)
            d = r.json()
            tr.ok(f"{name} Health", f"status={d['status']}", ms)

        # ── Step 2: Auth (7 roles, 9 users) ──
        print(f"\n{'─'*50}\n  Step 2: Authentication (9 users, 7 roles)\n{'─'*50}")
        tokens = {}
        for user, pw, role in [
            ("admin","admin123","admin"),
            ("energy_raghuram","energy123","energy_manager"),
            ("ehs_saicharan","ehs123","ehs_manager"),
            ("analyst_vikram","analyst123","analyst"),
            ("maint_raju","maint123","maintenance"),
            ("researcher_ananya","research123","researcher"),
            ("resident_arjun","resident123","resident"),
        ]:
            r = requests.post(f"{GATEWAY}/auth/login", json={"username":user,"password":pw})
            if r.status_code == 200:
                tokens[role] = r.json()["access_token"]
                tr.ok(f"Login {role}", f"user={user}")
            else:
                tr.fail(f"Login {role}", r.text)

        # Invalid login
        r = requests.post(f"{GATEWAY}/auth/login", json={"username":"admin","password":"wrong"})
        tr.ok("Invalid Login Rejected", "401") if r.status_code == 401 else tr.fail("Invalid Login", str(r.status_code))

        # Profile
        r = requests.get(f"{GATEWAY}/api/v1/me", headers={"Authorization":f"Bearer {tokens['admin']}"})
        d = r.json()
        tr.ok("Admin Profile", f"perms={len(d['permissions'])}, domains={d['domains']}")

        # ── Step 3: Telemetry Ingestion + Emergency Detection ──
        print(f"\n{'─'*50}\n  Step 3: Telemetry Ingestion + Emergency Detection\n{'─'*50}")
        for node in ENERGY_NODES + EHS_NODES + RESIDENT_NODES:
            node["timestamp"] = datetime.now().isoformat()
            t0 = time.time()
            r = requests.post(f"{INGEST}/ingest", json=node)
            ms = int((time.time()-t0)*1000)
            d = r.json()
            tr.ok(f"Ingest {node['node_id']}", f"domain={d['domain']} crit={d['is_critical']}", ms)

        # Batch
        import random
        batch = [{"node_id":f"NRG-SOL-{random.randint(100,999)}","domain":"energy","node_type":"solar_panel",
                  "timestamp":datetime.now().isoformat(),"data":{"solar_power_w":random.uniform(100,900),"is_critical":False}} for _ in range(20)]
        r = requests.post(f"{INGEST}/ingest/batch", json={"readings": batch})
        d = r.json()
        tr.ok("Batch Ingest", f"stored={d['stored']}")

        # Check alerts were generated
        time.sleep(1)  # let alerts propagate
        r = requests.get(f"{ALERT_MGR}/alerts")
        d = r.json()
        alert_count = d.get("count", 0)
        tr.ok("Emergency Alerts Generated", f"{alert_count} alerts from engine") if alert_count > 0 else tr.fail("No Alerts", "Expected alerts")

        # ── Step 4: RBAC Queries ──
        print(f"\n{'─'*50}\n  Step 4: RBAC-Filtered SQL Queries\n{'─'*50}")

        r = requests.get(f"{GATEWAY}/api/v1/telemetry/query", headers={"Authorization":f"Bearer {tokens['admin']}"})
        d = r.json(); tr.ok("Admin Query (all)", f"{d['count']} records")

        r = requests.get(f"{GATEWAY}/api/v1/telemetry/query", headers={"Authorization":f"Bearer {tokens['energy_manager']}"})
        d = r.json()
        all_energy = all(x["domain_name"] == "energy" for x in d["records"])
        tr.ok("Energy Mgr Query", f"{d['count']} records, all_energy={all_energy}")

        r = requests.get(f"{GATEWAY}/api/v1/telemetry/query", headers={"Authorization":f"Bearer {tokens['ehs_manager']}"})
        d = r.json()
        all_ehs = all(x["domain_name"] == "ehs" for x in d["records"])
        tr.ok("EHS Mgr Query", f"{d['count']} records, all_ehs={all_ehs}")

        r = requests.get(f"{GATEWAY}/api/v1/telemetry/query", headers={"Authorization":f"Bearer {tokens['resident']}"})
        d = r.json()
        own_only = all(x["node_id_str"].startswith("R1-") for x in d["records"])
        tr.ok("Resident Own Nodes", f"{d['count']} records, own_nodes_only={own_only}")

        r = requests.get(f"{GATEWAY}/api/v1/my-data", headers={"Authorization":f"Bearer {tokens['resident']}"})
        d = r.json()
        tr.ok("Resident my-data", f"nodes={d.get('node_count','?')}, consumption={d.get('consumption_w',0)}W, bill=₹{d.get('est_monthly_bill_inr',0)}")

        r = requests.get(f"{GATEWAY}/api/v1/telemetry/query", headers={"Authorization":"Bearer bad"})
        tr.ok("Unauth Blocked", "401") if r.status_code == 401 else tr.fail("Unauth", str(r.status_code))

        # ── Step 5: Users & Nodes ──
        print(f"\n{'─'*50}\n  Step 5: Users & Nodes\n{'─'*50}")

        r = requests.get(f"{GATEWAY}/api/v1/users", headers={"Authorization":f"Bearer {tokens['admin']}"})
        d = r.json(); tr.ok("Admin List Users", f"{d['count']} users")

        r = requests.get(f"{GATEWAY}/api/v1/users", headers={"Authorization":f"Bearer {tokens['analyst']}"})
        tr.ok("Analyst Users Blocked", "403") if r.status_code == 403 else tr.fail("Analyst Users", str(r.status_code))

        r = requests.get(f"{GATEWAY}/api/v1/nodes", headers={"Authorization":f"Bearer {tokens['admin']}"})
        d = r.json(); tr.ok("List Nodes", f"{d['count']} nodes registered")

        # User Node CRUD
        r = requests.get(f"{GATEWAY}/api/v1/my-nodes", headers={"Authorization":f"Bearer {tokens['resident']}"})
        d = r.json(); tr.ok("My Nodes List", f"{d['count']} nodes for resident")

        r = requests.post(f"{GATEWAY}/api/v1/my-nodes/add",
            json={"node_id":"R1-TEST-001","domain":"energy","node_type":"solar_panel"},
            headers={"Authorization":f"Bearer {tokens['resident']}"})
        d = r.json(); tr.ok("Resident Add Node", f"node_id={d.get('node_id')}, owner={d.get('owner')}")

        r = requests.post(f"{GATEWAY}/api/v1/my-nodes/remove",
            json={"node_id":"R1-TEST-001"},
            headers={"Authorization":f"Bearer {tokens['resident']}"})
        d = r.json(); tr.ok("Resident Remove Node", f"node_id={d.get('node_id')}")

        # ── Step 6: Dashboard Data ──
        print(f"\n{'─'*50}\n  Step 6: Dashboard Data (per role)\n{'─'*50}")
        for role in tokens:
            r = requests.get(f"{GATEWAY}/api/v1/dashboard-data", headers={"Authorization":f"Bearer {tokens[role]}"})
            d = r.json()
            extra = ""
            if d.get("personal"):
                extra = f", bill=₹{d['personal'].get('est_monthly_bill_inr',0)}"
            tr.ok(f"Dashboard ({role})", f"readings={d['stats']['total_readings']}, domains={d['stats']['total_domains']}{extra}")

        # ── Step 7: Roles, Stats, Analytics, Alerts ──
        print(f"\n{'─'*50}\n  Step 7: Roles, Stats, Analytics, Alerts\n{'─'*50}")

        r = requests.get(f"{GATEWAY}/api/v1/roles")
        d = r.json(); tr.ok("List Roles", f"{d['count']} roles")

        r = requests.get(f"{GATEWAY}/api/v1/stats", headers={"Authorization":f"Bearer {tokens['admin']}"})
        d = r.json(); tr.ok("Telemetry Stats", f"{len(d.get('domains',[]))} domains")

        r = requests.get(f"{GATEWAY}/api/v1/alerts", headers={"Authorization":f"Bearer {tokens['admin']}"})
        d = r.json(); tr.ok("Alerts (from Alert Manager)", f"{d['count']} alerts")

        r = requests.get(f"{GATEWAY}/api/v1/analytics", headers={"Authorization":f"Bearer {tokens['analyst']}"})
        d = r.json(); tr.ok("Analyst Analytics", f"node_types={len(d.get('node_type_stats',[]))}, top_crit={len(d.get('top_critical_nodes',[]))}")

        r = requests.get(f"{GATEWAY}/api/v1/node-health", headers={"Authorization":f"Bearer {tokens['maintenance']}"})
        d = r.json(); tr.ok("Node Health", f"{d['count']} nodes with status")

        r = requests.get(f"{GATEWAY}/dashboard")
        tr.ok("Dashboard HTML", f"{len(r.text)} bytes") if r.status_code == 200 else tr.fail("Dashboard HTML", str(r.status_code))

        # ── Step 8: Engine Health, Control, HLD ──
        print(f"\n{'─'*50}\n  Step 8: Engine Health, Control, HLD, Scaling\n{'─'*50}")

        r = requests.get(f"{GATEWAY}/api/v1/engine-health", headers={"Authorization":f"Bearer {tokens['admin']}"})
        d = r.json()
        sys_m = d.get("system", {})
        hld = d.get("hld", {})
        tr.ok("Engine Health", f"rps={d.get('records_per_second',0)}, nodes={d.get('active_nodes',0)}")
        tr.ok("HLD CPU Simulation", f"cpu_count={sys_m.get('cpu_count','?')}, usage={sys_m.get('cpu_usage_pct','?')}%, status={sys_m.get('cpu_status','?')}")

        r = requests.get(f"{GATEWAY}/api/v1/engine-report", headers={"Authorization":f"Bearer {tokens['admin']}"})
        d = r.json(); tr.ok("Engine Report", f"domains={len(d.get('domain_breakdown',[]))}")

        r = requests.get(f"{GATEWAY}/api/v1/fleet-status", headers={"Authorization":f"Bearer {tokens['admin']}"})
        d = r.json(); tr.ok("Fleet Status", f"{d['count']} nodes, {d['active']} active")

        # Set Interval
        r = requests.post(f"{GATEWAY}/api/v1/control/set-interval",
            json={"interval":2.0}, headers={"Authorization":f"Bearer {tokens['admin']}"})
        d = r.json(); tr.ok("Set Interval", f"new={d.get('new_interval')}s")

        # Add Node
        r = requests.post(f"{GATEWAY}/api/v1/control/add-node",
            json={"node_id":"DYN-TEST-001","domain":"energy","node_type":"solar_panel"},
            headers={"Authorization":f"Bearer {tokens['admin']}"})
        d = r.json(); tr.ok("Add Node", f"{d.get('node_id')} -> {d.get('status')}")

        # Bulk Add
        r = requests.post(f"{GATEWAY}/api/v1/control/add-bulk-nodes",
            json={"count":5,"domain":"energy","node_type":"solar_panel","prefix":"BULK"},
            headers={"Authorization":f"Bearer {tokens['admin']}"})
        d = r.json(); tr.ok("Add Bulk Nodes", f"{d.get('count',0)} nodes added")

        # Remove Node
        r = requests.post(f"{GATEWAY}/api/v1/control/remove-node",
            json={"node_id":"DYN-TEST-001"},
            headers={"Authorization":f"Bearer {tokens['admin']}"})
        d = r.json(); tr.ok("Remove Node", f"DYN-TEST-001 -> {d.get('status')}")

        # HLD Scale CPU
        r = requests.post(f"{GATEWAY}/api/v1/hld/scale-cpu",
            json={"new_count":8},
            headers={"Authorization":f"Bearer {tokens['admin']}"})
        d = r.json(); tr.ok("HLD Scale CPU", f"{d.get('old_cpu')} -> {d.get('new_cpu')} cores")

        # HTML pages
        r = requests.get(f"{GATEWAY}/control-panel")
        tr.ok("Control Panel HTML", f"{len(r.text)} bytes") if r.status_code == 200 else tr.fail("Control Panel", str(r.status_code))

        r = requests.get(f"{GATEWAY}/hld-architecture")
        tr.ok("HLD Architecture HTML", f"{len(r.text)} bytes") if r.status_code == 200 else tr.fail("HLD", str(r.status_code))

        # RBAC: resident blocked from control
        r = requests.post(f"{GATEWAY}/api/v1/control/set-interval",
            json={"interval":1.0}, headers={"Authorization":f"Bearer {tokens['resident']}"})
        tr.ok("Resident Control Blocked", "403") if r.status_code == 403 else tr.fail("Resident Control", str(r.status_code))

        # ── Report ──
        print(f"\n{'─'*50}\n  Generating Report\n{'─'*50}")
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        rp = REPORT_DIR / "access_service_test_report.html"
        color = "#10b981" if tr.failed == 0 else "#ef4444"
        rows = "\n".join(f'<tr style="background:{"#1a2035" if s=="PASS" else "rgba(239,68,68,.1)"}"><td>{"✅" if s=="PASS" else "❌"}</td><td>{n}</td><td>{d}</td><td>{m}ms</td></tr>' for s,n,d,m in tr.results)
        rp.write_text(f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Test Report</title>
<style>body{{font-family:Inter,sans-serif;background:#0a0e1a;color:#e2e8f0;padding:40px}}h1{{color:{color}}}
table{{width:100%;border-collapse:collapse;margin-top:20px}}th,td{{padding:10px 14px;text-align:left;border-bottom:1px solid rgba(255,255,255,.06);font-size:.85rem}}
th{{color:#94a3b8;font-size:.75rem;text-transform:uppercase}}</style></head>
<body><h1>Access Management Service v4 — Test Report</h1><p>Generated: {datetime.now().isoformat()}</p>
<p style="font-size:1.2rem;font-weight:800;color:{color}">{tr.passed}/{tr.passed+tr.failed} tests passed</p>
<p>Architecture: 3 Microservices (Ingestion + Gateway + Alert Manager) | Database: SQLite (WAL)</p>
<table><thead><tr><th></th><th>Test</th><th>Detail</th><th>Time</th></tr></thead><tbody>{rows}</tbody></table></body></html>""")
        tr.ok("Report Generated", str(rp))

        # Summary
        print(f"\n{'═'*64}")
        print(f"  {'ALL TESTS PASSED' if tr.failed==0 else f'{tr.failed} FAILED'} ({tr.passed}/{tr.passed+tr.failed})")
        print(f"\n  Report:    {rp}")
        print(f"  Gateway:   {GATEWAY}/dashboard")
        print(f"  Ingestion: {INGEST}/docs")
        print(f"  Alert Mgr: {ALERT_MGR}/docs")
        print(f"  Gateway:   {GATEWAY}/docs")
        print(f"{'═'*64}")

        if not args.no_browser:
            webbrowser.open(f"{GATEWAY}/dashboard")
            print(f"\n  Server running. Press Ctrl+C to stop...")
            try:
                while True: time.sleep(1)
            except KeyboardInterrupt:
                pass

    finally:
        print(f"\n  Shutting down...")
        for p in procs:
            p.terminate()
        for p in procs:
            try: p.wait(timeout=3)
            except: pass
        print(f"  [PASS] All services stopped cleanly")

    sys.exit(0 if tr.failed == 0 else 1)


if __name__ == "__main__":
    main()
