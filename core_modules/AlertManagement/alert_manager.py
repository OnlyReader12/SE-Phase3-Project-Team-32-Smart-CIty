"""
alert_manager.py — Microservice 3: Alert Manager

Port: 8008

Receives emergency alerts from the Ingestion Engine, stores them,
and dispatches email notifications to affected users.

Endpoints:
  POST /alert           — Receive alert (from engine)
  GET  /alerts          — List recent alerts
  GET  /alerts/stats    — Alert statistics
  GET  /health          — Service health
"""

import json, os, sys, time, smtplib, threading
from datetime import datetime
from typing import Any, Dict, List, Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from collections import deque

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_ACCESS_MGR_DIR = os.path.join(_BASE_DIR, "..", "AccessManagementService")
sys.path.insert(0, _BASE_DIR)
sys.path.insert(0, _ACCESS_MGR_DIR)

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from database.connection import DatabaseManager

# Load .env
def load_env():
    env_path = os.path.join(_BASE_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

load_env()

SERVER_PORT = int(os.getenv("ALERT_MANAGER_PORT", "8008"))
db = DatabaseManager(os.path.join(_BASE_DIR, "..", "AccessManagementService", "smartcity.db"))

app = FastAPI(
    title="Smart City Alert Manager",
    description="Microservice 3: Emergency alert dispatch via email",
    version="1.0.0",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ═══════════════════════════════════════════
# Alert Storage (in-memory + DB)
# ═══════════════════════════════════════════
RECENT_ALERTS = deque(maxlen=200)
ALERT_STATS = {"total": 0, "emergency": 0, "warning": 0, "emails_sent": 0, "emails_failed": 0}

# Contact routing: domain → env keys
CONTACT_ROUTING = {
    "energy": [
        ("ADMIN_EMAIL", "ADMIN_PHONE"),
        ("ENERGY_MANAGER_EMAIL", "ENERGY_MANAGER_PHONE"),
    ],
    "ehs": [
        ("ADMIN_EMAIL", "ADMIN_PHONE"),
        ("EHS_MANAGER_EMAIL", "EHS_MANAGER_PHONE"),
    ],
}


@app.on_event("startup")
async def startup():
    db.initialize()
    # Ensure alerts table exists
    conn = db.get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alert_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id TEXT NOT NULL,
            domain TEXT NOT NULL,
            severity TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            message TEXT NOT NULL,
            data_json TEXT,
            dispatched_to TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    count = db.fetchone("SELECT COUNT(*) as c FROM alert_log")
    ALERT_STATS["total"] = count["c"]
    print(f"[ALERT MGR] Started on port {SERVER_PORT} | {count['c']} alerts in DB")


# ═══════════════════════════════════════════
# Models
# ═══════════════════════════════════════════

class AlertPayload(BaseModel):
    node_id: str
    domain: str
    severity: str  # EMERGENCY, WARNING, INFO
    alert_type: str  # aqi_high, battery_low, grid_overload, etc.
    message: str
    data: Dict[str, Any] = {}
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())


# ═══════════════════════════════════════════
# Email & SMS Dispatch
# ═══════════════════════════════════════════

def _send_email(to_email: str, subject: str, body: str):
    """Send email via SMTP. Non-blocking (threaded)."""
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASSWORD", "")
    smtp_from = os.getenv("SMTP_FROM", smtp_user)

    if not smtp_host or not smtp_user or smtp_pass == "your-app-password-here":
        print(f"  [EMAIL SKIP] To: {to_email} | Subject: {subject} (SMTP not configured)")
        ALERT_STATS["emails_failed"] += 1
        return False

    try:
        msg = MIMEMultipart()
        msg["From"] = smtp_from
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "html"))

        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)

        print(f"  [EMAIL SENT] To: {to_email} | Subject: {subject}")
        ALERT_STATS["emails_sent"] += 1
        return True
    except Exception as e:
        print(f"  [EMAIL FAIL] To: {to_email} | Error: {e}")
        ALERT_STATS["emails_failed"] += 1
        return False

def _send_sms(to_phone: str, body: str):
    """Send SMS via Twilio. Non-blocking (threaded)."""
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_phone = os.getenv("TWILIO_FROM_PHONE")

    if not account_sid or not auth_token or not from_phone or account_sid == "your-twilio-sid":
        print(f"  [SMS SKIP] To: {to_phone} | Body: {body} (Twilio not configured)")
        ALERT_STATS["sms_failed"] = ALERT_STATS.get("sms_failed", 0) + 1
        return False

    try:
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        message = client.messages.create(
            body=body,
            from_=from_phone,
            to=to_phone
        )
        print(f"  [SMS SENT] To: {to_phone} | SID: {message.sid}")
        ALERT_STATS["sms_sent"] = ALERT_STATS.get("sms_sent", 0) + 1
        return True
    except Exception as e:
        print(f"  [SMS FAIL] To: {to_phone} | Error: {e}")
        ALERT_STATS["sms_failed"] = ALERT_STATS.get("sms_failed", 0) + 1
        return False


def _dispatch_alert(alert: dict):
    """Route alert to appropriate contacts and send email & SMS."""
    domain = alert["domain"]
    severity = alert["severity"]
    contacts = CONTACT_ROUTING.get(domain, CONTACT_ROUTING.get("energy", []))

    # For EMERGENCY, also notify admin
    if severity == "EMERGENCY":
        admin_email = os.getenv("ADMIN_EMAIL", "")
        admin_phone = os.getenv("ADMIN_PHONE", "")
        if admin_email or admin_phone:
            contacts = list(contacts)
            if ("ADMIN_EMAIL", "ADMIN_PHONE") not in contacts:
                contacts.insert(0, ("ADMIN_EMAIL", "ADMIN_PHONE"))

    dispatched_to = []
    severity_emoji = "🔴" if severity == "EMERGENCY" else "🟡"

    subject = f"{severity_emoji} [{severity}] Smart City Alert: {alert['alert_type']} — {alert['node_id']}"
    html_body = f"""
    <html><body style="font-family:Arial;background:#0a0e1a;color:#e2e8f0;padding:20px">
    <h2 style="color:{'#ef4444' if severity=='EMERGENCY' else '#f59e0b'}">{severity_emoji} {severity} Alert</h2>
    <table style="border-collapse:collapse">
        <tr><td style="padding:5px 15px 5px 0;color:#94a3b8">Node:</td><td><strong>{alert['node_id']}</strong></td></tr>
        <tr><td style="padding:5px 15px 5px 0;color:#94a3b8">Domain:</td><td>{alert['domain']}</td></tr>
        <tr><td style="padding:5px 15px 5px 0;color:#94a3b8">Type:</td><td>{alert['alert_type']}</td></tr>
        <tr><td style="padding:5px 15px 5px 0;color:#94a3b8">Message:</td><td>{alert['message']}</td></tr>
        <tr><td style="padding:5px 15px 5px 0;color:#94a3b8">Time:</td><td>{alert.get('timestamp','')}</td></tr>
    </table>
    <p style="margin-top:15px;color:#64748b;font-size:12px">— Smart City Alert Manager</p>
    </body></html>
    """
    
    sms_body = f"[{severity}] {alert['alert_type']} on {alert['node_id']}: {alert['message']}"

    for email_key, phone_key in contacts:
        email = os.getenv(email_key, "")
        phone = os.getenv(phone_key, "")
        
        if email:
            dispatched_to.append(email)
            threading.Thread(target=_send_email, args=(email, subject, html_body), daemon=True).start()
        
        if phone:
            dispatched_to.append(phone)
            threading.Thread(target=_send_sms, args=(phone, sms_body), daemon=True).start()

    return dispatched_to


# ═══════════════════════════════════════════
# Routes
# ═══════════════════════════════════════════

@app.get("/", tags=["info"])
def root():
    return {"service": "Smart City Alert Manager", "version": "1.0.0", "port": SERVER_PORT}

@app.get("/health", tags=["info"])
def health():
    return {
        "status": "healthy", "service": "AlertManager",
        "port": SERVER_PORT, "stats": ALERT_STATS,
        "timestamp": datetime.now().isoformat(),
    }

@app.post("/alert", tags=["alerts"])
def receive_alert(payload: AlertPayload):
    """Receive an alert from the ingestion engine, store it, and dispatch."""
    alert = {
        "node_id": payload.node_id,
        "domain": payload.domain,
        "severity": payload.severity,
        "alert_type": payload.alert_type,
        "message": payload.message,
        "data": payload.data,
        "timestamp": payload.timestamp,
    }

    # Store in DB
    try:
        dispatched = _dispatch_alert(alert)
        db.execute(
            "INSERT INTO alert_log (node_id, domain, severity, alert_type, message, data_json, dispatched_to, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (payload.node_id, payload.domain, payload.severity, payload.alert_type,
             payload.message, json.dumps(payload.data), json.dumps(dispatched), payload.timestamp)
        )
    except Exception as e:
        print(f"  [ALERT ERR] {e}")
        dispatched = []

    # In-memory
    alert["dispatched_to"] = dispatched
    RECENT_ALERTS.appendleft(alert)
    ALERT_STATS["total"] += 1
    if payload.severity == "EMERGENCY":
        ALERT_STATS["emergency"] += 1
    else:
        ALERT_STATS["warning"] += 1

    sev_icon = "🔴" if payload.severity == "EMERGENCY" else "🟡"
    print(f"  {sev_icon} [{payload.severity}] {payload.node_id}: {payload.message} → {dispatched}")

    return {
        "status": "received",
        "alert_id": ALERT_STATS["total"],
        "dispatched_to": dispatched,
        "severity": payload.severity,
    }

@app.get("/alerts", tags=["alerts"])
def list_alerts(limit: int = 50):
    """Recent alerts from DB."""
    rows = db.fetchall(
        "SELECT * FROM alert_log ORDER BY id DESC LIMIT ?", (limit,)
    )
    return {"count": len(rows), "alerts": rows, "stats": ALERT_STATS}

@app.get("/alerts/stats", tags=["alerts"])
def alert_stats():
    return ALERT_STATS

@app.get("/alerts/recent", tags=["alerts"])
def recent_alerts(limit: int = 20):
    """Recent alerts from memory (faster)."""
    alerts = list(RECENT_ALERTS)[:limit]
    return {"count": len(alerts), "alerts": alerts, "stats": ALERT_STATS}


# ═══════════════════════════════════════════
# Entry Point
# ═══════════════════════════════════════════

if __name__ == "__main__":
    print(f"\n{'='*60}")
    print(f"  Alert Manager v1.0 — Port {SERVER_PORT}")
    print(f"{'='*60}\n")
    uvicorn.run(app, host="0.0.0.0", port=SERVER_PORT)
