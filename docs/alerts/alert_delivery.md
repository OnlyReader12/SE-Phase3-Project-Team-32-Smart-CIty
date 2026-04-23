# 📡 Alert Delivery — Channels, Cooldowns & Deduplication

This document covers how alerts are physically delivered to each recipient across three channels: **In-App**, **SMS (Twilio)**, and **Email (SendGrid)**.

---

## Delivery Channels

### 1. 📱 In-App (Flutter — always on)

Every alert that passes routing is stored in the `alerts` table and becomes visible in the Flutter app. The app polls `GET /dashboard/alerts` on UserService every 30 seconds.

**How it works:**
- Flutter polls `GET /alerts/my` (returns alerts scoped to the logged-in user's role)
- The alert feed shows a red badge count on the bottom nav
- Tapping an alert marks it `ACKNOWLEDGED`
- Resolved alerts move to "History" tab

**No additional setup required.** This is always active.

---

### 2. 📱 SMS (Twilio) — Opt-In, Critical Only

**Who gets it:**
- Residents: only if `subscription.alert_sms == true`
- Servicers: automatically for `CRITICAL` domain alerts on their assigned nodes
- Managers: configurable

**Rate limiting:**
- Max **3 SMS per user per hour** — prevents runaway costs
- Despite cooldown on DB, Twilio sending has an independent rate limit
- INFO severity alerts are never sent via SMS

**Message format:**
```
🚨 CRITICAL — Smart City Alert
Zone: BLK-A | Domain: Water
Pump WATER-PUMP-003 is DRY RUNNING (flow=0.5 LPM).
Check immediately.
```

**Config required:** `.env` file in UserService:
```
TWILIO_ACCOUNT_SID=ACxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxx
TWILIO_FROM_NUMBER=+1XXXXXXXXXX
```

---

### 3. 📧 Email (SendGrid) — Opt-In, Warning+

**Who gets it:**
- Residents: only if `subscription.alert_email == true`
- Managers: all `WARNING` and `CRITICAL` alerts
- Servicers: assignment alerts (new task, overdue)

**Severity filter:** INFO alerts are never emailed.

**Email subjects by severity:**
```
⚠️ [WARNING] Water quality degraded in Library Zone
🚨 [CRITICAL] DRY RUN detected — Pump offline
ℹ️ [ASSIGNMENT] New task assigned: Inspect AC-UNIT-007
```

**Rate limiting:**
- Daily email digest option for Managers (batch all INFOs into one morning email)
- Individual email for WARNING/CRITICAL

**Config required:**
```
SENDGRID_API_KEY=SG.xxxxxxxx
EMAIL_FROM=alerts@smartcity.local
```

---

## Deduplication Logic

The same alert cannot fire repeatedly from the same source. Two-layer deduplication:

### Layer 1 — DB Cooldown Check (in AlertService)

```python
COOLDOWN_SECONDS = {
    "DOMAIN":     300,   # 5 min
    "NODE":       600,   # 10 min
    "SYSTEM":     900,   # 15 min
    "ASSIGNMENT": 0,     # no cooldown
    "ACTUATOR":   0,     # audit log — no cooldown
}

def is_within_cooldown(alert_type, rule_id, node_id, db):
    threshold = datetime.utcnow() - timedelta(seconds=COOLDOWN_SECONDS[alert_type])
    return db.query(Alert).filter(
        Alert.rule_id   == rule_id,
        Alert.node_id   == node_id,
        Alert.alert_type == alert_type,
        Alert.created_at >= threshold,
        Alert.resolved  == False,
    ).first() is not None
```

If `is_within_cooldown` returns `True` → **the alert is silently dropped**.

### Layer 2 — SMS Rate Limiter (in TwilioService)

```python
# In-memory per-user SMS counter, resets every hour
_sms_count: dict[str, int] = defaultdict(int)
_sms_reset_at: datetime = datetime.utcnow() + timedelta(hours=1)

def send_sms_safe(user_id, phone, message):
    global _sms_reset_at
    if datetime.utcnow() > _sms_reset_at:
        _sms_count.clear()
        _sms_reset_at = datetime.utcnow() + timedelta(hours=1)
    
    if _sms_count[user_id] >= 3:
        logger.warning(f"SMS rate limit hit for {user_id}")
        return
    
    _sms_count[user_id] += 1
    twilio_client.messages.create(to=phone, from_=FROM, body=message)
```

---

## Channel Decision Matrix (per recipient)

```
┌────────────────────────────────────────────────────────────────────────┐
│  For each recipient determined by routing:                             │
│                                                                        │
│  1. IN-APP  ─── Always ✅ (all roles, all severities)                  │
│                                                                        │
│  2. SMS     ─── if severity == CRITICAL                                │
│                  AND (sub.alert_sms OR role == SERVICER)               │
│                  AND user.phone_number exists                           │
│                  AND not rate-limited (< 3/hour)                       │
│                                                                        │
│  3. EMAIL   ─── if severity in [WARNING, CRITICAL]                     │
│                  AND (sub.alert_email OR role == MANAGER)              │
│                  AND not daily-digest mode (for INFO)                  │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Delivery Log

Every delivery attempt (success or fail) is logged to a `AlertDeliveryLog` table:

```sql
CREATE TABLE alert_delivery_logs (
  id           TEXT PRIMARY KEY,
  alert_id     TEXT,          -- FK → alerts.id
  user_id      TEXT,          -- recipient
  channel      TEXT,          -- 'in_app' | 'sms' | 'email'
  status       TEXT,          -- 'sent' | 'failed' | 'rate_limited'
  attempted_at DATETIME,
  error_msg    TEXT           -- if failed
);
```

This gives Managers full observability: "Was John notified? Via what channel? Did it succeed?"

---

## Flutter In-App Notification UX Flow

```
1. Flutter polls GET /alerts/my  (every 30s)
   ↓
2. Badge count updates on nav bar (red dot)
   ↓
3. User opens Alert Feed:
   - CRITICAL: red card with pulsing border
   - WARNING:  amber card
   - INFO:     blue card
   ↓
4. User taps card → opens detail sheet
   - Shows: message, zone, node, time, severity
   - Button: [Mark as Acknowledged]
   ↓
5. PUT /alerts/{id}/acknowledge
   ↓
6. Card moves to History tab (greyed out)
```
