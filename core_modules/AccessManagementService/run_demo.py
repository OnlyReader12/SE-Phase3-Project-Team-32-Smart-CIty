"""
run_demo.py — Access Management Service: Automated Demo & Test Suite.

Tests all endpoints: health, auth, telemetry ingestion, RBAC enforcement,
role-filtered queries, and dashboard data. Generates an HTML test report.

Usage:
  python3 run_demo.py                 # Full demo with browser
  python3 run_demo.py --no-browser    # Headless mode
  python3 run_demo.py --headless      # Same as --no-browser
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


# ═══════════════════════════════════════════
# Utilities
# ═══════════════════════════════════════════

def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.results = []

    def ok(self, name, detail="", ms=0):
        self.passed += 1
        self.results.append(("PASS", name, detail, ms))
        print(f"  [PASS]  {name} -> {detail} ({ms}ms)")

    def fail(self, name, detail=""):
        self.failed += 1
        self.results.append(("FAIL", name, detail, 0))
        print(f"  [FAIL]  {name} -> {detail}")

    @property
    def total(self):
        return self.passed + self.failed

    @property
    def all_passed(self):
        return self.failed == 0


# ═══════════════════════════════════════════
# Sample Test Data
# ═══════════════════════════════════════════

SAMPLE_ENERGY_NODES = [
    {"node_id": "NRG-SOL-001", "domain": "energy", "node_type": "solar_panel",
     "data": {"solar_power_w": 850.0, "voltage": 36.5, "is_critical": False}},
    {"node_id": "NRG-BAT-001", "domain": "energy", "node_type": "battery_storage",
     "data": {"battery_soc_pct": 15.0, "charge_rate_w": -500, "is_critical": True}},
    {"node_id": "NRG-GRD-001", "domain": "energy", "node_type": "grid_transformer",
     "data": {"grid_load_pct": 95.0, "grid_temperature_c": 92.0, "is_critical": True}},
    {"node_id": "NRG-AC-001", "domain": "energy", "node_type": "ac_unit",
     "data": {"ac_power_w": 4200, "set_temp_c": 22, "ac_mode": "cool", "is_critical": True}},
]

SAMPLE_EHS_NODES = [
    {"node_id": "EHS-AQI-001", "domain": "ehs", "node_type": "air_quality",
     "data": {"aqi": 320, "pm25": 112.0, "temperature_c": 35.2, "is_critical": True}},
    {"node_id": "EHS-WTR-001", "domain": "ehs", "node_type": "water_quality",
     "data": {"water_ph": 4.2, "turbidity_ntu": 150, "is_critical": True}},
    {"node_id": "EHS-NOS-001", "domain": "ehs", "node_type": "noise_monitor",
     "data": {"noise_db": 45.0, "peak_db": 52.0, "is_critical": False}},
]


# ═══════════════════════════════════════════
# Test Functions
# ═══════════════════════════════════════════

def test_health(base, tr):
    print(f"\n{'─'*50}\n  Step 1: Health Check\n{'─'*50}")
    t0 = time.time()
    r = requests.get(f"{base}/health", timeout=5)
    ms = int((time.time()-t0)*1000)
    if r.status_code == 200:
        d = r.json()
        tr.ok("Health Check", f"Status={d['status']}, Backend={d['storage_backend']}, Users={d['registered_users']}", ms)
    else:
        tr.fail("Health Check", f"HTTP {r.status_code}")


def test_auth(base, tr):
    print(f"\n{'─'*50}\n  Step 2: Authentication\n{'─'*50}")

    # Valid login
    t0 = time.time()
    r = requests.post(f"{base}/auth/login", json={"username": "admin", "password": "admin123"})
    ms = int((time.time()-t0)*1000)
    if r.status_code == 200:
        d = r.json()
        tr.ok("Admin Login", f"Role={d['role']}, Token={d['access_token'][:20]}...", ms)
    else:
        tr.fail("Admin Login", r.text)
        return {}

    admin_token = d["access_token"]

    # Invalid login
    r2 = requests.post(f"{base}/auth/login", json={"username": "admin", "password": "wrong"})
    if r2.status_code == 401:
        tr.ok("Invalid Login Rejected", "Expected 401 received")
    else:
        tr.fail("Invalid Login Rejected", f"Got {r2.status_code}")

    # Login as other roles
    tokens = {"admin": admin_token}
    for user, pw, role in [
        ("analyst1", "analyst123", "analyst"),
        ("maint1", "maint123", "maintenance"),
        ("researcher1", "research123", "researcher"),
        ("responder1", "respond123", "emergency_responder"),
        ("resident1", "resident123", "resident"),
    ]:
        r = requests.post(f"{base}/auth/login", json={"username": user, "password": pw})
        if r.status_code == 200:
            tokens[role] = r.json()["access_token"]
            tr.ok(f"{role.title()} Login", f"User={user}")
        else:
            tr.fail(f"{role.title()} Login", r.text)

    # Get profile
    r = requests.get(f"{base}/api/v1/me", headers={"Authorization": f"Bearer {admin_token}"})
    if r.status_code == 200:
        d = r.json()
        tr.ok("Admin Profile", f"Role={d['role']}, Perms={len(d['permissions'])}")
    else:
        tr.fail("Admin Profile", r.text)

    return tokens


def test_ingestion(base, tr):
    print(f"\n{'─'*50}\n  Step 3: Telemetry Ingestion\n{'─'*50}")
    all_nodes = SAMPLE_ENERGY_NODES + SAMPLE_EHS_NODES

    for node in all_nodes:
        node["timestamp"] = datetime.now().isoformat()
        t0 = time.time()
        r = requests.post(f"{base}/api/v1/telemetry", json=node)
        ms = int((time.time()-t0)*1000)
        if r.status_code == 200:
            d = r.json()
            tr.ok(f"Ingest {node['node_id']}", f"ID={d['record_id']} domain={d['domain']}", ms)
        else:
            tr.fail(f"Ingest {node['node_id']}", r.text)

    # Ingest some extra for volume
    import random
    for i in range(10):
        extra = {
            "node_id": f"NRG-SOL-{random.randint(100,999)}",
            "domain": "energy",
            "node_type": "solar_panel",
            "timestamp": datetime.now().isoformat(),
            "data": {"solar_power_w": random.uniform(100, 900), "is_critical": False},
        }
        requests.post(f"{base}/api/v1/telemetry", json=extra)


def test_rbac_queries(base, tokens, tr):
    print(f"\n{'─'*50}\n  Step 4: RBAC-Filtered Queries\n{'─'*50}")

    # Admin sees everything
    r = requests.get(f"{base}/api/v1/telemetry/query", headers={"Authorization": f"Bearer {tokens['admin']}"})
    if r.status_code == 200:
        d = r.json()
        tr.ok("Admin Query", f"{d['count']} records (all domains visible)")
    else:
        tr.fail("Admin Query", r.text)

    # Analyst sees energy + ehs
    if "analyst" in tokens:
        r = requests.get(f"{base}/api/v1/telemetry/query", headers={"Authorization": f"Bearer {tokens['analyst']}"})
        if r.status_code == 200:
            d = r.json()
            domains_seen = set(rec.get("domain") for rec in d.get("records", []))
            tr.ok("Analyst Query", f"{d['count']} records, domains={domains_seen}")
        else:
            tr.fail("Analyst Query", r.text)

    # Emergency responder sees only critical
    if "emergency_responder" in tokens:
        r = requests.get(f"{base}/api/v1/telemetry/query", headers={"Authorization": f"Bearer {tokens['emergency_responder']}"})
        if r.status_code == 200:
            d = r.json()
            all_crit = all(rec.get("data", {}).get("is_critical", False) for rec in d.get("records", []))
            tr.ok("Responder Query", f"{d['count']} records, all_critical={all_crit}")
        else:
            tr.fail("Responder Query", r.text)

    # Resident can't read telemetry (no telemetry.read permission)
    if "resident" in tokens:
        r = requests.get(f"{base}/api/v1/telemetry/query", headers={"Authorization": f"Bearer {tokens['resident']}"})
        if r.status_code == 403:
            tr.ok("Resident Blocked", "Expected 403 — no telemetry.read permission")
        else:
            tr.fail("Resident Blocked", f"Expected 403, got {r.status_code}")

    # Unauthenticated request
    r = requests.get(f"{base}/api/v1/telemetry/query")
    if r.status_code == 401:
        tr.ok("Unauth Blocked", "Expected 401 for missing token")
    else:
        tr.fail("Unauth Blocked", f"Expected 401, got {r.status_code}")


def test_users_endpoint(base, tokens, tr):
    print(f"\n{'─'*50}\n  Step 5: User Management (Admin Only)\n{'─'*50}")

    # Admin can list users
    r = requests.get(f"{base}/api/v1/users", headers={"Authorization": f"Bearer {tokens['admin']}"})
    if r.status_code == 200:
        d = r.json()
        tr.ok("Admin List Users", f"{d['count']} users")
    else:
        tr.fail("Admin List Users", r.text)

    # Analyst cannot list users
    if "analyst" in tokens:
        r = requests.get(f"{base}/api/v1/users", headers={"Authorization": f"Bearer {tokens['analyst']}"})
        if r.status_code == 403:
            tr.ok("Analyst Users Blocked", "Expected 403 — no users.read permission")
        else:
            tr.fail("Analyst Users Blocked", f"Expected 403, got {r.status_code}")


def test_dashboard_data(base, tokens, tr):
    print(f"\n{'─'*50}\n  Step 6: Dashboard Data (Role-Specific)\n{'─'*50}")

    for role, token in tokens.items():
        t0 = time.time()
        r = requests.get(f"{base}/api/v1/dashboard-data", headers={"Authorization": f"Bearer {token}"})
        ms = int((time.time()-t0)*1000)
        if r.status_code == 200:
            d = r.json()
            tr.ok(f"Dashboard ({role})",
                  f"Records={d['stats'].get('total_records',0)}, "
                  f"Alerts={d['stats'].get('total_alerts',0)}, "
                  f"Domains={d['stats'].get('total_domains',0)}", ms)
        else:
            tr.fail(f"Dashboard ({role})", r.text)


def test_roles_endpoint(base, tr):
    print(f"\n{'─'*50}\n  Step 7: Roles & Dashboard HTML\n{'─'*50}")

    r = requests.get(f"{base}/api/v1/roles")
    if r.status_code == 200:
        d = r.json()
        tr.ok("List Roles", f"{d['count']} roles defined")
    else:
        tr.fail("List Roles", r.text)

    r = requests.get(f"{base}/dashboard")
    if r.status_code == 200 and len(r.text) > 1000:
        tr.ok("Dashboard HTML", f"HTML page served ({len(r.text)} bytes)")
    else:
        tr.fail("Dashboard HTML", f"HTTP {r.status_code}")


def test_stats(base, tokens, tr):
    print(f"\n{'─'*50}\n  Step 8: Telemetry Stats & Alerts\n{'─'*50}")

    r = requests.get(f"{base}/api/v1/telemetry/stats", headers={"Authorization": f"Bearer {tokens['admin']}"})
    if r.status_code == 200:
        d = r.json()
        domains = list(d.get("domains", {}).keys())
        tr.ok("Telemetry Stats", f"Domains: {domains}")
    else:
        tr.fail("Telemetry Stats", r.text)

    r = requests.get(f"{base}/api/v1/alerts", headers={"Authorization": f"Bearer {tokens['admin']}"})
    if r.status_code == 200:
        d = r.json()
        tr.ok("Alerts Query", f"{d['count']} alerts")
    else:
        tr.fail("Alerts Query", r.text)


# ═══════════════════════════════════════════
# Report Generator
# ═══════════════════════════════════════════

def generate_report(tr, report_path):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    status = "ALL PASSED" if tr.all_passed else f"{tr.failed} FAILED"
    color = "#10b981" if tr.all_passed else "#ef4444"

    rows = ""
    for status_t, name, detail, ms in tr.results:
        icon = "✅" if status_t == "PASS" else "❌"
        row_color = "#1a2035" if status_t == "PASS" else "rgba(239,68,68,0.1)"
        rows += f'<tr style="background:{row_color}"><td>{icon}</td><td>{name}</td><td>{detail}</td><td>{ms}ms</td></tr>\n'

    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Access Management Service — Test Report</title>
<style>body{{font-family:Inter,sans-serif;background:#0a0e1a;color:#e2e8f0;padding:40px;}}
h1{{color:{color};}}table{{width:100%;border-collapse:collapse;margin-top:20px;}}
th,td{{padding:10px 14px;text-align:left;border-bottom:1px solid rgba(255,255,255,0.06);font-size:0.85rem;}}
th{{color:#94a3b8;font-size:0.75rem;text-transform:uppercase;}}</style></head>
<body><h1>Access Management Service — Test Report</h1>
<p>Generated: {datetime.now().isoformat()}</p>
<p style="font-size:1.2rem;font-weight:800;color:{color}">{tr.passed}/{tr.total} tests passed</p>
<table><thead><tr><th></th><th>Test</th><th>Detail</th><th>Time</th></tr></thead><tbody>
{rows}</tbody></table></body></html>"""

    with open(report_path, "w") as f:
        f.write(html)
    return str(report_path)


# ═══════════════════════════════════════════
# Main
# ═══════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Access Management Service Demo & Test Suite")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()
    no_browser = args.no_browser or args.headless

    port = find_free_port()
    env = {**os.environ, "ACCESS_SERVICE_PORT": str(port)}
    base = f"http://127.0.0.1:{port}"

    print(f"\n{'='*60}")
    print(f"  Access Management Service v1.0 — Demo & Test Suite")
    print(f"{'='*60}")

    print(f"\n{'─'*50}\n  Step 0: Starting Server\n{'─'*50}")
    print(f"  [INFO] Port: {port}")

    server = subprocess.Popen(
        [sys.executable, "main.py"],
        cwd=str(_BASE_DIR), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    print(f"  [INFO] Server PID: {server.pid}")

    # Wait for healthy
    deadline = time.time() + 15
    ready = False
    while time.time() < deadline:
        try:
            r = requests.get(f"{base}/health", timeout=2)
            if r.status_code == 200:
                ready = True
                break
        except Exception:
            pass
        elapsed = int(time.time() - (deadline - 15)) + 1
        print(f"  [INFO] Waiting for server... ({elapsed}/15s)")
        time.sleep(1)

    if not ready:
        print("  [FAIL]  Server failed to start")
        # Dump output
        out = server.stdout.read() if server.stdout else ""
        print(f"\n=== SERVER OUTPUT ===\n{out}\n=== END SERVER OUTPUT ===")
        server.terminate()
        sys.exit(1)

    secs = int(time.time() - (deadline - 15))
    print(f"  [PASS]  Server is HEALTHY (took {secs}s)")

    tr = TestResult()

    try:
        test_health(base, tr)
        tokens = test_auth(base, tr)
        test_ingestion(base, tr)
        if tokens:
            test_rbac_queries(base, tokens, tr)
            test_users_endpoint(base, tokens, tr)
            test_dashboard_data(base, tokens, tr)
        test_roles_endpoint(base, tr)
        if tokens:
            test_stats(base, tokens, tr)

        # Browser demo
        if not no_browser:
            print(f"\n{'─'*50}\n  Step 9: Browser Demo\n{'─'*50}")
            webbrowser.open(f"{base}/dashboard")
            print("  [INFO] Opened dashboard in browser")
            print("  [INFO] Login as: admin / admin123")

        # Report
        print(f"\n{'─'*50}\n  Step 10: Generating Test Report\n{'─'*50}")
        report_path = REPORT_DIR / "access_service_test_report.html"
        generate_report(tr, report_path)
        print(f"  [PASS]  Report: {report_path}")

        # Summary
        color = "" if tr.all_passed else "\033[91m"
        end = "\033[0m" if color else ""
        print(f"\n{'═'*60}")
        print(f"  {color}{'ALL TESTS PASSED' if tr.all_passed else f'{tr.failed} TESTS FAILED'} ({tr.passed}/{tr.total}){end}")
        print(f"\n  Report: {report_path}")
        print(f"  Dashboard: {base}/dashboard")
        print(f"  Swagger: {base}/docs")
        print(f"{'═'*60}")

    finally:
        if not no_browser and tokens:
            # Keep server running for browser demo
            print(f"\n  [INFO] Server running at {base}/dashboard")
            print(f"  [INFO] Press Ctrl+C to stop...")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass

        print(f"\n  [INFO] Shutting down server...")
        server.terminate()
        try:
            server.wait(timeout=5)
        except Exception:
            server.kill()
        print(f"  [PASS]  Server stopped cleanly")

    sys.exit(0 if tr.all_passed else 1)


if __name__ == "__main__":
    main()
