# 🚨 Smart City Alert System — Overview

This document is the root reference for the alert system design. It covers **what**, **why**, **who**, and **how** across every alert type in the Smart City system.

---

## 🎯 Design Goals

1. **No alert spam** — Same alert from the same node cannot repeat within a cooldown window.
2. **Right person, right channel** — Each role only receives alerts relevant to their context.
3. **Full lifecycle** — Every alert is `RAISED → DELIVERED → ACKNOWLEDGED → RESOLVED`.
4. **Multi-source** — Alerts come from Engine rules, device toggles, assignment events, node offline events.
5. **Analyst-adjustable** — Threshold-based alert sensitivity can be changed live via slider.
6. **Auditable** — Every alert delivery is logged. Who got it, when, via which channel.

---

## 📚 Document Index

| Document | What it covers |
|---|---|
| [alert_sources.md](alert_sources.md) | All events that can trigger an alert |
| [alert_routing.md](alert_routing.md) | Which role receives which alert type |
| [alert_lifecycle.md](alert_lifecycle.md) | State machine: RAISED → RESOLVED |
| [alert_delivery.md](alert_delivery.md) | In-app, SMS, Email channels + cooldown/dedup |
| [alert_implementation.md](alert_implementation.md) | How to implement all of this in UserService code |

---

## 🗂️ Alert Type Taxonomy

| Category | Code | Examples |
|---|---|---|
| **Domain** | `DOMAIN` | Rules triggered by Engines (PM2.5, dry run, AC waste) |
| **Node** | `NODE` | Node went OFFLINE, came back ONLINE, no heartbeat |
| **Assignment** | `ASSIGNMENT` | New task assigned, overdue, status changed |
| **Actuator** | `ACTUATOR` | Someone toggled a device ON/OFF (audit) |
| **System** | `SYSTEM` | Service down, RabbitMQ disconnected |

---

## 🏗️ System-Level Data Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         ALERT SOURCES                                   │
│                                                                         │
│  EnergyEngine   EHSEngine                                               │
│  (Rules Q1-Q5)  (Rules Q1-Q5)   ──→  POST /internal/alerts [DOMAIN]    │
│                                                                         │
│  Middleware (node heartbeat miss) → POST /internal/alerts [NODE]        │
│                                                                         │
│  UserService (assignment event)   → Internal event bus [ASSIGNMENT]     │
│                                                                         │
│  UserService (actuator toggle)    → Internal audit log [ACTUATOR]       │
└──────────────────────────────────────┬──────────────────────────────────┘
                                       │
                                       ▼
                    ┌──────────────────────────────┐
                    │  AlertService (UserService)   │
                    │                               │
                    │  1. Cooldown check            │
                    │  2. Persist to alerts table   │
                    │  3. Route to recipients       │
                    │  4. Dispatch channels         │
                    └────────────────┬─────────────┘
                                     │
              ┌──────────────────────┼────────────────────┐
              ▼                      ▼                     ▼
       In-App Feed             Twilio SMS            SendGrid Email
    (Flutter polling)      (opt-in, CRITICAL)      (opt-in, digest)
```
