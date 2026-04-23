# Smart Appliance Nodes (Targets / Actuators)
-- also send the state change events to Ingestion using Websocket
👉 These can be controlled (ON/OFF, adjust levels)

* AC Unit Node
* Indoor Lighting Node
* Outdoor Lamp Post Node
* Water Pump Node

# Data Collection Nodes (Sensors / Monitors)

👉 These observe + report, no direct control

* Solar Panel Node
* Smart Energy Meter Node
* Battery / Energy Storage Node
* Grid / Transformer Node
* Environmental Sensor Node
* Occupancy / Footfall Node
* Smart Water Meter Node

# Quick mental model
* Appliance nodes = "Do something"
* Data nodes = "Tell you what's happening"

| Node Name                     | Purpose (simple)                          | Protocol                         | Data / Control Payload                                  |
| ----------------------------- | ----------------------------------------- | -------------------------------- | ------------------------------------------------------- |
| **Solar Panel Node**          | Tells how much energy is being generated  | MQTT                             | `{ power_w, energy_kwh, voltage, current, status }`    |
| **Smart Energy Meter Node**   | Measures electricity usage                | MQTT                             | `{ voltage, current, power, energy_kwh, power_factor }` |
| **Battery / Storage Node**    | Reports battery level and charging status | MQTT / HTTP                      | `{ soc, voltage, charge_rate, status }`                 |
| **Grid / Transformer Node**   | Monitors grid load and faults             | MQTT / HTTP                      | `{ load_percent, temperature, fault_status }`           |
| **Environmental Sensor Node** | Reports weather and air conditions        | CoAP / MQTT                      | `{ temperature, humidity, pm2_5, co2, noise_db }`       |
| **Occupancy / Footfall Node** | Detects people presence/count             | MQTT / CoAP                      | `{ occupancy, count }`                                   |
| **Smart Water Meter Node**    | Tracks water usage and leaks              | MQTT                             | `{ flow_rate, total_consumption, leak_detected }`       |
| **AC Unit Node**              | Controls cooling based on demand          | MQTT / HTTP (receives control)   | `{ command: ON/OFF, set_temp, mode }`                   |
| **Indoor Lighting Node**      | Controls lights inside buildings          | MQTT                             | `{ command: ON/OFF, brightness }`                       |
| **Outdoor Lamp Post Node**    | Controls street lighting                  | MQTT                             | `{ command: ON/OFF, brightness }`                       |
| **Water Pump Node**           | Controls water flow systems               | MQTT / HTTP                      | `{ command: ON/OFF, flow_level }`                       |

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
│     EnergyManagementEngine    │
└───────────────────────────────┘
	↓
Middleware (commands)
	↓
Appliance Nodes
	↓
Feedback → back to Middleware
```

# Current Scope (Same style as EHS)

Do only this flow for now:

`IoT Nodes -> Ingestion -> Middleware -> Energy Appliance Logic -> Feedback`

Step meaning:
1. IoT Nodes: Data and appliance state events are produced.
2. Ingestion: Normalizes protocol payloads to a common SmartCityObject.
3. Middleware: Persists telemetry/state and exposes it to engines.
4. Energy Appliance Logic: Evaluates conditions and decides control/suggestion actions.
5. Feedback: Dashboard/consumer systems receive latest status and decisions.

Not included in this scope:
- No IoT node ignition/bootstrap or recovery orchestration.
- No auto-start simulation runners in this document scope.
