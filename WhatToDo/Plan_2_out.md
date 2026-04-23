# Plan 2 Verification — Test Suite for UserService

This document outlines the testing strategy for the `UserService` (:8003) across all four user roles. You can use tools like Postman, Insomnia, or simple `curl` commands to verify these.

---

## 🔐 Auth & Generic Tests (All Users)

| Test Case | Method | Endpoint | Expectation |
|---|---|---|---|
| **Self-Registration** | POST | `/auth/register` | 201 Created. Returns JWTs. Role is RESIDENT. |
| **Login** | POST | `/auth/login` | 200 OK. Returns JWT access + refresh. |
| **Get My Profile** | GET | `/auth/me` | 200 OK. Returns user details. |
| **Token Refresh** | POST | `/auth/refresh` | 200 OK. New access token issued. |
| **Access Unauth** | GET | `/auth/me` | 401 Unauthorized if no Bearer token. |

---

## 🏠 User: RESIDENT

| Test Case | Method | Endpoint | Expectation |
|---|---|---|---|
| **Create Sub** | POST | `/resident/subscriptions` | 201 Created. Input: `{"zone_ids":["BLK-A"], "engine_types":["energy"]}`. |
| **List Subs** | GET | `/resident/subscriptions` | 200 OK. List of My subscriptions. |
| **Resident Dash** | GET | `/dashboard/resident` | 200 OK. Returns summary + alerts for the user's zones. |
| **Resident Alerts**| GET | `/dashboard/alerts` | 200 OK. Returns unacknowledged alerts for user's zones. |
| **Actuator Control**| PATCH| `/actuators/{node_id}/command`| 200 OK if node is in a subscribed zone/domain. |
| **Unauthorized** | POST | `/manager/create-user` | **403 Forbidden**. Residents cannot create users. |

---

## 🛠️ User: SERVICER (Technician)

| Test Case | Method | Endpoint | Expectation |
|---|---|---|---|
| **My Assignments** | GET | `/servicer/assignments` | 200 OK. Returns nodes assigned TO this technician. |
| **Update Status** | PUT | `/servicer/assignments/{id}/status`| 200 OK. Input: `{"status": "IN_PROGRESS"}`. |
| **Update Notes** | PUT | `/servicer/assignments/{id}/notes` | 200 OK. Field notes persisted. |
| **Servicer Dash** | GET | `/dashboard/servicer` | 200 OK. Map-ready node health list for assigned nodes. |
| **Actuator Control**| PATCH| `/actuators/{node_id}/command`| 200 OK if node is in their active assignments. |

---

## 📈 User: ANALYST

| Test Case | Method | Endpoint | Expectation |
|---|---|---|---|
| **Analyst Dash** | GET | `/dashboard/analyst` | 200 OK. Aggregated trends and moving-average predictions. |
| **Cross-Access** | GET | `/dashboard/resident` | **403 Forbidden**. Analysts have no zone subscriptions. |
| **No Control** | PATCH| `/actuators/{node_id}/command`| **403 Forbidden**. Analysts are read-only. |

---

## 👑 User: MANAGER

| Test Case | Method | Endpoint | Expectation |
|---|---|---|---|
| **Create Team** | POST | `/manager/create-user` | 201 Created. Manager creates ANALYST or SERVICER. |
| **List Team** | GET | `/manager/team` | 200 OK. Returns only users CRATED by this manager. |
| **Assign Node** | POST | `/manager/assignments` | 201 Created. Link node `AC-UNIT-001` to a Servicer. |
| **Manager Dash** | GET | `/dashboard/manager/team` | 200 OK. Overview of team status and their assignments. |
| **Alert History** | GET | `/alerts/history` | 200 OK. Full log of all city alerts. |
| **Full Control** | PATCH| `/actuators/{node_id}/command`| 200 OK for ANY node in the city. |

---

## 🚨 System & Alerting (Internal)

| Test Case | Method | Endpoint | Expectation |
|---|---|---|---|
| **Post Alert** | POST | `/alerts/internal` | 202 Accepted. Requires `X-API-Key` header. |
| **Fanout Check** | | | Verify terminal logs for `[Twilio] SMS sent` or `[SendGrid] Email sent`. |
| **Acknowledge** | PUT | `/alerts/{id}/acknowledge` | 200 OK. Alert moves out of active resident feed. |

---

## 🕹️ Actuator Confirmation Flow

1. **User Request**: Flutter calls `PATCH /actuators/LIGHT-001/command`.
2. **UserService**: Checks DB permissions and forwards to `POST :8000/api/actuator/LIGHT-001/command`.
3. **IngestionEngine**: Returns `{"accepted": true}`.
4. **IoT Simulator**: When it next sends a WS message, it receives the command in the ACK: `{"ack":"ok", "command": {"state":"ON"}}`.
5. **Confirmation**: Next telemetry from node shows `"state": "ON"`.

---

## 🧪 Quick `curl` Smoke Test (Example)

```bash
# 1. Login to get token
export TOKEN=$(curl -X POST http://127.0.0.1:8003/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@smartcity.local", "password":"password123"}' | jq -r .access_token)

# 2. Check profile
curl http://127.0.0.1:8003/auth/me -H "Authorization: Bearer $TOKEN"

# 3. Check health
curl http://127.0.0.1:8003/health
```
