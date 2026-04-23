# Data Collection Nodes (observe / report)

👉 These nodes only send data into your system

## 💧 Water (Data)
* Water Quality Monitoring Node
* Reservoir Level Monitoring Node
* Soil Moisture Monitoring Node
* Smart Water Meter Node
## 🌬️ Air (Data)
* Air Quality Monitoring Node
* Temperature & Humidity Node
* Wind Monitoring Node
* Environmental Sensor Node

# Target / Actuator Nodes (control / act)
-- also send the state change events to Ingestion using Websocket 
👉 These nodes receive commands from your system

## 💧 Water (Actuators)
* Valve Control Node
* Water Treatment Control Node
* Water Pump Node
## 🌬️ Air (Actuators)
* Ventilation Control Node
* Air Purification Control Node

# Water Domain

| Node Type                             | Purpose (simple)                       | Protocol    | Data Payload                                               |
| ------------------------------------- | -------------------------------------- | ----------- | ---------------------------------------------------------- |
| **Water Quality Monitoring Node**     | Checks if water is safe                | MQTT / CoAP | `{ ph, turbidity, tds, temperature, contamination_level }` |
| **Reservoir Level Monitoring Node**   | Tracks water level in tanks/reservoirs | MQTT        | `{ level_percent, volume }`                                |
| **Soil Moisture Monitoring Node**     | Measures soil wetness (for irrigation) | CoAP / MQTT | `{ moisture_level }`                                       |
| **Valve Control Node**           | Opens/closes water flow              | MQTT / HTTP | `{ command: OPEN/CLOSE, valve_level }`   |
| **Water Treatment Control Node** | Controls purification processes      | HTTP / MQTT | `{ command: START/STOP, chemical_dose }` |
| **Smart Water Meter Node**    | Tracks water usage and leaks              | MQTT                           | `{ flow_rate, total_consumption, leak_detected }`       |
| **Water Pump Node**           | Controls water flow systems               | MQTT / HTTP                    | `{ command: ON/OFF, flow_level }`                       |

# Air Domain

| Node Type                       | Purpose (simple)                    | Protocol    | Data Payload                          |
| ------------------------------- | ----------------------------------- | ----------- | ------------------------------------- |
| **Air Quality Monitoring Node** | Measures pollution levels           | MQTT / CoAP | `{ pm2_5, pm10, co2, no2, o3 }`       |
| **Temperature & Humidity Node** | Tracks environmental comfort        | CoAP / MQTT | `{ temperature, humidity }`           |
| **Wind Monitoring Node**        | Measures wind speed/direction       | MQTT        | `{ wind_speed, wind_direction }`      |
| **Ventilation Control Node**      | Controls airflow (fans, vents)       | MQTT / HTTP | `{ command: ON/OFF, speed }`              |
| **Air Purification Control Node** | Controls air filters/purifiers       | MQTT        | `{ command: ON/OFF, mode }`               |
| **Environmental Sensor Node** | Reports weather and air conditions        | CoAP / MQTT                    | `{ temperature, humidity, pm2_5, co2, noise_db }`       |


# 🔁 Actuator State Feedback Table (WebSocket → Ingestion)
| Node Type                         | State Payload (WebSocket → Ingestion)        |
| --------------------------------- | -------------------------------------------- |
| **Valve Control Node**            | `{ state: OPEN/CLOSED, valve_level }`        |
| **Water Treatment Control Node**  | `{ state: RUNNING/STOPPED, chemical_dose }`  |
| **Water Pump Node**               | `{ state: ON/OFF, flow_level, power_usage }` |
| **Ventilation Control Node**      | `{ state: ON/OFF, speed }`                   |
| **Air Purification Control Node** | `{ state: ON/OFF, mode, air_quality_index }` |



# System Flow
```
IoT Data Nodes
      ↓
Ingestion (parse → SmartCityObject)
      ↓
Middleware (DB / state store)
      ↓
 ┌───────────────────────────────┐
 │   Decision Layer              │
 │                               │
 │     EHSEngine                 │
 └───────────────────────────────┘
      ↓
Middleware (commands)
      ↓
Appliance Nodes
      ↓
Feedback → back to Middleware
```