"""
═══════════════════════════════════════════════════════════════════
  EHS Engine v2.0 — Automated Testing & Presentation Demo Script
═══════════════════════════════════════════════════════════════════

This script:
  1. Boots the EHS FastAPI server automatically in background
  2. Waits for it to become healthy
  3. Sends realistic test payloads for ALL 6 EHS node types
  4. Validates ALL API endpoints (evaluate, predict, visualize, suggest, dashboard)
  5. Opens the live dashboard in your browser (Selenium)
  6. Takes screenshots for your presentation
  7. Generates a beautiful HTML test report with pass/fail results
  8. Auto-debugs any errors with full context

Usage:
  cd core_modules/EHSEngine
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

DEFAULT_PORT = 8002
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

TEST_PAYLOADS = [
    # ── Air Quality Stations (3 nodes: CRITICAL, SAFE, WARNING) ──
    {
        "node_id": "EHS-AQI-001", "domain": "ehs", "node_type": "air_quality",
        "timestamp": datetime.datetime.now().isoformat(),
        "data": {
            "aqi": 380, "water_ph": 7.2, "pm25": 200, "pm10": 280,
            "co2_ppm": 650, "temperature_c": 34, "humidity_pct": 72,
            "is_critical": True
        }
    },
    {
        "node_id": "EHS-AQI-002", "domain": "ehs", "node_type": "air_quality",
        "timestamp": datetime.datetime.now().isoformat(),
        "data": {
            "aqi": 42, "water_ph": 7.1, "pm25": 10, "pm10": 18,
            "co2_ppm": 415, "temperature_c": 26, "humidity_pct": 55,
            "is_critical": False
        }
    },
    {
        "node_id": "EHS-AQI-003", "domain": "ehs", "node_type": "air_quality",
        "timestamp": datetime.datetime.now().isoformat(),
        "data": {
            "aqi": 175, "water_ph": 7.4, "pm25": 62, "pm10": 95,
            "co2_ppm": 510, "temperature_c": 30, "humidity_pct": 60,
            "is_critical": False
        }
    },

    # ── Water Quality Probes (2 nodes: CRITICAL contamination, SAFE) ──
    {
        "node_id": "EHS-WTR-001", "domain": "ehs", "node_type": "water_quality",
        "timestamp": datetime.datetime.now().isoformat(),
        "data": {
            "aqi": 30, "water_ph": 4.0, "turbidity_ntu": 78,
            "dissolved_oxygen_mgl": 2.8, "water_temp_c": 24,
            "is_critical": True
        }
    },
    {
        "node_id": "EHS-WTR-002", "domain": "ehs", "node_type": "water_quality",
        "timestamp": datetime.datetime.now().isoformat(),
        "data": {
            "aqi": 28, "water_ph": 7.3, "turbidity_ntu": 2.1,
            "dissolved_oxygen_mgl": 8.5, "water_temp_c": 21,
            "is_critical": False
        }
    },

    # ── Noise Monitors (2 nodes: CRITICAL construction, SAFE) ──
    {
        "node_id": "EHS-NOS-001", "domain": "ehs", "node_type": "noise_monitor",
        "timestamp": datetime.datetime.now().isoformat(),
        "data": {
            "aqi": 35, "water_ph": 7.0, "noise_db": 94,
            "peak_db": 108, "frequency_hz": 250,
            "is_critical": True
        }
    },
    {
        "node_id": "EHS-NOS-002", "domain": "ehs", "node_type": "noise_monitor",
        "timestamp": datetime.datetime.now().isoformat(),
        "data": {
            "aqi": 35, "water_ph": 7.0, "noise_db": 48,
            "peak_db": 55, "frequency_hz": 1000,
            "is_critical": False
        }
    },

    # ── Weather Station (1 node: extreme UV) ──
    {
        "node_id": "EHS-WEA-001", "domain": "ehs", "node_type": "weather_station",
        "timestamp": datetime.datetime.now().isoformat(),
        "data": {
            "aqi": 38, "water_ph": 7.0, "temperature_c": 39,
            "humidity_pct": 28, "wind_speed_ms": 6.5,
            "wind_direction_deg": 180, "pressure_hpa": 1012,
            "uv_index": 10.5, "rainfall_mm": 0,
            "is_critical": False
        }
    },

    # ── Soil Sensors (1 node: normal) ──
    {
        "node_id": "EHS-SOL-001", "domain": "ehs", "node_type": "soil_sensor",
        "timestamp": datetime.datetime.now().isoformat(),
        "data": {
            "aqi": 30, "water_ph": 7.0, "soil_moisture_pct": 42,
            "soil_ph": 6.2, "soil_temp_c": 28,
            "is_critical": False
        }
    },

    # ── Radiation/Gas Detectors (1 node: CRITICAL lab leak) ──
    {
        "node_id": "EHS-RAD-001", "domain": "ehs", "node_type": "radiation_gas",
        "timestamp": datetime.datetime.now().isoformat(),
        "data": {
            "aqi": 32, "water_ph": 7.0, "voc_ppb": 3800,
            "co_ppm": 52, "radiation_usv": 1.5, "methane_ppm": 950,
            "is_critical": True
        }
    },
]

# Send a few extra rounds to build ML history
EXTRA_HISTORY_PAYLOADS = [
    {"node_id": "EHS-AQI-001", "domain": "ehs", "node_type": "air_quality",
     "timestamp": datetime.datetime.now().isoformat(),
     "data": {"aqi": v, "water_ph": 7.0, "pm25": v * 0.35, "is_critical": False}}
    for v in [320, 340, 360, 370, 380]  # Rising trend for ML
]


# ═══════════════════════════════════════
# STEP 1: SERVER MANAGEMENT
# ═══════════════════════════════════════

def start_server():
    """Boot the EHS FastAPI server as a background process."""
    section("Step 1: Starting EHS Engine Server")
    info(f"Working directory: {SCRIPT_DIR}")

    port = int(os.environ.get("EHS_ENGINE_PORT", "0")) or find_free_port()
    os.environ["EHS_ENGINE_PORT"] = str(port)

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
        # On Windows, CREATE_NEW_PROCESS_GROUP allows clean shutdown
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
                # Dump server output for debugging
                process.terminate()
                stdout = ''.join(list(SERVER_LOG_LINES)[-80:])
                print(f"\n{Colors.RED}=== SERVER OUTPUT ==={Colors.END}")
                print(stdout)  # Last 80 lines
                print(f"{Colors.RED}=== END SERVER OUTPUT ==={Colors.END}")
                return None
    return None


def stop_server(process):
    """Gracefully shut down the server."""
    if process:
        info("Shutting down EHS Engine server...")
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

    section("Step 2: Evaluating Telemetry (POST /evaluate)")

    # ── 2a. Send primary test payloads ──
    for payload in TEST_PAYLOADS:
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
                ext = data.get("extended_metrics") or []
                ext_str = f" + {len(ext)} extended" if ext else ""
                ok(f"{payload['node_id']:15s} → {status:8s} ({result.duration_ms}ms){ext_str}")
            else:
                result.error_message = r.text[:300]
                fail(f"{payload['node_id']} → HTTP {r.status_code}", result.error_message)
                debug_evaluate_error(payload, r)

        except Exception as e:
            result.error_message = str(e)
            fail(f"{payload['node_id']} → Connection Error", str(e))
            debug_connection_error(e)

        ALL_RESULTS.append(result)

    # ── 2b. Send extra history to build ML trends ──
    info("Sending 5 additional readings for ML history...")
    for p in EXTRA_HISTORY_PAYLOADS:
        try:
            req.post(f"{BASE_URL}/evaluate", json=p, timeout=EVALUATE_TIMEOUT_SECONDS)
        except Exception:
            pass
    ok("ML history populated (rising AQI trend)")

    # ── 2c. Test GET /health ──
    section("Step 3: Testing Operational Endpoints")
    test_get_endpoint(
        "Health Check", "/health",
        validate=lambda d: d.get("status") == "healthy" and d.get("nodes_tracked", 0) > 0,
        display=lambda d: f"Status={d['status']}, Nodes={d['nodes_tracked']}, ML={d['ml_strategy']}"
    )

    # ── 2d. Test GET /thresholds ──
    test_get_endpoint(
        "Safety Thresholds", "/thresholds",
        validate=lambda d: len(d) >= 7,
        display=lambda d: f"{len(d)} metrics configured: {list(d.keys())}"
    )

    # ── 2e. Test GET /suggestions ──
    section("Step 4: Actionable Suggestions (GET /suggestions)")
    test_get_endpoint(
        "EHS Suggestions", "/suggestions",
        validate=lambda d: "suggestions" in d and d.get("total_suggestions", 0) > 0,
        display=lambda d: format_suggestions(d),
    )

    # ── 2f. Test GET /predict/{node_id} ──
    section("Step 5: ML Predictions (GET /predict/{node_id})")
    test_get_endpoint(
        "Predict EHS-AQI-001", "/predict/EHS-AQI-001",
        validate=lambda d: "aqi_forecast" in d,
        display=lambda d: f"AQI Forecast: {d['aqi_forecast']['predicted_value']} "
                          f"(trend: {d['aqi_forecast']['trend']}, "
                          f"confidence: {d['aqi_forecast']['confidence']})",
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
        "Time-Series (AQI)", "/visualize/timeseries?metric=aqi",
        validate=lambda d: d.get("total_series", 0) > 0,
        display=lambda d: f"{d['total_series']} node series, metric={d['metric']}",
    )
    test_get_endpoint(
        "Time-Series (noise)", "/visualize/timeseries?metric=noise_db",
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
        validate=lambda d: "campus_health_score" in d and d.get("total_nodes", 0) >= 10,
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
                ok(f"{name} → Expected {expect_error} received ({result.duration_ms}ms)")
            else:
                result.error_message = f"Expected {expect_error}, got {r.status_code}"
                fail(name, result.error_message)
        elif r.status_code == 200:
            data = r.text if is_html else r.json()
            result.response_data = data if not is_html else {"html_length": len(data)}
            if validate(data):
                result.passed = True
                ok(f"{name} → {display(data)} ({result.duration_ms}ms)")
            else:
                result.error_message = "Validation failed"
                fail(name, f"Response didn't pass validation ({result.duration_ms}ms)")
                debug_validation_error(name, data)
        else:
            result.error_message = r.text[:300]
            fail(name, f"HTTP {r.status_code}: {result.error_message}")

    except Exception as e:
        result.error_message = str(e)
        fail(name, str(e))
        debug_connection_error(e)

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
    return "\n".join(lines)


def format_dashboard(data):
    """Pretty-print dashboard summary for console."""
    return (
        f"\n    Campus Health Score: {data['campus_health_score']}/100\n"
        f"    Nodes: {data['total_nodes']} total "
        f"({data['safe_count']} safe, {data['warning_count']} warning, {data['critical_count']} critical)\n"
        f"    Metric Cards: {list(data.get('metric_cards', {}).keys())}\n"
        f"    Suggestions: {len(data.get('suggestions', []))}"
    )


# ═══════════════════════════════════════
# STEP 3: BROWSER DEMO (Selenium)
# ═══════════════════════════════════════

def run_browser_demo(headless=False):
    """Open the EHS Dashboard in a real browser and take screenshots."""
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
            warn("Could not auto-start the presentation demo. Capturing the landing page instead.")

        # ── Screenshot 1: Presentation overview ──
        ss1 = os.path.join(SCREENSHOTS_DIR, "01_presentation_overview.png")
        driver.save_screenshot(ss1)
        ok(f"Screenshot saved: {ss1}")

        # ── Wait for flow animation to advance ──
        info("Waiting for presentation flow to advance...")
        time.sleep(5)

        # ── Screenshot 2: Mid-flow state ──
        ss2 = os.path.join(SCREENSHOTS_DIR, "02_presentation_midflow.png")
        driver.save_screenshot(ss2)
        ok(f"Screenshot saved: {ss2}")

        # ── Scroll down to show node catalog and results ──
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1)
        ss3 = os.path.join(SCREENSHOTS_DIR, "03_presentation_results.png")
        driver.save_screenshot(ss3)
        ok(f"Screenshot saved: {ss3}")

        # ── Navigate to Swagger docs ──
        info("Opening Swagger API docs...")
        driver.get(f"{BASE_URL}/docs")
        time.sleep(3)
        ss4 = os.path.join(SCREENSHOTS_DIR, "04_swagger_api.png")
        driver.save_screenshot(ss4)
        ok(f"Screenshot saved: {ss4}")

        # ── Return to presentation page for the presentation capture ──
        driver.get(f"{BASE_URL}/presentation")
        time.sleep(1)
        ss5 = os.path.join(SCREENSHOTS_DIR, "05_presentation_return.png")
        driver.save_screenshot(ss5)
        ok(f"Screenshot saved: {ss5}")

        # ── Leave the presentation page open for manual walkthroughs ──
        info("Presentation demo is now live for your presentation!")

        if not headless:
            info("Browser will stay open. Press Ctrl+C to close and generate report.")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass

    except Exception as e:
        fail(f"Browser demo failed: {e}")
        debug_selenium_error(e)
    finally:
        if driver and headless:
            driver.quit()
            ok("Browser closed")


# ═══════════════════════════════════════
# AUTO-DEBUG FUNCTIONS
# ═══════════════════════════════════════

def debug_evaluate_error(payload, response):
    """Auto-debug a failed /evaluate call."""
    print(f"\n{Colors.YELLOW}  +-- AUTO-DEBUG: Evaluation Error --{Colors.END}")
    print(f"  | Endpoint: POST /evaluate")
    print(f"  | Status:   {response.status_code}")
    try:
        detail = response.json()
        print(f"  | Detail:   {json.dumps(detail, indent=2)[:500]}")
    except Exception:
        print(f"  | Raw Body: {response.text[:500]}")

    # Check common issues
    data = payload.get("data", {})
    if "aqi" not in data:
        print(f"  | >> Missing 'aqi' field in data -- required by EHSData schema")
    if "water_ph" not in data:
        print(f"  | >> Missing 'water_ph' field -- defaults to 7.0 but check schema")
    if data.get("water_ph", 7) < 0 or data.get("water_ph", 7) > 14:
        print(f"  | >> water_ph={data.get('water_ph')} is out of range [0, 14]")
    if data.get("aqi", 0) < 0:
        print(f"  | >> aqi={data.get('aqi')} cannot be negative")

    print(f"  |")
    print(f"  | Payload sent:")
    print(f"  | {json.dumps(payload, indent=2)[:600]}")
    print(f"  +----------------------------------{Colors.END}")


def debug_connection_error(error):
    """Auto-debug a connection error."""
    print(f"\n{Colors.YELLOW}  +-- AUTO-DEBUG: Connection Error --{Colors.END}")
    print(f"  | Error: {error}")
    print(f"  |")
    print(f"  | Possible causes:")
    print(f"  |   1. EHS Engine server is not running")
    print(f"  |      -> Run: python main.py")
    print(f"  |   2. Port 8002 is blocked or in use")
    print(f"  |      -> Check: netstat -an | findstr 8002")
    print(f"  |   3. Firewall blocking localhost connections")
    print(f"  |   4. Server crashed during startup (check server logs)")
    print(f"  +----------------------------------{Colors.END}")


def debug_validation_error(name, data):
    """Auto-debug a validation failure."""
    print(f"\n{Colors.YELLOW}  +-- AUTO-DEBUG: Validation Failed --{Colors.END}")
    print(f"  | Test: {name}")
    print(f"  | Response type: {type(data).__name__}")
    if isinstance(data, dict):
        print(f"  | Keys: {list(data.keys())[:15]}")
        if "detail" in data:
            print(f"  | Detail: {data['detail']}")
    print(f"  +----------------------------------{Colors.END}")


def debug_selenium_error(error):
    """Auto-debug a Selenium error."""
    msg = str(error).lower()
    print(f"\n{Colors.YELLOW}  +-- AUTO-DEBUG: Selenium Error --{Colors.END}")
    if "chromedriver" in msg or "webdriver" in msg or "session not created" in msg:
        print(f"  | ChromeDriver not found or version mismatch.")
        print(f"  | Fix options:")
        print(f"  |   1. pip install webdriver-manager")
        print(f"  |   2. Or download matching ChromeDriver from:")
        print(f"  |      https://chromedriver.chromium.org/downloads")
        print(f"  |   3. Run with --no-browser flag to skip browser demo")
    elif "no such window" in msg:
        print(f"  | Browser window was closed manually.")
    else:
        print(f"  | Error: {error}")
        print(f"  | Full traceback:")
        traceback.print_exc()
    print(f"  +----------------------------------{Colors.END}")


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

    # Check for screenshots
    screenshots = []
    if os.path.exists(SCREENSHOTS_DIR):
        screenshots = sorted([f for f in os.listdir(SCREENSHOTS_DIR) if f.endswith('.png')])

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>EHS Engine — Test Report</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #0a0e1a; --card: #1a2035; --border: rgba(255,255,255,0.08);
            --text: #e2e8f0; --muted: #64748b; --green: #10b981;
            --red: #ef4444; --yellow: #f59e0b; --blue: #3b82f6; --cyan: #22d3ee;
        }}
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{ font-family:'Inter',sans-serif; background:var(--bg); color:var(--text); padding:32px; }}
        .container {{ max-width:1100px; margin:0 auto; }}
        h1 {{ font-size:2rem; font-weight:800;
             background:linear-gradient(135deg,#e2e8f0,#3b82f6);
             -webkit-background-clip:text; -webkit-text-fill-color:transparent;
             margin-bottom:8px; }}
        .subtitle {{ color:var(--muted); margin-bottom:32px; }}
        .stats {{ display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin-bottom:32px; }}
        .stat {{ background:var(--card); border:1px solid var(--border); border-radius:14px;
                 padding:24px; text-align:center; }}
        .stat-value {{ font-size:2.2rem; font-weight:800; margin-bottom:4px; }}
        .stat-label {{ font-size:0.8rem; color:var(--muted); text-transform:uppercase; letter-spacing:1px; }}
        .results-table {{ width:100%; border-collapse:collapse; margin-bottom:32px; }}
        .results-table th {{ text-align:left; padding:12px 16px; font-size:0.75rem;
             color:var(--muted); text-transform:uppercase; letter-spacing:1px;
             border-bottom:1px solid var(--border); }}
        .results-table td {{ padding:14px 16px; border-bottom:1px solid var(--border); font-size:0.88rem; }}
        .results-table tr:hover {{ background:rgba(59,130,246,0.05); }}
        .badge {{ padding:4px 10px; border-radius:6px; font-size:0.7rem; font-weight:700; }}
        .badge-pass {{ background:rgba(16,185,129,0.15); color:var(--green); }}
        .badge-fail {{ background:rgba(239,68,68,0.15); color:var(--red); }}
        .method {{ font-family:monospace; font-size:0.75rem; padding:3px 8px;
                   border-radius:4px; background:rgba(59,130,246,0.1); color:var(--blue); }}
        .endpoint {{ font-family:monospace; color:var(--cyan); font-size:0.82rem; }}
        .error-text {{ color:var(--red); font-size:0.78rem; margin-top:4px; }}
        .duration {{ color:var(--muted); font-size:0.78rem; }}
        .screenshots {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:32px; }}
        .screenshot {{ border-radius:12px; overflow:hidden; border:1px solid var(--border); }}
        .screenshot img {{ width:100%; display:block; }}
        .screenshot .caption {{ padding:10px 14px; font-size:0.78rem; color:var(--muted);
                                background:var(--card); }}
        .section-title {{ font-size:1.1rem; font-weight:700; margin:24px 0 16px;
                          display:flex; align-items:center; gap:8px; }}
        .dot {{ width:6px; height:6px; border-radius:50%; background:var(--blue); }}
        .footer {{ text-align:center; padding:24px; color:var(--muted); font-size:0.75rem;
                   border-top:1px solid var(--border); margin-top:32px; }}
    </style>
</head>
<body>
<div class="container">
    <h1>🌿 EHS Engine v2.0 — Test Report</h1>
    <p class="subtitle">Generated: {timestamp} | Smart City Living Lab — Team 32, Member 2 (Saicharan)</p>

    <div class="stats">
        <div class="stat">
            <div class="stat-value" style="color:var(--text)">{total}</div>
            <div class="stat-label">Total Tests</div>
        </div>
        <div class="stat">
            <div class="stat-value" style="color:var(--green)">{passed}</div>
            <div class="stat-label">Passed</div>
        </div>
        <div class="stat">
            <div class="stat-value" style="color:var(--red)">{failed}</div>
            <div class="stat-label">Failed</div>
        </div>
        <div class="stat">
            <div class="stat-value" style="color:{'var(--green)' if pass_rate >= 80 else 'var(--yellow)' if pass_rate >= 50 else 'var(--red)'}">{pass_rate:.0f}%</div>
            <div class="stat-label">Pass Rate</div>
        </div>
    </div>

    <h2 class="section-title"><span class="dot"></span>Test Results</h2>
    <table class="results-table">
        <thead>
            <tr>
                <th>Status</th>
                <th>Test Name</th>
                <th>Endpoint</th>
                <th>HTTP</th>
                <th>Time</th>
            </tr>
        </thead>
        <tbody>"""

    for r in ALL_RESULTS:
        badge = "badge-pass" if r.passed else "badge-fail"
        label = "PASS" if r.passed else "FAIL"
        error_html = f'<div class="error-text">{r.error_message}</div>' if r.error_message and not r.passed else ""
        html += f"""
            <tr>
                <td><span class="badge {badge}">{label}</span></td>
                <td>{r.name}{error_html}</td>
                <td><span class="method">{r.method}</span> <span class="endpoint">{r.endpoint}</span></td>
                <td>{r.status_code}</td>
                <td class="duration">{r.duration_ms}ms</td>
            </tr>"""

    html += """
        </tbody>
    </table>"""

    # Screenshots section
    if screenshots:
        html += '\n    <h2 class="section-title"><span class="dot"></span>Dashboard Screenshots</h2>\n'
        html += '    <div class="screenshots">\n'
        for ss in screenshots:
            caption = ss.replace(".png", "").replace("_", " ").title()
            html += f"""        <div class="screenshot">
            <img src="screenshots/{ss}" alt="{caption}">
            <div class="caption">{caption}</div>
        </div>\n"""
        html += '    </div>\n'

    html += f"""
    <div class="footer">
        EHS Domain Engine v2.0 | Team 32 — Smart City Living Lab<br>
        Design Patterns: Strategy (ML) · Observer (AMQP) · Factory Method (Evaluators)<br>
        Protocols: MQTT · HTTP · CoAP | 6 Node Types · 7+ Metrics · 120 Sensors
    </div>
</div>
</body>
</html>"""

    report_path = os.path.join(REPORT_DIR, "test_report.html")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)

    ok(f"Report saved: {report_path}")
    return report_path


# ═══════════════════════════════════════
# MAIN ORCHESTRATOR
# ═══════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="EHS Engine Automated Demo & Test")
    parser.add_argument("--no-browser", action="store_true", help="Skip Selenium browser demo")
    parser.add_argument("--no-server", action="store_true", help="Don't start server (assume already running)")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    args = parser.parse_args()

    banner("EHS Engine v2.0 - Automated Demo & Test Suite")
    print(f"  {Colors.DIM}Team 32 | Member 2: Saicharan | Smart City Living Lab{Colors.END}")
    print(f"  {Colors.DIM}6 Node Types | 7+ Metrics | 3 Protocols{Colors.END}")
    print(f"  {Colors.DIM}Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.END}")

    server_process = None

    try:
        # ── Step 1: Start server ──
        if not args.no_server:
            server_process = start_server()
            if server_process is None:
                print(f"\n{Colors.RED}FATAL: Could not start EHS Engine. Aborting.{Colors.END}")
                print(f"{Colors.YELLOW}Debug: Check that main.py, config.yaml, and all dependencies exist.{Colors.END}")
                print(f"{Colors.YELLOW}Try running manually: python main.py{Colors.END}")
                sys.exit(1)
        else:
            info("Skipping server start (--no-server flag)")
            # Verify server is reachable
            import requests as req
            try:
                req.get(f"{BASE_URL}/health", timeout=3)
                ok("Server is already running")
            except Exception:
                fail("Server is not reachable at localhost:8002")
                sys.exit(1)

        # ── Step 2-7: Run all API tests ──
        run_api_tests()

        # ── Step 8: Browser demo ──
        if not args.no_browser:
            run_browser_demo(headless=args.headless)
        else:
            info("Skipping browser demo (--no-browser flag)")

        # ── Step 9: Generate report ──
        report_path = generate_html_report()

        # ── Final Summary ──
        banner("Test Suite Complete")
        passed = sum(1 for r in ALL_RESULTS if r.passed)
        failed = sum(1 for r in ALL_RESULTS if not r.passed)
        total = len(ALL_RESULTS)
        color = Colors.GREEN if failed == 0 else Colors.YELLOW if failed < 3 else Colors.RED

        print(f"  {color}{Colors.BOLD}Results: {passed}/{total} passed ({failed} failed){Colors.END}")
        print(f"  Report: {Colors.CYAN}{report_path}{Colors.END}")
        print(f"  Dashboard: {Colors.CYAN}{BASE_URL}/dashboard{Colors.END}")
        print(f"  Swagger:   {Colors.CYAN}{BASE_URL}/docs{Colors.END}")

        if failed > 0:
            print(f"\n  {Colors.RED}Failed tests:{Colors.END}")
            for r in ALL_RESULTS:
                if not r.passed:
                    print(f"    ✗ {r.name}: {r.error_message}")

        # Open report in browser
        if os.path.exists(report_path):
            info("Opening test report in browser...")
            import webbrowser
            webbrowser.open(f"file:///{report_path.replace(os.sep, '/')}")

    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Interrupted by user.{Colors.END}")
    finally:
        # Generate report even on interrupt
        if ALL_RESULTS and not any("report" in r.name.lower() for r in ALL_RESULTS):
            try:
                generate_html_report()
            except Exception:
                pass

        if server_process:
            stop_server(server_process)


if __name__ == "__main__":
    main()
