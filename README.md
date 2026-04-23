# 🏙️ Smart City Living Lab — System README

A modular, real-time Smart City IoT platform with 100 simulated campus nodes, domain engines, and a multi-role Flutter dashboard.

---

## 📐 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        IoT Data Generator                           │
│              100 campus nodes (MQTT / CoAP / HTTP / WS)             │
└────────────────────────────────┬────────────────────────────────────┘
                                 │ telemetry
                                 ▼
┌────────────────────────────────────────────────────────────────────┐
│                   Ingestion Engine  :8000                          │
│   Adapters: MQTT, CoAP, HTTP  │  Embedded MQTT Broker :1883       │
└────────────────────────────────┬───────────────────────────────────┘
                                 │ RabbitMQ publish
                                 ▼
┌────────────────────────────────────────────────────────────────────┐
│               Persistent Middleware  :8001                         │
│        SQLite persistence  │  REST API  │  Node state store        │
└──────────────┬─────────────────────────────────────────────────────┘
               │ poll every 30s
       ┌───────┴──────────┐
       ▼                  ▼
┌─────────────┐    ┌─────────────┐
│  Energy Mgr │    │  EHS Engine │
│  Engine     │    │  :8005      │
│  :8004      │    └──────┬──────┘
└──────┬──────┘           │  POST /internal/alerts
       └──────────┬───────┘
                  ▼
        ┌─────────────────┐
        │   UserService   │
        │   :8003         │
        │  Auth│RBAC│Dash │
        └────────┬────────┘
                 │ JSON REST
                 ▼
        ┌─────────────────┐
        │  Flutter Web App│
        │  :8080          │
        │  4 Role Dashboards│
        └─────────────────┘
```

---

## 🗂️ Service Ports Reference

| Service | Port | Description |
|---|---|---|
| Ingestion Engine | `8000` | IoT protocol adapters + embedded MQTT broker |
| MQTT Broker (embedded) | `1883` | Embedded AMQTT inside IngestionEngine |
| Persistent Middleware | `8001` | Node state store + REST API |
| UserService | `8003` | Auth, RBAC, Subscriptions, Dashboards, Alerts |
| Energy Management Engine | `8004` | Rule-based energy analytics |
| EHS Engine | `8005` | Environmental Health & Safety analytics |
| Flutter Web App | `8080` | Multi-role dashboard UI |

---

## 🚀 How to Run — Step by Step

> **Start services in this exact order.** Each service depends on the one above it.

---

### 0. Prerequisites

```bash
# Check Python (needs 3.10+)
python3 --version

# Check Flutter (needs 3.10+)
flutter --version

# Check RabbitMQ is running
sudo systemctl status rabbitmq-server
# If not running:
sudo systemctl start rabbitmq-server
```

---

### 1. 🌐 Ingestion Engine (Port 8000)

Opens 4 protocol adapters and the embedded MQTT broker.

```bash
cd core_modules/IngestionEngine
source .ingvenv/bin/activate
uvicorn main:app --port 8000 --reload
```

**Expected logs:**
```
[Ingestion Engine] Connected to RabbitMQ at 127.0.0.1
[Embedded Broker] AMQTT Server live on port 1883...
INFO: Uvicorn running on http://127.0.0.1:8000
```

---

### 2. 💾 Persistent Middleware (Port 8001)

```bash
cd core_modules/PersistentMiddleware
# Create venv if first time:
python3 -m venv .pmvenv && source .pmvenv/bin/activate && pip install -r requirements.txt
# Or if venv exists:
source .pmvenv/bin/activate
uvicorn main:app --port 8001 --reload
```

**Expected logs:**
```
[Middleware] Connected to RabbitMQ, consuming messages...
INFO: Uvicorn running on http://127.0.0.1:8001
```

---

### 3. 📡 IoT Node Simulator (100 campus nodes)

```bash
cd IOTDataGenerator
# Create venv if first time:
python3 -m venv .simvenv && source .simvenv/bin/activate && pip install -r requirements.txt
# Or if venv exists:
source .simvenv/bin/activate
python simulator/main.py
```

**Expected logs:**
```
[Simulator] Starting 100 nodes...
[MQTT] TEMP-HUMIDITY-001 → published OK
[CoAP] WATER-QUALITY-041 → success
[HTTP] SOLAR-PANEL-001 → 200 OK
```

> Nodes publish every **30 seconds** by default.

---

### 4. 👥 UserService (Port 8003)

```bash
cd core_modules/UserService
source .usvenv/bin/activate

# First time only — seed test users:
python seed_db.py

# Start service:
uvicorn main:app --port 8003 --reload
```

**Expected logs:**
```
[UserService] DB tables created.
INFO: Uvicorn running on http://127.0.0.1:8003
```

**Test users created by seed_db.py:**

| Role | Email | Password |
|---|---|---|
| Manager | `manager@city.com` | `password123` |
| Resident | `resident@city.com` | `password123` |
| Servicer | `servicer@city.com` | `password123` |
| Analyst | `analyst@city.com` | `password123` |

---

### 5. ⚡ Energy Management Engine (Port 8004)

```bash
cd core_modules/EnergyManagementEngine
python3 -m venv .emevenv && source .emevenv/bin/activate && pip install -r requirements.txt

uvicorn main:app --port 8004 --reload
```

**Expected logs:**
```
[EnergyManagementEngine] Initialised with 5 rules.
[EnergyManagementEngine] Starting analysis loop (every 30s).
INFO: Uvicorn running on http://127.0.0.1:8004
```

---

### 6. 🌬️ EHS Engine (Port 8005)

```bash
cd core_modules/EHSEngine
python3 -m venv .ehsvenv && source .ehsvenv/bin/activate && pip install -r requirements.txt

uvicorn main:app --port 8005 --reload
```

**Expected logs:**
```
[EHSEngine] Initialised with 5 rules.
[EHSEngine] Starting analysis loop (every 30s).
INFO: Uvicorn running on http://127.0.0.1:8005
```

---

### 7. 📱 Flutter Web App (Port 8080)

```bash
cd flutter_app
flutter pub get
flutter run -d chrome --web-port 8080
```

App opens automatically in Chrome at `http://localhost:8080`.

---

## 🧑‍💻 Quick-Start Script (All services in parallel)

Save as `start_all.sh` in the project root and run `bash start_all.sh`:

```bash
#!/bin/bash
echo "Starting Smart City services..."

# 1. Ingestion Engine
cd core_modules/IngestionEngine
source .ingvenv/bin/activate
uvicorn main:app --port 8000 &
cd ../..

# 2. Persistent Middleware
cd core_modules/PersistentMiddleware
source .pmvenv/bin/activate
uvicorn main:app --port 8001 &
cd ../..

# 3. UserService
cd core_modules/UserService
source .usvenv/bin/activate
python seed_db.py 2>/dev/null
uvicorn main:app --port 8003 &
cd ../..

# 4. Energy Engine
cd core_modules/EnergyManagementEngine
source .emevenv/bin/activate
uvicorn main:app --port 8004 &
cd ../..

# 5. EHS Engine
cd core_modules/EHSEngine
source .ehsvenv/bin/activate
uvicorn main:app --port 8005 &
cd ../..

# 6. Simulator
cd IOTDataGenerator
source .simvenv/bin/activate
python simulator/main.py &
cd ..

echo "All services started. Flutter: cd flutter_app && flutter run -d chrome --web-port 8080"
wait
```

---

## 📖 API Documentation

Once running, each service exposes OpenAPI Swagger UI:

| Service | Swagger URL |
|---|---|
| Ingestion Engine | http://127.0.0.1:8000/docs |
| Persistent Middleware | http://127.0.0.1:8001/docs |
| UserService | http://127.0.0.1:8003/docs |
| Energy Engine | http://127.0.0.1:8004/docs |
| EHS Engine | http://127.0.0.1:8005/docs |
