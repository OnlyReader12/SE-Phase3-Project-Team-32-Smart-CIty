import time
import json
import random
import threading
import datetime
import requests
import paho.mqtt.client as mqtt

# ==========================================
# 1. PROTOCOL ADAPTERS (Strategy Pattern)
# ==========================================
class ProtocolAdapter:
    def send(self, payload):
        raise NotImplementedError

class HttpAdapter(ProtocolAdapter):
    def __init__(self, target_url="http://localhost:8000/api/telemetry"):
        self.target_url = target_url

    def send(self, payload):
        try:
            # Simulate HTTP POST. Fast timeout to avoid hanging threads.
            # response = requests.post(self.target_url, json=payload, timeout=2)
            print(f"[HTTP POST] {payload['node_id']} Data:\n{json.dumps(payload, indent=2)}\n")
        except Exception as e:
            print(f"[HTTP ERROR] Destination unreachable for {payload['node_id']}")

class MqttAdapter(ProtocolAdapter):
    def __init__(self, broker="localhost", port=1883, topic="smartcity/telemetry"):
        self.broker = broker
        self.port = port
        self.topic = topic
        self.client = mqtt.Client()
        try:
            # Uncomment below if you have a real broker running
            # self.client.connect(self.broker, self.port)
            pass
        except Exception:
            pass

    def send(self, payload):
        try:
            merged_topic = f"{self.topic}/{payload['domain']}"
            # self.client.publish(merged_topic, json.dumps(payload))
            print(f"[MQTT PUBLISH] to '{merged_topic}':\n{json.dumps(payload, indent=2)}\n")
        except Exception as e:
            print(f"[MQTT ERROR] Broker unreachable for {payload['node_id']}")

# ==========================================
# 2. NODE DOMAIN DEFINITIONS
# ==========================================
class SimulatedNode:
    def __init__(self, node_id, protocol_adapter):
        self.node_id = node_id
        self.protocol = protocol_adapter
        self.domain = "unknown"

    def generate_payload(self):
        raise NotImplementedError

    def run(self, interval=5):
        print(f"Starting Node {self.node_id} ({self.domain}) via {type(self.protocol).__name__}...")
        while True:
            payload = self.generate_payload()
            self.protocol.send(payload)
            # Add some jitter so 300 nodes don't fire at the exact same millisecond
            time.sleep(interval + random.uniform(-1, 1))

class EHSNode(SimulatedNode):
    def __init__(self, node_id, protocol_adapter):
        super().__init__(node_id, protocol_adapter)
        self.domain = "ehs"

    def generate_payload(self):
        # 5% chance of a toxic AQI spike
        is_spike = random.random() < 0.05
        aqi = random.randint(150, 400) if is_spike else random.randint(20, 50)
        water_ph = round(random.uniform(6.5, 8.5), 2)
        
        return {
            "node_id": self.node_id,
            "domain": self.domain,
            "timestamp": datetime.datetime.now().isoformat(),
            "data": {
                "aqi": aqi,
                "water_ph": water_ph,
                "is_critical": is_spike
            }
        }

class EnergyNode(SimulatedNode):
    def __init__(self, node_id, protocol_adapter):
        super().__init__(node_id, protocol_adapter)
        self.domain = "energy"

    def generate_payload(self):
        # Simulate realistic solar curve based on current hour
        hour = datetime.datetime.now().hour
        solar_output = 0
        if 7 <= hour <= 18:
            # Curve peaks around noon (hour 12)
            solar_output = max(0, 1000 - (abs(12 - hour) * 150)) + random.randint(-50, 50)

        ac_load = random.randint(300, 1200)

        return {
            "node_id": self.node_id,
            "domain": self.domain,
            "timestamp": datetime.datetime.now().isoformat(),
            "data": {
                "solar_generation_watts": max(0, solar_output),
                "ac_consumption_watts": ac_load
            }
        }

# ==========================================
# 3. GENERATOR ORCHESTRATOR
# ==========================================
def main():
    print("=============================================")
    print("  Smart City IoT Data Generator Starting...")
    print("=============================================\n")
    
    TOTAL_NODES = 10  # Set to 300 for full production stress test
    threads = []

    # Prepare Shared Protocols
    http_protocol = HttpAdapter()
    mqtt_protocol = MqttAdapter()

    # Create & Start Nodes
    for i in range(TOTAL_NODES):
        # Even IDs = Energy, Odd IDs = EHS
        if i % 2 == 0:
            # Mix the protocols randomly
            protocol = http_protocol if random.random() > 0.5 else mqtt_protocol
            node = EnergyNode(f"PWR-NODE-{i:03d}", protocol)
        else:
            protocol = mqtt_protocol if random.random() > 0.5 else http_protocol
            node = EHSNode(f"EHS-NODE-{i:03d}", protocol)

        t = threading.Thread(target=node.run, args=(5,), daemon=True)
        threads.append(t)
        t.start()

    try:
        # Keep main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Stopping all 300 IoT nodes...")

if __name__ == "__main__":
    main()
