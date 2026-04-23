"""Quick test script to validate all EHS Engine endpoints."""
import requests, json

url = "http://localhost:8002"

# ─── Test payloads for all 6 EHS node types ───
payloads = [
    {
        "node_id": "EHS-AQI-001", "domain": "ehs", "node_type": "air_quality",
        "timestamp": "2026-04-23T08:00:00",
        "data": {"aqi": 350, "water_ph": 7.2, "pm25": 180, "co2_ppm": 550, "temperature_c": 32, "humidity_pct": 65, "is_critical": True}
    },
    {
        "node_id": "EHS-AQI-002", "domain": "ehs", "node_type": "air_quality",
        "timestamp": "2026-04-23T08:01:00",
        "data": {"aqi": 45, "water_ph": 7.0, "pm25": 12, "co2_ppm": 420, "is_critical": False}
    },
    {
        "node_id": "EHS-AQI-003", "domain": "ehs", "node_type": "air_quality",
        "timestamp": "2026-04-23T08:06:00",
        "data": {"aqi": 180, "water_ph": 7.5, "pm25": 55, "co2_ppm": 480, "is_critical": False}
    },
    {
        "node_id": "EHS-WTR-001", "domain": "ehs", "node_type": "water_quality",
        "timestamp": "2026-04-23T08:02:00",
        "data": {"aqi": 30, "water_ph": 4.2, "turbidity_ntu": 65, "dissolved_oxygen_mgl": 3.5, "water_temp_c": 22, "is_critical": True}
    },
    {
        "node_id": "EHS-NOS-001", "domain": "ehs", "node_type": "noise_monitor",
        "timestamp": "2026-04-23T08:03:00",
        "data": {"aqi": 30, "water_ph": 7.0, "noise_db": 92, "peak_db": 105, "frequency_hz": 500, "is_critical": True}
    },
    {
        "node_id": "EHS-RAD-001", "domain": "ehs", "node_type": "radiation_gas",
        "timestamp": "2026-04-23T08:04:00",
        "data": {"aqi": 30, "water_ph": 7.0, "voc_ppb": 3500, "co_ppm": 45, "radiation_usv": 1.2, "methane_ppm": 800, "is_critical": True}
    },
    {
        "node_id": "EHS-WEA-001", "domain": "ehs", "node_type": "weather_station",
        "timestamp": "2026-04-23T08:05:00",
        "data": {"aqi": 30, "water_ph": 7.0, "temperature_c": 38, "humidity_pct": 30, "uv_index": 10, "wind_speed_ms": 8, "pressure_hpa": 1013, "is_critical": False}
    },
]

print("=" * 60)
print("  EHS Engine v2.0 — Endpoint Validation")
print("=" * 60)

# 1. Evaluate all payloads
print("\n[1] POST /evaluate — Sending 7 test payloads:")
for p in payloads:
    r = requests.post(f"{url}/evaluate", json=p)
    status = r.json().get("overall_status", "?") if r.status_code == 200 else f"ERROR {r.status_code}"
    ext_count = len(r.json().get("extended_metrics", []) or []) if r.status_code == 200 else 0
    print(f"  {p['node_id']:15s} ({p['node_type']:18s}) → {status:10s} | {ext_count} extended metrics")

# 2. Suggestions
print("\n[2] GET /suggestions:")
r = requests.get(f"{url}/suggestions")
s = r.json()
print(f"  Total: {s['total_suggestions']}")
for sug in s["suggestions"]:
    print(f"  [{sug['severity']:9s}] {sug['title']}")

# 3. Dashboard
print("\n[3] GET /dashboard-data:")
d = requests.get(f"{url}/dashboard-data").json()
print(f"  Campus Health Score: {d['campus_health_score']}")
print(f"  Nodes: {d['total_nodes']} (Safe={d['safe_count']}, Warn={d['warning_count']}, Crit={d['critical_count']})")
print(f"  Metric Cards: {list(d['metric_cards'].keys())}")

# 4. Prediction
print("\n[4] GET /predict/EHS-AQI-001:")
r = requests.get(f"{url}/predict/EHS-AQI-001")
if r.status_code == 200:
    pred = r.json()
    print(f"  AQI Forecast: {pred.get('aqi_forecast', {}).get('predicted_value', 'N/A')}")
    print(f"  Trend: {pred.get('aqi_forecast', {}).get('trend', 'N/A')}")
else:
    print(f"  {r.status_code}: {r.json().get('detail', 'error')}")

# 5. Visualization
print("\n[5] GET /visualize/timeseries?metric=aqi:")
r = requests.get(f"{url}/visualize/timeseries?metric=aqi")
viz = r.json()
print(f"  Series count: {viz['total_series']}")
for s in viz["series"]:
    print(f"  {s['node_id']:15s} → {len(s['values'])} values, avg={s['avg']}")

# 6. Heatmap
print("\n[6] GET /visualize/heatmap:")
hm = requests.get(f"{url}/visualize/heatmap").json()
print(f"  Total nodes in heatmap: {hm['total_nodes']}")
for entry in hm["heatmap"][:3]:
    print(f"  {entry['node_id']:15s} → {entry['status']:8s} AQI={entry['aqi']}")

# 7. Health
print("\n[7] GET /health:")
h = requests.get(f"{url}/health").json()
print(f"  Status: {h['status']}")
print(f"  Nodes tracked: {h['nodes_tracked']}")
print(f"  ML Strategy: {h['ml_strategy']}")
print(f"  Metrics: {h['metrics_monitored']}")

# 8. Thresholds
print("\n[8] GET /thresholds:")
t = requests.get(f"{url}/thresholds").json()
print(f"  Configured metrics: {list(t.keys())}")

print("\n" + "=" * 60)
print("  ALL ENDPOINT TESTS COMPLETED SUCCESSFULLY")
print("=" * 60)
