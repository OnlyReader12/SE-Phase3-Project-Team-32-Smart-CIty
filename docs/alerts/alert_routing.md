# 🗺️ Alert Routing — Who Receives Which Alert

This document defines the exact routing rules for every alert type. The AlertService in UserService applies these rules to determine the recipient list for every incoming alert.

---

## Routing Principles

1. **Residents** receive alerts only if the alert's `zone_id` and `domain` match their subscription.
2. **Servicers** receive alerts only if the alert's `node_id` is in their active assignments.
3. **Analysts** receive NO personal alert delivery (no SMS/email). They see all alerts in read-only via API.
4. **Managers** receive ALL alerts across all types. They are the always-on recipients.

---

## Routing Matrix

| Alert Type | RESIDENT | ANALYST | SERVICER | MANAGER |
|---|---|---|---|---|
| `DOMAIN` — Subscribed zone+domain | ✅ In-App + channel | 📊 Read-only | If node is assigned | ✅ Always |
| `DOMAIN` — Outside subscription | ❌ | 📊 Read-only | If node is assigned | ✅ Always |
| `NODE` — Offline/Online | If node in their zone | 📊 Read-only | If node is assigned | ✅ Always |
| `ASSIGNMENT` — New task | ❌ | ❌ | ✅ This servicer only | ✅ Always |
| `ASSIGNMENT` — Status change | ❌ | ❌ | ✅ Involved servicer | ✅ Manager who assigned |
| `ASSIGNMENT` — Overdue | ❌ | ❌ | ✅ Assigned servicer | ✅ All managers |
| `ACTUATOR` — Audit | ❌ | ❌ | If their node | ✅ Always |
| `SYSTEM` | ❌ | ❌ | ❌ | ✅ Always |

---

## Role-Specific Routing Logic

### 🏠 RESIDENT — Subscription-Gated Routing

A Resident receives a `DOMAIN` or `NODE` alert **only if all conditions are met**:

```
RECEIVE if:
  alert.zone_id ∈ subscription.zone_ids
  AND alert.domain ∈ subscription.engine_types
  AND subscription.alert_in_app == true  (always for in-app)
  AND (subscription.alert_sms == true)   (for SMS delivery)
  AND (subscription.alert_email == true) (for email delivery)
```

**Example:**
- Resident subscribed to `zone_ids: ["BLK-A"]`, `engine_types: ["energy"]`
- Alert: `zone_id: "BLK-A"`, `domain: "energy"` → ✅ **DELIVERED**
- Alert: `zone_id: "LIB"`, `domain: "energy"` → ❌ **BLOCKED** (zone mismatch)
- Alert: `zone_id: "BLK-A"`, `domain: "ehs"` → ❌ **BLOCKED** (domain mismatch)

> Residents never receive `ASSIGNMENT`, `ACTUATOR`, or `SYSTEM` alerts.

---

### 🛠️ SERVICER — Assignment-Gated Routing

A Servicer receives a `DOMAIN` or `NODE` alert **only if**:

```
RECEIVE if:
  ∃ assignment WHERE assignment.node_id == alert.node_id
  AND assignment.servicer_id == this_servicer.id
  AND assignment.status IN ['ASSIGNED', 'IN_PROGRESS']
```

Servicers always receive:
- Their own `ASSIGNMENT` alerts (new task, overdue)
- `ACTUATOR` alerts for their assigned nodes (if someone else toggled it)

**Example:**
- Servicer has assignment for `AC-UNIT-007` in `BLK-B`
- Alert: `node_id: "AC-UNIT-007"` → ✅ **DELIVERED**
- Alert: `node_id: "WATER-PUMP-003"` (not assigned) → ❌ **BLOCKED**

> Servicers do NOT receive `SYSTEM` alerts.

---

### 📈 ANALYST — Read-Only Observer

Analysts have **no subscription-based delivery**. They are read-only monitors.

- They can query `GET /alerts` on UserService or directly on Engine APIs.
- They receive no SMS or email delivery.
- They can adjust thresholds (which changes what future alerts get raised).
- They do not appear in the `recipients` list of any alert.

> This is intentional: Analysts process data, they don't respond to incidents.

---

### 👑 MANAGER — Always-On Recipient

Managers receive every alert regardless of zone, domain, or type.

```
RECEIVE if: user.role == MANAGER
```

In addition:
- Managers receive **aggregated summary** alerts if configured (e.g., daily digest via email).
- Managers see the full `recipients` list of each alert (who else got notified).
- Managers receive `ACTUATOR` audit events for any device in the city.

---

## Routing Algorithm (Pseudocode)

```python
def route_alert(alert: AlertPayload, db: Session) -> list[User]:
    recipients = []

    # 1. Always add all Managers
    managers = db.query(User).filter(User.role == Role.MANAGER, User.is_active == True).all()
    recipients.extend(managers)

    # 2. DOMAIN/NODE alerts → match Resident subscriptions
    if alert.alert_type in ['DOMAIN', 'NODE']:
        subs = db.query(Subscription).all()
        for sub in subs:
            zones   = json.loads(sub.zone_ids)
            domains = json.loads(sub.engine_types)
            if alert.zone_id in zones and alert.domain in domains:
                user = db.query(User).get(sub.user_id)
                if user and user.role == Role.RESIDENT:
                    recipients.append((user, sub))  # carry sub for channel prefs

    # 3. DOMAIN/NODE alerts → match Servicer active assignments
    if alert.alert_type in ['DOMAIN', 'NODE'] and alert.node_id:
        assignments = db.query(ServicerAssignment).filter(
            ServicerAssignment.node_id == alert.node_id,
            ServicerAssignment.status.in_(['ASSIGNED', 'IN_PROGRESS'])
        ).all()
        for asgn in assignments:
            user = db.query(User).get(asgn.servicer_id)
            if user and user.is_active:
                recipients.append(user)

    # 4. ASSIGNMENT alerts → direct to target_user_id only
    if alert.alert_type == 'ASSIGNMENT' and alert.target_user_id:
        user = db.query(User).get(alert.target_user_id)
        if user:
            recipients.append(user)

    # 5. Deduplicate
    seen = set()
    return [r for r in recipients if not (r.id in seen or seen.add(r.id))]
```

---

## Channel Decision Per Recipient

After routing determines the recipient list, the channel selector decides how each person gets notified:

```
For each recipient:

  ✅ In-App:  ALWAYS (if alert_in_app in subscription, or always for MANAGER/SERVICER)
  
  ✅ SMS:     if user.phone_number exists
              AND (sub.alert_sms == true OR role == SERVICER and severity == CRITICAL)
              
  ✅ Email:   if sub.alert_email == true OR role == MANAGER
              AND severity in [WARNING, CRITICAL]   (no INFOs by email)
```

---

## Analyst Threshold Change → Alert Sensitivity

When an Analyst changes a threshold via slider:

```
PUT /thresholds/air_quality?key=pm2_5_warning_ugm3&value=15
```

This does NOT create alerts itself. Instead:
- Next engine cycle uses the new threshold.
- More alerts may be raised if threshold is tightened.
- Fewer alerts if threshold is loosened.
- The threshold change itself is logged as an `INFO` system event visible to Managers.
