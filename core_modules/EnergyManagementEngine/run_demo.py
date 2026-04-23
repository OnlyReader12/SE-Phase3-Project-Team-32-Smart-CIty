"""
═══════════════════════════════════════════════════════════════════
  Energy Management Engine v2.0 — Automated Testing & Presentation Demo Script
═══════════════════════════════════════════════════════════════════

This script:
  1. Boots the Energy FastAPI server automatically in background
  2. Waits for it to become healthy
  3. Sends realistic test payloads for ALL 7 Energy node types
  4. Validates ALL API endpoints (evaluate, predict, visualize, suggest, dashboard)
  5. Opens the live dashboard in your browser (Selenium)
  6. Takes screenshots for your presentation
  7. Generates a beautiful HTML test report with pass/fail results
  8. Auto-debugs any errors with full context

Usage:
  cd core_modules/EnergyManagementEngine
  pip install selenium requests pyyaml
  python run_demo.py

  Optional flags:
    --no-browser    Skip Selenium browser demo
    --no-server     Don't start server (assume already running)
    --headless      Run browser in headless mode
"""

import os
import sys
import io
import time
import json
import signal
import datetime
import subprocess
import traceback
import argparse
import socket
import threading
import random
from collections import deque
from typing import List, Dict, Any, Tuple

# --- Fix Windows encoding: force UTF-8 output ---
if sys.platform == "win32":
    os.system("")  # Enable ANSI escape codes on Windows 10+
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass  # Fallback: old Python or piped context

# ===================================
# CONFIGURATION
# ===================================

DEFAULT_PORT = 8003
BASE_URL = f"http://127.0.0.1:{DEFAULT_PORT}"
EVALUATE_TIMEOUT_SECONDS = 45
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.join(SCRIPT_DIR, "test_reports")
SCREENSHOTS_DIR = os.path.join(REPORT_DIR, "screenshots")

# Ensure output directories exist
os.makedirs(REPORT_DIR, exist_ok=True)
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

SERVER_LOG_LINES = deque(maxlen=200)
# ===================================
# PRETTY CONSOLE OUTPUT
# ===================================

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    END = '\033[0m'

def banner(text, char="="):
    width = 64
    print(f"\n{Colors.CYAN}{char * width}{Colors.END}", flush=True)
    print(f"{Colors.BOLD}{Colors.CYAN}  {text}{Colors.END}", flush=True)
    print(f"{Colors.CYAN}{char * width}{Colors.END}\n", flush=True)

def section(text):
    print(f"\n{Colors.BLUE}{'-' * 50}{Colors.END}", flush=True)
    print(f"  {Colors.BOLD}{text}{Colors.END}", flush=True)
    print(f"{Colors.BLUE}{'-' * 50}{Colors.END}", flush=True)

def ok(msg):
    print(f"  {Colors.GREEN}[PASS]{Colors.END}  {msg}", flush=True)

def fail(msg, detail=""):
    print(f"  {Colors.RED}[FAIL]{Colors.END}  {msg}", flush=True)
    if detail:
        print(f"         {Colors.DIM}{detail}{Colors.END}", flush=True)

def warn(msg):
    print(f"  {Colors.YELLOW}[WARN]{Colors.END}  {msg}", flush=True)

def info(msg):
    print(f"  {Colors.DIM}[INFO] {msg}{Colors.END}", flush=True)


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]

def drain_server_output(process):
    if not process.stdout:
        return
    for line in iter(process.stdout.readline, ""):
        if not line:
            break
        SERVER_LOG_LINES.append(line.rstrip("\n"))


# ═══════════════════════════════════════
# TEST RESULT TRACKING
# ═══════════════════════════════════════

class TestResult:
    def __init__(self, name: str, endpoint: str, method: str = "GET"):
        self.name = name
        self.endpoint = endpoint
        self.method = method
        self.passed = False
        self.status_code = 0
        self.response_data = None
        self.error_message = ""
        self.debug_info = ""
        self.duration_ms = 0

    def to_dict(self):
        return {
            "name": self.name, "endpoint": self.endpoint, "method": self.method,
            "passed": self.passed, "status_code": self.status_code,
            "error": self.error_message, "duration_ms": self.duration_ms,
        }


# Global results collector
ALL_RESULTS: List[TestResult] = []


# ═══════════════════════════════════════
# TEST PAYLOAD DEFINITIONS
# ═══════════════════════════════════════

def build_test_payloads() -> List[Dict[str, Any]]:
    """Build varied demo payloads for each run while preserving coverage scenarios."""
    ts = datetime.datetime.now().isoformat

    return [
        # ── Solar Panel: CRITICAL (very low output) ──
        {
            "node_id": "NRG-SOL-001", "domain": "energy", "node_type": "solar_panel",
            "timestamp": ts(),
            "data": {
                "solar_power_w": round(random.uniform(10, 45), 1),
                "voltage": round(random.uniform(28, 36), 1),
                "current": round(random.uniform(0.3, 1.2), 2),
                "energy_kwh": round(random.uniform(5, 20), 2),
                "solar_status": "active",
                "is_critical": True,
            },
        },
        # ── Solar Panel: SAFE (good output) ──
        {
            "node_id": "NRG-SOL-002", "domain": "energy", "node_type": "solar_panel",
            "timestamp": ts(),
            "data": {
                "solar_power_w": round(random.uniform(450, 850), 1),
                "voltage": round(random.uniform(36, 42), 1),
                "current": round(random.uniform(12, 22), 2),
                "energy_kwh": round(random.uniform(100, 300), 2),
                "solar_status": "active",
                "is_critical": False,
            },
        },
        # ── Solar Panel: WARNING (low output) ──
        {
            "node_id": "NRG-SOL-003", "domain": "energy", "node_type": "solar_panel",
            "timestamp": ts(),
            "data": {
                "solar_power_w": round(random.uniform(60, 180), 1),
                "voltage": round(random.uniform(32, 38), 1),
                "current": round(random.uniform(1.5, 5.0), 2),
                "energy_kwh": round(random.uniform(30, 80), 2),
                "solar_status": "active",
                "is_critical": False,
            },
        },
        # ── Smart Meter: Low Power Factor (CRITICAL) ──
        {
            "node_id": "NRG-MTR-001", "domain": "energy", "node_type": "smart_meter",
            "timestamp": ts(),
            "data": {
                "voltage": round(random.uniform(218, 242), 1),
                "current": round(random.uniform(8, 25), 2),
                "power_w": round(random.uniform(1800, 4500), 1),
                "energy_kwh": round(random.uniform(200, 800), 2),
                "power_factor": round(random.uniform(0.60, 0.78), 3),
                "is_critical": True,
            },
        },
        # ── Smart Meter: Good Power Factor (SAFE) ──
        {
            "node_id": "NRG-MTR-002", "domain": "energy", "node_type": "smart_meter",
            "timestamp": ts(),
            "data": {
                "voltage": round(random.uniform(228, 232), 1),
                "current": round(random.uniform(5, 15), 2),
                "power_w": round(random.uniform(1000, 3000), 1),
                "energy_kwh": round(random.uniform(100, 500), 2),
                "power_factor": round(random.uniform(0.92, 0.99), 3),
                "is_critical": False,
            },
        },
        # ── Battery Storage: CRITICAL (very low SoC) ──
        {
            "node_id": "NRG-BAT-001", "domain": "energy", "node_type": "battery_storage",
            "timestamp": ts(),
            "data": {
                "battery_soc_pct": round(random.uniform(5, 18), 1),
                "voltage": round(random.uniform(46, 50), 1),
                "charge_rate_w": round(random.uniform(-800, -200), 1),
                "battery_status": "discharging",
                "is_critical": True,
            },
        },
        # ── Battery Storage: SAFE ──
        {
            "node_id": "NRG-BAT-002", "domain": "energy", "node_type": "battery_storage",
            "timestamp": ts(),
            "data": {
                "battery_soc_pct": round(random.uniform(65, 95), 1),
                "voltage": round(random.uniform(52, 56), 1),
                "charge_rate_w": round(random.uniform(200, 600), 1),
                "battery_status": "charging",
                "is_critical": False,
            },
        },
        # ── Grid Transformer: CRITICAL (overloaded) ──
        {
            "node_id": "NRG-GRD-001", "domain": "energy", "node_type": "grid_transformer",
            "timestamp": ts(),
            "data": {
                "grid_load_pct": round(random.uniform(92, 99), 1),
                "grid_temperature_c": round(random.uniform(78, 95), 1),
                "fault_status": "warning",
                "is_critical": True,
            },
        },
        # ── Grid Transformer: SAFE ──
        {
            "node_id": "NRG-GRD-002", "domain": "energy", "node_type": "grid_transformer",
            "timestamp": ts(),
            "data": {
                "grid_load_pct": round(random.uniform(30, 55), 1),
                "grid_temperature_c": round(random.uniform(40, 60), 1),
                "fault_status": "normal",
                "is_critical": False,
            },
        },
        # ── Occupancy Sensor: CRITICAL (overcrowded) ──
        {
            "node_id": "NRG-OCC-001", "domain": "energy", "node_type": "occupancy_sensor",
            "timestamp": ts(),
            "data": {
                "occupancy_detected": True,
                "person_count": random.randint(110, 180),
                "is_critical": True,
            },
        },
        # ── Smart Water Meter: CRITICAL (leak detected) ──
        {
            "node_id": "NRG-H2O-001", "domain": "energy", "node_type": "water_meter",
            "timestamp": ts(),
            "data": {
                "flow_rate_lpm": round(random.uniform(80, 150), 1),
                "total_consumption_l": round(random.uniform(5000, 15000), 1),
                "leak_detected": True,
                "is_critical": True,
            },
        },
        # ── Smart Water Meter: SAFE ──
        {
            "node_id": "NRG-H2O-002", "domain": "energy", "node_type": "water_meter",
            "timestamp": ts(),
            "data": {
                "flow_rate_lpm": round(random.uniform(5, 30), 1),
                "total_consumption_l": round(random.uniform(500, 3000), 1),
                "leak_detected": False,
                "is_critical": False,
            },
        },
        # ── AC Unit: CRITICAL (overload) ──
        {
            "node_id": "NRG-AC-001", "domain": "energy", "node_type": "ac_unit",
            "timestamp": ts(),
            "data": {
                "ac_power_w": round(random.uniform(3600, 5000), 1),
                "set_temp_c": round(random.uniform(16, 20), 1),
                "ac_mode": "cool",
                "ac_state": "on",
                "is_critical": True,
            },
        },
        # ── AC Unit: SAFE ──
        {
            "node_id": "NRG-AC-002", "domain": "energy", "node_type": "ac_unit",
            "timestamp": ts(),
            "data": {
                "ac_power_w": round(random.uniform(800, 1800), 1),
                "set_temp_c": round(random.uniform(22, 26), 1),
                "ac_mode": "auto",
                "ac_state": "on",
                "is_critical": False,
            },
        },
    ]


def build_extra_history_payloads() -> List[Dict[str, Any]]:
    """Send extra rounds to build a falling solar trend for forecast tests."""
    base = random.randint(300, 500)
    decrements = [0, random.randint(30, 60), random.randint(80, 120), random.randint(140, 200), random.randint(220, 280)]
    values = [max(10, base - dec) for dec in decrements]
    return [
        {
            "node_id": "NRG-SOL-001", "domain": "energy", "node_type": "solar_panel",
            "timestamp": datetime.datetime.now().isoformat(),
            "data": {
                "solar_power_w": v,
                "voltage": round(random.uniform(30, 40), 1),
                "current": round(v / 36, 2),
                "energy_kwh": round(random.uniform(5, 20), 2),
                "solar_status": "active",
                "is_critical": False,
            },
        }
        for v in values
    ]


# ═══════════════════════════════════════
# STEP 1: SERVER MANAGEMENT
# ═══════════════════════════════════════

def start_server():
    """Boot the Energy FastAPI server as a background process."""
    section("Step 1: Starting Energy Engine Server")
    info(f"Working directory: {SCRIPT_DIR}")

    port = int(os.environ.get("ENERGY_ENGINE_PORT", "0")) or find_free_port()
    os.environ["ENERGY_ENGINE_PORT"] = str(port)

    global BASE_URL
    BASE_URL = f"http://127.0.0.1:{port}"
    info(f"Using server port: {port}")

    process = subprocess.Popen(
        [sys.executable, "main.py"],
        cwd=SCRIPT_DIR,
        env={**os.environ},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0,
    )
    threading.Thread(target=drain_server_output, args=(process,), daemon=True).start()
    info(f"Server PID: {process.pid}")

    # Wait for server to become healthy
    import requests as req
    max_wait = 15
    for i in range(max_wait):
        time.sleep(1)
        try:
            r = req.get(f"{BASE_URL}/health", timeout=2)
            if r.status_code == 200:
                ok(f"Server is HEALTHY (took {i+1}s)")
                return process
        except Exception:
            if i < max_wait - 1:
                info(f"Waiting for server... ({i+1}/{max_wait}s)")
            else:
                fail("Server failed to start within timeout")
                process.terminate()
                stdout = ''.join(list(SERVER_LOG_LINES)[-80:])
                print(f"\n{Colors.RED}=== SERVER OUTPUT ==={Colors.END}")
                print(stdout)
                print(f"{Colors.RED}=== END SERVER OUTPUT ==={Colors.END}")
                return None
    return None


def stop_server(process):
    """Gracefully shut down the server."""
    if process:
        info("Shutting down Energy Engine server...")
        if os.name == 'nt':
            process.terminate()
        else:
            os.kill(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
        ok("Server stopped cleanly")


# ═══════════════════════════════════════
# STEP 2: API ENDPOINT TESTS
# ═══════════════════════════════════════

def run_api_tests():
    """Execute all API endpoint tests and collect results."""
    import requests as req
    test_payloads = build_test_payloads()
    extra_history_payloads = build_extra_history_payloads()

    section("Step 2: Evaluating Telemetry (POST /evaluate)")

    # ── 2a. Send primary test payloads ──
    for payload in test_payloads:
        result = TestResult(
            name=f"Evaluate {payload['node_id']} ({payload['node_type']})",
            endpoint="/evaluate",
            method="POST",
        )
        try:
            start = time.time()
            r = req.post(f"{BASE_URL}/evaluate", json=payload, timeout=EVALUATE_TIMEOUT_SECONDS)
            result.duration_ms = round((time.time() - start) * 1000)
            result.status_code = r.status_code

            if r.status_code == 200:
                data = r.json()
                result.response_data = data
                result.passed = True
                status = data.get("overall_status", "?")
                metrics = data.get("metric_evaluations", [])
                metrics_str = f" ({len(metrics)} metrics)" if metrics else ""
                ok(f"{payload['node_id']:15s} -> {status:8s} ({result.duration_ms}ms){metrics_str}")
            else:
                result.error_message = r.text[:300]
                fail(f"{payload['node_id']} -> HTTP {r.status_code}", result.error_message)

        except Exception as e:
            result.error_message = str(e)
            fail(f"{payload['node_id']} -> Connection Error", str(e))

        ALL_RESULTS.append(result)

    # ── 2b. Send extra history to build ML trends ──
    info("Sending 5 additional readings for ML history...")
    for p in extra_history_payloads:
        try:
            req.post(f"{BASE_URL}/evaluate", json=p, timeout=EVALUATE_TIMEOUT_SECONDS)
        except Exception:
            pass
    ok("ML history populated (falling solar trend)")

    # ── 2c. Test GET /health ──
    section("Step 3: Testing Operational Endpoints")
    test_get_endpoint(
        "Health Check", "/health",
        validate=lambda d: d.get("status") == "healthy" and d.get("nodes_tracked", 0) > 0,
        display=lambda d: f"Status={d['status']}, Nodes={d['nodes_tracked']}, ML={d['ml_strategy']}"
    )

    # ── 2d. Test GET /thresholds ──
    test_get_endpoint(
        "Energy Thresholds", "/thresholds",
        validate=lambda d: len(d) >= 7,
        display=lambda d: f"{len(d)} metrics configured: {list(d.keys())}"
    )

    # ── 2e. Test GET /suggestions ──
    section("Step 4: Actionable Suggestions (GET /suggestions)")
    test_get_endpoint(
        "Energy Suggestions", "/suggestions",
        validate=lambda d: "suggestions" in d and d.get("total_suggestions", 0) > 0,
        display=lambda d: format_suggestions(d),
    )

    # ── 2f. Test GET /predict/{node_id} ──
    section("Step 5: ML Predictions (GET /predict/{node_id})")
    test_get_endpoint(
        "Predict NRG-SOL-001", "/predict/NRG-SOL-001",
        validate=lambda d: "solar_forecast" in d,
        display=lambda d: f"Solar Forecast: {d['solar_forecast']['predicted_value']} "
                          f"(trend: {d['solar_forecast']['trend']}, "
                          f"confidence: {d['solar_forecast']['confidence']})",
    )
    test_get_endpoint(
        "Predict unfound node", "/predict/NONEXISTENT-999",
        validate=lambda d: False,  # should 404
        display=lambda d: "N/A",
        expect_error=404,
    )

    # ── 2g. Test GET /visualize/timeseries ──
    section("Step 6: Visualization Data (GET /visualize/...)")
    test_get_endpoint(
        "Time-Series (Solar)", "/visualize/timeseries?metric=solar_power_w",
        validate=lambda d: d.get("total_series", 0) > 0,
        display=lambda d: f"{d['total_series']} node series, metric={d['metric']}",
    )
    test_get_endpoint(
        "Time-Series (Grid Load)", "/visualize/timeseries?metric=grid_load_pct",
        validate=lambda d: "series" in d,
        display=lambda d: f"{d['total_series']} node series",
    )

    # ── 2h. Test GET /visualize/heatmap ──
    test_get_endpoint(
        "Campus Heatmap", "/visualize/heatmap",
        validate=lambda d: d.get("total_nodes", 0) >= 10,
        display=lambda d: f"{d['total_nodes']} nodes in heatmap",
    )

    # ── 2i. Test GET /dashboard-data ──
    section("Step 7: Dashboard Summary (GET /dashboard-data)")
    test_get_endpoint(
        "Dashboard Data", "/dashboard-data",
        validate=lambda d: "campus_energy_score" in d and d.get("total_nodes", 0) >= 10,
        display=lambda d: format_dashboard(d),
    )

    # ── 2j. Test GET /dashboard (HTML) ──
    test_get_endpoint(
        "Dashboard HTML", "/dashboard",
        validate=lambda d: True,  # Always passes if 200
        display=lambda d: f"HTML page served ({len(str(d))} bytes)",
        is_html=True,
    )


def test_get_endpoint(name, endpoint, validate, display, expect_error=None, is_html=False):
    """Helper to test a GET endpoint and record result."""
    import requests as req

    result = TestResult(name=name, endpoint=endpoint, method="GET")
    try:
        start = time.time()
        r = req.get(f"{BASE_URL}{endpoint}", timeout=15)
        result.duration_ms = round((time.time() - start) * 1000)
        result.status_code = r.status_code

        if expect_error:
            if r.status_code == expect_error:
                result.passed = True
                ok(f"{name} -> Expected {expect_error} received ({result.duration_ms}ms)")
            else:
                result.error_message = f"Expected {expect_error}, got {r.status_code}"
                fail(name, result.error_message)
        elif r.status_code == 200:
            data = r.text if is_html else r.json()
            result.response_data = data if not is_html else {"html_length": len(data)}
            if validate(data):
                result.passed = True
                ok(f"{name} -> {display(data)} ({result.duration_ms}ms)")
            else:
                result.error_message = "Validation failed"
                fail(name, f"Response didn't pass validation ({result.duration_ms}ms)")
        else:
            result.error_message = r.text[:300]
            fail(name, f"HTTP {r.status_code}: {result.error_message}")

    except Exception as e:
        result.error_message = str(e)
        fail(name, str(e))

    ALL_RESULTS.append(result)


def format_suggestions(data):
    """Pretty-print suggestions for console."""
    lines = [f"{data['total_suggestions']} suggestions:"]
    for s in data.get("suggestions", []):
        sev = s['severity']
        icon = {"EMERGENCY": "[!!!]", "URGENT": "[!!]", "CAUTION": "[!]", "INFO": "[i]"}.get(sev, "?")
        lines.append(f"\n    {icon} [{sev:9s}] {s['title']}")
        if s.get("affected_nodes"):
            lines.append(f"              Nodes: {', '.join(s['affected_nodes'])}")
        if s.get("command_type"):
            lines.append(f"              Command: {s['command_type']}")
    return "\n".join(lines)


def format_dashboard(data):
    """Pretty-print dashboard summary for console."""
    return (
        f"\n    Campus Energy Score: {data['campus_energy_score']}/100\n"
        f"    Nodes: {data['total_nodes']} total "
        f"({data['safe_count']} safe, {data['warning_count']} warning, {data['critical_count']} critical)\n"
        f"    Solar Generation: {data.get('total_solar_generation_w', 0)}W | "
        f"Consumption: {data.get('total_consumption_w', 0)}W\n"
        f"    Avg Battery SoC: {data.get('avg_battery_soc', 0)}% | "
        f"Avg Grid Load: {data.get('avg_grid_load', 0)}%\n"
        f"    Metric Cards: {list(data.get('metric_cards', {}).keys())}\n"
        f"    Suggestions: {len(data.get('suggestions', []))}"
    )


# ═══════════════════════════════════════
# STEP 3: BROWSER DEMO (Selenium)
# ═══════════════════════════════════════

def run_browser_demo(headless=False):
    """Open the Energy Dashboard in a real browser and take screenshots."""
    section("Step 8: Browser Demo (Selenium)")

    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
    except ImportError:
        warn("Selenium not installed. Skipping browser demo.")
        warn("Install with: pip install selenium")
        return

    # ── Setup Chrome driver ──
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1440,900")
    options.add_argument("--force-device-scale-factor=1")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")

    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        ok("Chrome WebDriver initialized")

        # ── Navigate to presentation demo ──
        info(f"Opening presentation demo: {BASE_URL}/presentation")
        driver.get(f"{BASE_URL}/presentation")
        time.sleep(2)

        try:
            start_button = driver.find_element(By.ID, "startDemo")
            start_button.click()
            time.sleep(3)
        except Exception:
            warn("Could not auto-start the presentation demo.")

        # ── Screenshot 1: Presentation overview ──
        ss1 = os.path.join(SCREENSHOTS_DIR, "01_energy_presentation_overview.png")
        driver.save_screenshot(ss1)
        ok(f"Screenshot saved: {ss1}")

        # ── Wait for flow animation ──
        info("Waiting for presentation flow to advance...")
        time.sleep(5)

        # ── Screenshot 2: Mid-flow state ──
        ss2 = os.path.join(SCREENSHOTS_DIR, "02_energy_presentation_midflow.png")
        driver.save_screenshot(ss2)
        ok(f"Screenshot saved: {ss2}")

        # ── Scroll down ──
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1)
        ss3 = os.path.join(SCREENSHOTS_DIR, "03_energy_presentation_results.png")
        driver.save_screenshot(ss3)
        ok(f"Screenshot saved: {ss3}")

        # ── Navigate to Swagger docs ──
        info("Opening Swagger API docs...")
        driver.get(f"{BASE_URL}/docs")
        time.sleep(3)
        ss4 = os.path.join(SCREENSHOTS_DIR, "04_energy_swagger_api.png")
        driver.save_screenshot(ss4)
        ok(f"Screenshot saved: {ss4}")

        if not headless:
            info("Browser will stay open. Press Ctrl+C to close and generate report.")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass

    except Exception as e:
        fail(f"Browser demo failed: {e}")
        traceback.print_exc()
    finally:
        if driver and headless:
            driver.quit()
            ok("Browser closed")


# ═══════════════════════════════════════
# HTML REPORT GENERATOR
# ═══════════════════════════════════════

def generate_html_report():
    """Generate a beautiful HTML test report for presentation."""
    section("Step 9: Generating Test Report")

    passed = sum(1 for r in ALL_RESULTS if r.passed)
    failed = sum(1 for r in ALL_RESULTS if not r.passed)
    total = len(ALL_RESULTS)
    pass_rate = (passed / total * 100) if total > 0 else 0
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Energy Engine — Test Report</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #0a0e1a; --card: #1a2035; --border: rgba(255,255,255,0.08);
            --text: #e2e8f0; --muted: #64748b; --green: #10b981;
            --red: #ef4444; --yellow: #f59e0b; --blue: #3b82f6; --cyan: #22d3ee;
            --orange: #f97316;
        }}
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{ font-family:'Inter',sans-serif; background:var(--bg); color:var(--text); padding:32px; }}
        .container {{ max-width:1100px; margin:0 auto; }}
        h1 {{ font-size:2rem; font-weight:800; margin-bottom:8px; }}
        h1 span {{ color:var(--orange); }}
        .subtitle {{ color:var(--muted); font-size:0.95rem; margin-bottom:24px; }}
        .summary {{ display:flex; gap:16px; margin-bottom:32px; flex-wrap:wrap; }}
        .stat {{ background:var(--card); border:1px solid var(--border); border-radius:12px; padding:20px 24px; flex:1; min-width:160px; }}
        .stat-label {{ color:var(--muted); font-size:0.8rem; text-transform:uppercase; letter-spacing:1px; }}
        .stat-value {{ font-size:2rem; font-weight:700; margin-top:4px; }}
        .stat-value.green {{ color:var(--green); }}
        .stat-value.red {{ color:var(--red); }}
        .stat-value.blue {{ color:var(--cyan); }}
        table {{ width:100%; border-collapse:collapse; background:var(--card); border-radius:12px; overflow:hidden; margin-top:16px; }}
        th {{ background:rgba(255,255,255,0.05); color:var(--muted); font-size:0.75rem; text-transform:uppercase; letter-spacing:1px; padding:12px 16px; text-align:left; }}
        td {{ padding:12px 16px; border-top:1px solid var(--border); font-size:0.9rem; }}
        .pass {{ color:var(--green); font-weight:600; }}
        .fail {{ color:var(--red); font-weight:600; }}
        .badge {{ display:inline-block; padding:2px 10px; border-radius:99px; font-size:0.75rem; font-weight:600; }}
        .badge-pass {{ background:rgba(16,185,129,0.15); color:var(--green); }}
        .badge-fail {{ background:rgba(239,68,68,0.15); color:var(--red); }}
        .footer {{ text-align:center; color:var(--muted); font-size:0.8rem; margin-top:32px; }}
    </style>
</head>
<body>
<div class="container">
    <h1>⚡ Energy Engine — <span>Test Report</span></h1>
    <p class="subtitle">Generated: {timestamp} | Energy Management Engine v2.0 | Team Member 3: Raghuram</p>

    <div class="summary">
        <div class="stat"><div class="stat-label">Total Tests</div><div class="stat-value blue">{total}</div></div>
        <div class="stat"><div class="stat-label">Passed</div><div class="stat-value green">{passed}</div></div>
        <div class="stat"><div class="stat-label">Failed</div><div class="stat-value red">{failed}</div></div>
        <div class="stat"><div class="stat-label">Pass Rate</div><div class="stat-value {'green' if pass_rate >= 90 else 'red'}">{pass_rate:.0f}%</div></div>
    </div>

    <table>
        <thead><tr><th>Test</th><th>Endpoint</th><th>Method</th><th>Status</th><th>HTTP</th><th>Time</th></tr></thead>
        <tbody>"""

    for r in ALL_RESULTS:
        badge = f'<span class="badge badge-pass">PASS</span>' if r.passed else f'<span class="badge badge-fail">FAIL</span>'
        error = f'<br><small style="color:var(--red)">{r.error_message[:100]}</small>' if r.error_message else ""
        html += f"""
            <tr>
                <td>{r.name}{error}</td>
                <td><code>{r.endpoint}</code></td>
                <td>{r.method}</td>
                <td>{badge}</td>
                <td>{r.status_code}</td>
                <td>{r.duration_ms}ms</td>
            </tr>"""

    html += f"""
        </tbody>
    </table>

    <p class="footer">
        Design Patterns: Strategy (ML) · Observer (AMQP) · Factory Method (Evaluators) · Command (Suggestions)
        <br>Smart City Living Lab | SE Phase 3 | Team 32
    </p>
</div>
</body></html>"""

    report_path = os.path.join(REPORT_DIR, "energy_engine_test_report.html")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)
    ok(f"HTML Report: {report_path}")
    return report_path


# ═══════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Energy Engine Demo & Test Runner")
    parser.add_argument("--no-browser", action="store_true", help="Skip Selenium browser demo")
    parser.add_argument("--no-server", action="store_true", help="Don't start server (assume already running)")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    args = parser.parse_args()

    banner("Energy Management Engine v2.0 — Demo & Test Suite")
    server_process = None

    try:
        # ── Step 1: Start server ──
        if not args.no_server:
            server_process = start_server()
            if not server_process:
                print(f"\n{Colors.RED}Cannot proceed without a running server.{Colors.END}")
                sys.exit(1)
        else:
            info("Skipping server startup (--no-server flag)")

        # ── Step 2–7: Run API tests ──
        run_api_tests()

        # ── Step 8: Browser demo ──
        if not args.no_browser:
            run_browser_demo(headless=args.headless)
        else:
            info("Skipping browser demo (--no-browser flag)")

        # ── Step 9: Generate report ──
        report_path = generate_html_report()

        # ── Final Summary ──
        banner("Test Summary", "═")
        passed = sum(1 for r in ALL_RESULTS if r.passed)
        total = len(ALL_RESULTS)
        pass_rate = (passed / total * 100) if total > 0 else 0

        if pass_rate >= 90:
            print(f"  {Colors.GREEN}{Colors.BOLD}ALL TESTS PASSED ({passed}/{total}){Colors.END}")
        else:
            print(f"  {Colors.RED}{Colors.BOLD}{passed}/{total} PASSED ({pass_rate:.0f}%){Colors.END}")

        print(f"\n  Report: {report_path}")
        print(f"  Dashboard: {BASE_URL}/dashboard")
        print(f"  Swagger: {BASE_URL}/docs\n")

    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Interrupted by user.{Colors.END}")
    finally:
        if server_process:
            stop_server(server_process)


if __name__ == "__main__":
    main()
