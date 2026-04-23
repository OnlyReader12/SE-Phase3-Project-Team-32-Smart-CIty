"""
iot_generator.py — Smart City IoT Data Generator (Expanded EHS Edition)

Simulates 300+ heterogeneous campus IoT nodes across all Smart City domains.
Each node type generates realistic telemetry using domain-appropriate value
ranges, spike probabilities, and diurnal curves.

EHS Node Types (120 nodes total):
  - Air Quality Stations  (EHS-AQI-xxx)  → MQTT  — AQI, PM2.5, PM10, CO2, temp, humidity
  - Water Quality Probes  (EHS-WTR-xxx)  → MQTT  — pH, turbidity, dissolved O2, water temp
  - Noise Level Monitors  (EHS-NOS-xxx)  → MQTT  — noise dB, peak dB, frequency
  - Weather Stations       (EHS-WEA-xxx)  → HTTP  — full weather suite
  - Soil Sensors           (EHS-SOL-xxx)  → CoAP  — soil moisture, pH, temp
  - Radiation/Gas Detectors(EHS-RAD-xxx)  → MQTT  — radiation, VOC, CO, methane

Energy Nodes (remaining):
  - Power Monitors         (PWR-NODE-xxx) → HTTP/MQTT — solar gen, AC consumption

Design Patterns:
  - Strategy Pattern: Protocol adapters (HTTP, MQTT, CoAP) are interchangeable
  - Factory/OOP: Each node type is a subclass of SimulatedNode
"""

import time
import json
import random
import math
import threading
import datetime
import os
import requests
import paho.mqtt.client as mqtt

# ==========================================
# 1. PROTOCOL ADAPTERS (Strategy Pattern)
# ==========================================

class ProtocolAdapter:
    """Abstract protocol adapter — all concrete adapters implement send()."""
    def send(self, payload):
        raise NotImplementedError


class HttpAdapter(ProtocolAdapter):
    """
    Simulates HTTP POST transmission to the Ingestion Engine.
    Used by: Weather Stations (AC-powered, full bandwidth).
    """
    def __init__(self, target_url="http://localhost:8000/api/telemetry"):
        self.target_url = target_url

    def send(self, payload):
        try:
            # Uncomment for live integration:
            # response = requests.post(self.target_url, json=payload, timeout=2)
            print(f"[HTTP POST] {payload['node_id']} → {payload.get('node_type', payload['domain'])}:\n"
                  f"  {json.dumps(payload['data'], indent=2)}\n")
        except Exception as e:
            print(f"[HTTP ERROR] Destination unreachable for {payload['node_id']}")


class MqttAdapter(ProtocolAdapter):
    """
    Simulates MQTT publish to the embedded broker.
    Used by: Air Quality, Water Quality, Noise, Radiation/Gas (battery-powered).
    """
    def __init__(self, broker="localhost", port=1883, topic="smartcity/telemetry"):
        self.broker = broker
        self.port = port
        self.topic = topic
        self.client = mqtt.Client()
        try:
            # Uncomment for live integration:
            # self.client.connect(self.broker, self.port)
            pass
        except Exception:
            pass

    def send(self, payload):
        try:
            merged_topic = f"{self.topic}/{payload['domain']}"
            # Uncomment for live integration:
            # self.client.publish(merged_topic, json.dumps(payload))
            print(f"[MQTT PUB] {payload['node_id']} → {merged_topic}:\n"
                  f"  {json.dumps(payload['data'], indent=2)}\n")
        except Exception as e:
            print(f"[MQTT ERROR] Broker unreachable for {payload['node_id']}")


class CoapAdapter(ProtocolAdapter):
    """
    Simulates CoAP (Constrained Application Protocol) transmission.
    Used by: Soil sensors — ultra-low-power, constrained devices.
    CoAP is a lightweight RESTful protocol designed for IoT devices
    with limited RAM and battery (RFC 7252).
    """
    def __init__(self, target_ip="localhost", port=5683):
        self.target_ip = target_ip
        self.port = port

    def send(self, payload):
        try:
            # In production, this would use aiocoap or coapthon3:
            # ctx = await aiocoap.Context.create_client_context()
            # request = aiocoap.Message(code=aiocoap.POST, payload=json.dumps(payload).encode())
            # request.set_request_uri(f"coap://{self.target_ip}:{self.port}/telemetry")
            print(f"[CoAP PUT] {payload['node_id']} → coap://{self.target_ip}:{self.port}/telemetry:\n"
                  f"  {json.dumps(payload['data'], indent=2)}\n")
        except Exception as e:
            print(f"[CoAP ERROR] Target unreachable for {payload['node_id']}")


# ==========================================
# 2. NODE DOMAIN DEFINITIONS
# ==========================================

class SimulatedNode:
    """Abstract base for all simulated IoT nodes."""
    def __init__(self, node_id, protocol_adapter):
        self.node_id = node_id
        self.protocol = protocol_adapter
        self.domain = "unknown"
        self.node_type = "unknown"
        seed = int.from_bytes(os.urandom(16), "big") ^ time.time_ns() ^ hash(node_id)
        self.rng = random.Random(seed)

    def generate_payload(self):
        raise NotImplementedError

    def run(self, interval=5):
        print(f"Starting Node {self.node_id} ({self.node_type}) via {type(self.protocol).__name__}...")
        while True:
            payload = self.generate_payload()
            self.protocol.send(payload)
            # Add some jitter so 300 nodes don't fire at the exact same millisecond
            time.sleep(interval + self.rng.uniform(-1.2, 1.2))


# ──────────────────────────────────────────
# EHS Node Type 1: Air Quality Station
# Protocol: MQTT (battery-powered outdoor)
# Parameters: AQI, PM2.5, PM10, CO2, temp, humidity
# ──────────────────────────────────────────

class AirQualityNode(SimulatedNode):
    """
    Simulates an outdoor air quality monitoring station.
    AQI follows US EPA scale (0–500). 5% chance of toxic spike.
    PM2.5/PM10 correlate with AQI. CO2 follows diurnal traffic patterns.
    """
    def __init__(self, node_id, protocol_adapter):
        super().__init__(node_id, protocol_adapter)
        self.domain = "ehs"
        self.node_type = "air_quality"

    def generate_payload(self):
        is_spike = self.rng.random() < 0.05
        aqi = self.rng.randint(150, 400) if is_spike else self.rng.randint(18, 65)
        # PM2.5 and PM10 correlate with AQI
        pm25 = round(aqi * 0.35 + self.rng.uniform(-7, 7), 1)
        pm10 = round(aqi * 0.55 + self.rng.uniform(-10, 10), 1)
        # CO2 follows traffic patterns (higher during business hours)
        hour = datetime.datetime.now().hour
        base_co2 = 400 + (150 if 8 <= hour <= 18 else 0)
        co2_ppm = round(base_co2 + self.rng.uniform(-45, 45))
        temperature_c = round(self.rng.uniform(17, 39), 1)
        humidity_pct = round(self.rng.uniform(28, 88), 1)

        return {
            "node_id": self.node_id,
            "domain": self.domain,
            "node_type": self.node_type,
            "timestamp": datetime.datetime.now().isoformat(),
            "data": {
                "aqi": aqi,
                "pm25": max(0, pm25),
                "pm10": max(0, pm10),
                "co2_ppm": max(350, co2_ppm),
                "temperature_c": temperature_c,
                "humidity_pct": humidity_pct,
                "water_ph": round(self.rng.uniform(6.3, 8.7), 2),
                "is_critical": is_spike
            }
        }


# ──────────────────────────────────────────
# EHS Node Type 2: Water Quality Probe
# Protocol: MQTT (submerged, event-driven)
# Parameters: pH, turbidity, dissolved O2, water temp
# ──────────────────────────────────────────

class WaterQualityNode(SimulatedNode):
    """
    Simulates a submerged water quality probe in campus water bodies.
    pH normally 6.5–8.5, with 3% chance of contamination event.
    Turbidity spikes after simulated rainfall events.
    """
    def __init__(self, node_id, protocol_adapter):
        super().__init__(node_id, protocol_adapter)
        self.domain = "ehs"
        self.node_type = "water_quality"

    def generate_payload(self):
        is_contaminated = self.rng.random() < 0.03
        water_ph = round(self.rng.uniform(3.5, 5.0) if is_contaminated
                         else self.rng.uniform(6.4, 8.6), 2)
        # Turbidity spikes during contamination
        turbidity_ntu = round(self.rng.uniform(50, 200) if is_contaminated
                              else self.rng.uniform(0.3, 6.0), 2)
        dissolved_oxygen = round(self.rng.uniform(2.0, 5.0) if is_contaminated
                                 else self.rng.uniform(5.5, 12.5), 2)
        water_temp_c = round(self.rng.uniform(14, 31), 1)

        return {
            "node_id": self.node_id,
            "domain": self.domain,
            "node_type": self.node_type,
            "timestamp": datetime.datetime.now().isoformat(),
            "data": {
                "aqi": self.rng.randint(18, 65),
                "water_ph": water_ph,
                "turbidity_ntu": turbidity_ntu,
                "dissolved_oxygen_mgl": dissolved_oxygen,
                "water_temp_c": water_temp_c,
                "is_critical": is_contaminated
            }
        }


# ──────────────────────────────────────────
# EHS Node Type 3: Noise Level Monitor
# Protocol: MQTT (compact acoustic sensor)
# Parameters: noise dB, peak dB, dominant frequency
# ──────────────────────────────────────────

class NoiseMonitorNode(SimulatedNode):
    """
    Simulates acoustic noise monitors near roads and construction zones.
    Campus ambient ~40–55 dB, construction zones 70–95 dB.
    10% chance of noise spike (construction/event).
    """
    def __init__(self, node_id, protocol_adapter):
        super().__init__(node_id, protocol_adapter)
        self.domain = "ehs"
        self.node_type = "noise_monitor"

    def generate_payload(self):
        is_loud = self.rng.random() < 0.10
        noise_db = round(self.rng.uniform(70, 100) if is_loud
                         else self.rng.uniform(32, 65), 1)
        peak_db = round(noise_db + self.rng.uniform(3, 15), 1)
        # Dominant frequency: low rumble (construction) vs speech range
        frequency_hz = self.rng.choice([125, 250, 500, 1000, 2000, 4000])

        return {
            "node_id": self.node_id,
            "domain": self.domain,
            "node_type": self.node_type,
            "timestamp": datetime.datetime.now().isoformat(),
            "data": {
                "noise_db": noise_db,
                "peak_db": min(130, peak_db),
                "frequency_hz": frequency_hz,
                "is_critical": noise_db > 85
            }
        }


# ──────────────────────────────────────────
# EHS Node Type 4: Weather Station
# Protocol: HTTP (AC-powered rooftop, full bandwidth)
# Parameters: temp, humidity, wind, pressure, UV, rainfall
# ──────────────────────────────────────────

class WeatherStationNode(SimulatedNode):
    """
    Simulates AC-powered rooftop weather stations.
    Uses HTTP POST for richer payloads (not battery-constrained).
    Temperature follows realistic diurnal sine curve.
    """
    def __init__(self, node_id, protocol_adapter):
        super().__init__(node_id, protocol_adapter)
        self.domain = "ehs"
        self.node_type = "weather_station"

    def generate_payload(self):
        hour = datetime.datetime.now().hour
        # Diurnal temperature curve: min ~5AM, max ~2PM
        base_temp = 25 + 8 * math.sin((hour - 5) * math.pi / 12)
        temperature_c = round(base_temp + self.rng.uniform(-2.4, 2.4), 1)
        humidity_pct = round(max(20, min(95, 70 - temperature_c * 0.8 + self.rng.uniform(-12, 12))), 1)
        wind_speed_ms = round(self.rng.uniform(0, 15), 1)
        wind_direction_deg = self.rng.randint(0, 359)
        pressure_hpa = round(self.rng.uniform(1008, 1025), 1)
        # UV index follows sunlight curve
        uv_index = round(max(0, 8 * math.sin((hour - 6) * math.pi / 12)
                              + self.rng.uniform(-1, 1)), 1) if 6 <= hour <= 18 else 0
        rainfall_mm = round(self.rng.uniform(0, 5), 1) if self.rng.random() < 0.15 else 0

        return {
            "node_id": self.node_id,
            "domain": self.domain,
            "node_type": self.node_type,
            "timestamp": datetime.datetime.now().isoformat(),
            "data": {
                "temperature_c": temperature_c,
                "humidity_pct": humidity_pct,
                "wind_speed_ms": wind_speed_ms,
                "wind_direction_deg": wind_direction_deg,
                "pressure_hpa": pressure_hpa,
                "uv_index": max(0, uv_index),
                "rainfall_mm": rainfall_mm,
                "is_critical": uv_index > 8 or wind_speed_ms > 12
            }
        }


# ──────────────────────────────────────────
# EHS Node Type 5: Soil & Agriculture Sensor
# Protocol: CoAP (ultra-low-power, constrained)
# Parameters: soil moisture, soil pH, soil temp
# ──────────────────────────────────────────

class SoilSensorNode(SimulatedNode):
    """
    Simulates soil sensors in campus gardens and greenhouses.
    Uses CoAP for ultra-low-power transmission (RFC 7252).
    Soil moisture varies with irrigation cycles.
    """
    def __init__(self, node_id, protocol_adapter):
        super().__init__(node_id, protocol_adapter)
        self.domain = "ehs"
        self.node_type = "soil_sensor"

    def generate_payload(self):
        hour = datetime.datetime.now().hour
        # Irrigation typically at 6AM and 6PM → moisture spikes
        is_irrigated = hour in (6, 7, 18, 19)
        soil_moisture_pct = round(self.rng.uniform(60, 85) if is_irrigated
                                  else self.rng.uniform(20, 50), 1)
        soil_ph = round(self.rng.uniform(5.4, 7.6), 2)
        soil_temp_c = round(self.rng.uniform(14, 36), 1)

        return {
            "node_id": self.node_id,
            "domain": self.domain,
            "node_type": self.node_type,
            "timestamp": datetime.datetime.now().isoformat(),
            "data": {
                "soil_moisture_pct": soil_moisture_pct,
                "soil_ph": soil_ph,
                "soil_temp_c": soil_temp_c,
                "is_critical": soil_moisture_pct < 15 or soil_ph < 4.5
            }
        }


# ──────────────────────────────────────────
# EHS Node Type 6: Radiation & Gas Detector
# Protocol: MQTT (critical safety, persistent connection)
# Parameters: radiation µSv/h, VOC ppb, CO ppm, methane ppm
# ──────────────────────────────────────────

class RadiationGasNode(SimulatedNode):
    """
    Simulates lab-adjacent radiation and gas safety sensors.
    Normal background radiation: 0.05–0.3 µSv/h.
    2% chance of lab leak event (elevated VOC/CO).
    """
    def __init__(self, node_id, protocol_adapter):
        super().__init__(node_id, protocol_adapter)
        self.domain = "ehs"
        self.node_type = "radiation_gas"

    def generate_payload(self):
        is_leak = self.rng.random() < 0.02
        radiation_usv = round(self.rng.uniform(0.5, 2.5) if is_leak
                              else self.rng.uniform(0.05, 0.25), 3)
        voc_ppb = round(self.rng.uniform(1500, 5000) if is_leak
                        else self.rng.uniform(50, 400))
        co_ppm = round(self.rng.uniform(20, 80) if is_leak
                       else self.rng.uniform(0, 5), 1)
        methane_ppm = round(self.rng.uniform(500, 2000) if is_leak
                           else self.rng.uniform(1, 50), 1)

        return {
            "node_id": self.node_id,
            "domain": self.domain,
            "node_type": self.node_type,
            "timestamp": datetime.datetime.now().isoformat(),
            "data": {
                "radiation_usv": radiation_usv,
                "voc_ppb": voc_ppb,
                "co_ppm": co_ppm,
                "methane_ppm": methane_ppm,
                "is_critical": is_leak
            }
        }


# ──────────────────────────────────────────
# Energy Node (preserved from original)
# ──────────────────────────────────────────

class EnergyNode(SimulatedNode):
    def __init__(self, node_id, protocol_adapter):
        super().__init__(node_id, protocol_adapter)
        self.domain = "energy"
        self.node_type = "power_monitor"

    def generate_payload(self):
        # Simulate realistic solar curve based on current hour
        hour = datetime.datetime.now().hour
        solar_output = 0
        if 7 <= hour <= 18:
            # Curve peaks around noon (hour 12)
            solar_output = max(0, 1000 - (abs(12 - hour) * 150)) + self.rng.randint(-50, 50)

        ac_load = self.rng.randint(300, 1200)

        return {
            "node_id": self.node_id,
            "domain": self.domain,
            "node_type": self.node_type,
            "timestamp": datetime.datetime.now().isoformat(),
            "data": {
                "solar_generation_watts": max(0, solar_output),
                "ac_consumption_watts": ac_load
            }
        }


# ==========================================
# 3. NODE CATALOG
# ==========================================

EHS_NODE_CATALOG = [
    {
        "node_type": "air_quality",
        "label": "Air Quality Station",
        "prefix": "EHS-AQI",
        "count": 40,
        "protocol": "mqtt",
        "protocols": ["MQTT"],
        "parameters": ["aqi", "pm25", "pm10", "co2_ppm", "temperature_c", "humidity_pct"],
        "used_for": ["prediction", "visualization", "suggestions"],
    },
    {
        "node_type": "water_quality",
        "label": "Water Quality Probe",
        "prefix": "EHS-WTR",
        "count": 25,
        "protocol": "mqtt",
        "protocols": ["MQTT"],
        "parameters": ["water_ph", "turbidity_ntu", "dissolved_oxygen_mgl", "water_temp_c"],
        "used_for": ["prediction", "visualization", "suggestions"],
    },
    {
        "node_type": "noise_monitor",
        "label": "Noise Level Monitor",
        "prefix": "EHS-NOS",
        "count": 20,
        "protocol": "mqtt",
        "protocols": ["MQTT"],
        "parameters": ["noise_db", "peak_db", "frequency_hz"],
        "used_for": ["visualization", "suggestions"],
    },
    {
        "node_type": "weather_station",
        "label": "Weather Station",
        "prefix": "EHS-WEA",
        "count": 10,
        "protocol": "http",
        "protocols": ["HTTP"],
        "parameters": ["temperature_c", "humidity_pct", "wind_speed_ms", "wind_direction_deg", "pressure_hpa", "uv_index", "rainfall_mm"],
        "used_for": ["visualization", "suggestions"],
    },
    {
        "node_type": "soil_sensor",
        "label": "Soil Sensor",
        "prefix": "EHS-SOL",
        "count": 15,
        "protocol": "coap",
        "protocols": ["CoAP"],
        "parameters": ["soil_moisture_pct", "soil_ph", "soil_temp_c"],
        "used_for": ["visualization", "suggestions"],
    },
    {
        "node_type": "radiation_gas",
        "label": "Radiation/Gas Detector",
        "prefix": "EHS-RAD",
        "count": 10,
        "protocol": "mqtt",
        "protocols": ["MQTT"],
        "parameters": ["radiation_usv", "voc_ppb", "co_ppm", "methane_ppm"],
        "used_for": ["prediction", "visualization", "suggestions"],
    },
]

NODE_CLASS_BY_TYPE = {
    "air_quality": AirQualityNode,
    "water_quality": WaterQualityNode,
    "noise_monitor": NoiseMonitorNode,
    "weather_station": WeatherStationNode,
    "soil_sensor": SoilSensorNode,
    "radiation_gas": RadiationGasNode,
}


def describe_catalog() -> None:
    print("\n  EHS node catalog (source of truth)")
    for item in EHS_NODE_CATALOG:
        params = ", ".join(item["parameters"])
        protos = "/".join(item["protocols"])
        print(f"    - {item['prefix']} ×{item['count']:<2} {item['label']} | {protos} | {params}")


# ==========================================
# 4. GENERATOR ORCHESTRATOR
# ==========================================

# Node distribution for 120 EHS nodes.
EHS_NODE_CONFIG = [
    (item["count"], item["prefix"], NODE_CLASS_BY_TYPE[item["node_type"]], item["protocol"])
    for item in EHS_NODE_CATALOG
]


def main():
    print("=" * 60)
    print("  Smart City IoT Data Generator (Expanded EHS Edition)")
    print("  6 EHS Node Types | 3 Protocols | 300 Nodes")
    print("=" * 60)
    print()
    describe_catalog()

    # ── Scale factor: set to 1.0 for full 300-node production run ──
    # At 0.1, runs 12 EHS + a few energy nodes for easy dev testing.
    SCALE = 0.1  # Change to 1.0 for full 300-node stress test
    ENERGY_NODES = max(1, int(60 * SCALE))  # Remaining nodes for energy
    INTERVAL = 5  # seconds between readings per node

    # Prepare shared protocol instances
    http_protocol = HttpAdapter()
    mqtt_protocol = MqttAdapter()
    coap_protocol = CoapAdapter()

    protocol_map = {
        "http": http_protocol,
        "mqtt": mqtt_protocol,
        "coap": coap_protocol,
    }

    threads = []
    node_count = 0

    # ── Create EHS Nodes ──
    print(f"\n{'─' * 50}")
    print(f"  EHS NODES (Environmental Health & Safety)")
    print(f"{'─' * 50}")

    for count, prefix, NodeClass, pref_protocol in EHS_NODE_CONFIG:
        scaled_count = max(1, int(count * SCALE))
        adapter = protocol_map[pref_protocol]
        for i in range(scaled_count):
            node_id = f"{prefix}-{i:03d}"
            node = NodeClass(node_id, adapter)
            t = threading.Thread(target=node.run, args=(INTERVAL,), daemon=True)
            threads.append(t)
            node_count += 1
        print(f"  ✓ {scaled_count:>3}x {prefix}  →  {pref_protocol.upper():>4}  ({NodeClass.__name__})")

    # ── Create Energy Nodes ──
    print(f"\n{'─' * 50}")
    print(f"  ENERGY NODES")
    print(f"{'─' * 50}")

    for i in range(ENERGY_NODES):
        protocol = http_protocol if random.random() > 0.5 else mqtt_protocol
        node = EnergyNode(f"PWR-NODE-{i:03d}", protocol)
        t = threading.Thread(target=node.run, args=(INTERVAL,), daemon=True)
        threads.append(t)
        node_count += 1
    print(f"  ✓ {ENERGY_NODES:>3}x PWR-NODE  →  HTTP/MQTT  (EnergyNode)")

    # ── Launch all threads ──
    print(f"\n{'═' * 60}")
    print(f"  LAUNCHING {node_count} NODES...")
    print(f"{'═' * 60}\n")

    for t in threads:
        t.start()
        time.sleep(0.02)  # Stagger starts to avoid burst

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print(f"\n[SHUTDOWN] Stopping all {node_count} IoT nodes...")


if __name__ == "__main__":
    main()
