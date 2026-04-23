# 🔄 Alert Lifecycle — State Machine

Every alert in the system moves through a defined state machine. This document describes each state, the valid transitions, and what triggers them.

---

## State Diagram

```
                    ┌──────────────────────┐
      Engine Rule   │                      │
      Node Offline  │        RAISED        │◄──── cooldown pass + condition re-occurs
      Toggle Event  │                      │
                    └──────────┬───────────┘
                               │ persist to DB
                               │ route to recipients
                               ▼
                    ┌──────────────────────┐
                    │                      │
                    │      DELIVERED       │  in-app stored
                    │                      │  SMS/Email sent (if opted in)
                    └──────────┬───────────┘
                               │
              ┌────────────────┼─────────────────────────┐
              │                │                         │
              ▼                ▼                         ▼
    User taps     24h passes        Condition clears
    Acknowledge   (auto-ack)        (node back online)
              │                │                         │
              ▼                ▼                         ▼
        ┌──────────┐    ┌──────────┐            ┌──────────────┐
        │          │    │          │            │              │
        │  ACK'D   │    │ AUTO-ACK │            │   RESOLVED   │
        │          │    │          │            │ (auto or man.)│
        └──────────┘    └──────────┘            └──────────────┘
              │                │
              └─── Escalate? ──┘
                       │
               If severity grew
               (WARNING→CRITICAL)
                       │
                       ▼
                ┌────────────┐
                │ ESCALATED  │
                │ (new alert)│
                └────────────┘
```

---

## States

| State | DB Value | Meaning |
|---|---|---|
| `RAISED` | `status: RAISED` | Alert generated, not yet persisted |
| `DELIVERED` | `status: DELIVERED` | Stored in DB, channels dispatched |
| `ACKNOWLEDGED` | `acknowledged: true` | User manually confirmed they saw it |
| `AUTO_ACKNOWLEDGED` | `auto_acked: true` | System auto-acked after 24h |
| `RESOLVED` | `resolved: true, resolved_at: <ts>` | Condition that caused the alert is gone |
| `ESCALATED` | New alert row with `escalated_from: <id>` | Alert re-raised at higher severity |
| `SUPPRESSED` | Never stored in DB | Cooldown prevented storage |

---

## Transitions

### RAISED → DELIVERED
**Trigger:** AlertService receives alert from engine or internal event.  
**Actions:**
1. Check cooldown — if within cooldown window → `SUPPRESSED` (no DB entry)
2. Persist to `alerts` table with `status: DELIVERED`
3. Run routing algorithm → determine recipients
4. Dispatch in-app + SMS/Email

---

### DELIVERED → ACKNOWLEDGED
**Trigger:** User calls `PUT /alerts/{id}/acknowledge` from Flutter app.  
**Who can ACK:**
- The alert must be in the user's "my alerts" feed (they are a recipient)
- Managers can ACK any alert
**Actions:**
1. Set `acknowledged = true`
2. Set `acknowledged_by = user.id`
3. Alert disappears from the "active" in-app feed
4. Still visible in history

---

### DELIVERED → AUTO-ACKNOWLEDGED
**Trigger:** Background job runs every hour. Any alert older than 24h with `acknowledged = false` is auto-acked.  
**Purpose:** Prevent permanent "red badge" buildup for older, non-actioned alerts.

---

### DELIVERED → RESOLVED
**Trigger:** Can be:
- **Automatic:** A follow-up engine cycle produces no alert for the same `(rule_id, node_id)` — condition has cleared.
- **Manual:** Manager or Servicer calls `PUT /alerts/{id}/resolve`.

**Actions:**
1. Set `resolved = true`, `resolved_at = now()`
2. Alert moves to history tab in Flutter

---

### WARNING → CRITICAL (Escalation)
**Trigger:** A `WARNING` alert exists that has not been `ACKNOWLEDGED` within `escalation_minutes` (default: 30 min).  
AND the same rule still fires in the next engine cycle.  
**Actions:**
1. Create a new alert row with `severity: CRITICAL`
2. Set `escalated_from = <original alert id>`
3. Re-route and re-dispatch — this wakes up channels (new SMS sent)
4. Original `WARNING` is auto-resolved

---

## Cooldown Rules

Cooldown prevents alert storms when the same bad condition persists.

```
SUPPRESS if:
  ∃ alert in DB WHERE:
    alert.rule_id == new_alert.rule_id
    AND alert.node_id == new_alert.node_id
    AND alert.created_at > (NOW - cooldown_seconds)
    AND alert.resolved == false
```

| Alert Type | Default Cooldown |
|---|---|
| `DOMAIN` (engine rule) | 5 minutes |
| `NODE` (offline) | 10 minutes |
| `ASSIGNMENT` | No cooldown (one-time events) |
| `ACTUATOR` | No cooldown (audit log) |
| `SYSTEM` | 15 minutes |

---

## Alert Lifecycle in the DB Schema

The existing `Alert` table gets these additions to support the full lifecycle:

```sql
ALTER TABLE alerts ADD COLUMN alert_type   TEXT    DEFAULT 'DOMAIN';   -- DOMAIN|NODE|ASSIGNMENT|ACTUATOR|SYSTEM
ALTER TABLE alerts ADD COLUMN status       TEXT    DEFAULT 'DELIVERED'; -- DELIVERED|RESOLVED
ALTER TABLE alerts ADD COLUMN rule_id      TEXT;                        -- e.g. 'water_safety'
ALTER TABLE alerts ADD COLUMN auto_acked   BOOLEAN DEFAULT FALSE;
ALTER TABLE alerts ADD COLUMN ack_by       TEXT;                        -- user.id who acknowledged
ALTER TABLE alerts ADD COLUMN resolved     BOOLEAN DEFAULT FALSE;
ALTER TABLE alerts ADD COLUMN resolved_at  DATETIME;
ALTER TABLE alerts ADD COLUMN escalated_from TEXT;                      -- parent alert id
ALTER TABLE alerts ADD COLUMN target_user_id TEXT;                      -- direct recipient (ASSIGNMENT type)
```
