# IoT Data Generator

This directory contains the Python simulator designed to stress-test the Smart City Living Lab backbone by simulating 300+ asynchronous, heterogeneous hardware nodes.

It follows the **Strategy Pattern** for transmission (HTTP vs MQTT) and the **Factory/OOP Pattern** for generating realistic domain data curves (e.g. solar energy peaking at noon, sporadic toxic air quality spikes).

## 🚀 How to Run the Data Generator

1. **Navigate to the generation folder:**
   ```bash
   cd IOTDataGenerator
   ```

2. **Install the lightweight dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
   *(We highly recommend running this inside a Virtual Environment `python3 -m venv venv`)*

3. **Execute the script:**
   ```bash
   python3 iot_generator.py
   ```

*(Note: The script currently defaults to 10 nodes for easy console reading. To run the full 300-node production stress test, change `TOTAL_NODES = 300` on Line 95 in `iot_generator.py`.)*

---

## 🎧 How to Verify and Access the Sent Data (Interception)

By default, the generator pushes data out to network ports exactly like a physical hardware node would. If you want to "catch" and see the data arriving, you need to set up local listeners.

### 1. Catching HTTP POST Data
The simulator sends standard HTTP web requests to `http://localhost:8000/api/telemetry`. If nothing is running on port 8000, those requests will fail gracefully.
*   **To see the data:** You can start a dummy server in a separate terminal. The easiest way without writing code is using `netcat` to listen on port 8000:
    ```bash
    nc -l 8000
    ```
    Once running, every time an HTTP node fires, you will see the full raw JSON printed in the terminal!

### 2. Catching MQTT Data (What is Mosquitto?)
**Mosquitto** is an open-source "Message Broker". Because IoT devices (like battery-powered water sensors) are low-power, they don't hold connections open. They just shout their data into the void using the **MQTT** protocol. The "Mosquitto Broker" acts as a centralized post office that catches those shouts and routes them to whoever cares about them.
*   **To install Mosquitto (Linux):** 
    ```bash
    sudo apt install mosquitto mosquitto-clients
    ```
*   **To catch the data:** Start Mosquitto in one terminal, and use the built-in subscriber to listen to all Smart City topics:
    ```bash
    mosquitto_sub -h localhost -t "smartcity/telemetry/#" -v
    ```
    As the generator runs, you will see a live stream of data popping up here in real time!

---

## 🛠 How to Add New Protocols

Currently, the simulator supports **HTTP POSTs** and **MQTT Publishes**. Because the script is isolated via the Strategy Pattern, adding a new hardware language (like CoAP or a raw TCP socket) is trivial.

**Step 1:** Open `iot_generator.py`.
**Step 2:** Find the "PROTOCOL ADAPTERS" section.
**Step 3:** Create a new class that inherits from `ProtocolAdapter`. 
**Step 4:** Implement the `.send()` method.

```python
class CoapAdapter(ProtocolAdapter):
    def __init__(self, target_ip):
        self.target_ip = target_ip

    def send(self, payload):
        # Write your custom PyCoAP logic here
        print(f"[CoAP] Successfully sent data for {payload['node_id']}")
```
Now, simply pass `CoapAdapter` into any node upon creation!

---

## 🌍 How to Add New Node Types (Domains)

If the city expands to track Smart Waste Management or Smart Parking, you don't need to rewrite the generator core. You just create a new Domain Object that generates exactly what the new hardware would read.

**Step 1:** Find the "NODE DOMAIN DEFINITIONS" section.
**Step 2:** Create a new class inheriting from `SimulatedNode`.
**Step 3:** Implement your custom dummy-data math inside `generate_payload()`.

```python
class SmartBinNode(SimulatedNode):
    def __init__(self, node_id, protocol_adapter):
        super().__init__(node_id, protocol_adapter)
        self.domain = "waste"

    def generate_payload(self):
        # A trash bin slowly gets fuller, occasionally emptying to 0%
        fill_level = random.randint(0, 100)
        
        return {
            "node_id": self.node_id,
            "timestamp": datetime.datetime.now().isoformat(),
            "data": {
                "bin_fullness_percent": fill_level
            }
        }
```
**Step 4:** Register it in the generator loop at the bottom by instantiating `SmartBinNode("BIN-001", mqtt_protocol)`.
