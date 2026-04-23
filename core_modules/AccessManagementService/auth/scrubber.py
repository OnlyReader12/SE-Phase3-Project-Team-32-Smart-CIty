"""
auth/scrubber.py — Role-Based Data Scrubbing (Strategy Pattern).

Each role gets a different "view" of the data:
  - Admin sees everything
  - Analyst sees all telemetry but no PII
  - Researcher sees 30-day data with PII stripped
  - Maintenance sees only node health/fault data
  - Emergency Responder sees only critical alerts
  - Resident sees nothing (personal data only)

Design Pattern: Strategy Pattern
  The scrubbing function is selected based on the user's role.
"""

from typing import Any, Dict, List, Optional

from auth.rbac import get_role_config, get_allowed_domains


# Fields that contain personally identifiable information
PII_FIELDS = {"email", "phone", "full_name", "address", "ip_address", "mac_address"}

# Fields that are technical/health related (for maintenance view)
HEALTH_FIELDS = {
    "battery_soc_pct", "voltage", "current", "fault_status",
    "grid_temperature_c", "ac_state", "ac_mode", "leak_detected",
    "solar_status", "battery_status", "is_critical",
}


def scrub_telemetry_for_role(
    records: List[Dict[str, Any]],
    role: str,
) -> List[Dict[str, Any]]:
    """
    Filter and scrub telemetry records based on the user's role.
    Returns a new list with sensitive fields removed/filtered.
    """
    config = get_role_config(role)
    allowed_domains = config.get("domains", [])
    can_see_pii = config.get("can_see_pii", False)

    result = []
    for rec in records:
        # Domain filtering — skip records from domains the user can't access
        domain = rec.get("domain", "unknown")
        if allowed_domains and domain not in allowed_domains:
            continue

        # Deep copy to avoid mutating original data
        scrubbed = dict(rec)
        data = dict(scrubbed.get("data", {}))

        # PII scrubbing for non-admin roles
        if not can_see_pii:
            for field in PII_FIELDS:
                if field in data:
                    data[field] = "***REDACTED***"
                if field in scrubbed:
                    scrubbed[field] = "***REDACTED***"

        # Maintenance role: only show health/fault fields
        if role == "maintenance":
            filtered_data = {}
            for k, v in data.items():
                if k in HEALTH_FIELDS or k.startswith("is_") or k.endswith("_status"):
                    filtered_data[k] = v
            # Always keep basic identification
            filtered_data["node_id"] = data.get("node_id", scrubbed.get("node_id"))
            data = filtered_data

        # Emergency responder: only show critical readings
        if role == "emergency_responder":
            if not data.get("is_critical", False):
                continue  # skip non-critical records entirely

        scrubbed["data"] = data
        result.append(scrubbed)

    return result


def scrub_user_for_role(
    user: Dict[str, Any],
    viewer_role: str,
) -> Dict[str, Any]:
    """Scrub user record based on viewer's role."""
    config = get_role_config(viewer_role)

    # Only admin can see full user records
    if config.get("can_see_pii", False):
        # Still strip password hash
        safe = dict(user)
        safe.pop("password_hash", None)
        return safe

    # Everyone else gets minimal info
    return {
        "username": user.get("username"),
        "role": user.get("role"),
        "is_active": user.get("is_active", True),
    }


def build_role_dashboard_stats(
    role: str,
    domain_stats: Dict[str, Any],
    alerts: List[Dict[str, Any]],
    total_users: int,
) -> Dict[str, Any]:
    """Build role-specific dashboard statistics."""
    allowed_domains = get_allowed_domains(role)
    config = get_role_config(role)

    # Filter domain stats to allowed domains
    visible_stats = {}
    total_records = 0
    total_nodes = 0
    for domain, stats in domain_stats.items():
        if allowed_domains and domain not in allowed_domains:
            continue
        visible_stats[domain] = stats
        total_records += stats.get("total_records", 0)
        total_nodes += stats.get("unique_nodes", 0)

    # Filter alerts
    visible_alerts = []
    for alert in alerts:
        if allowed_domains and alert.get("domain", "") not in allowed_domains:
            continue
        visible_alerts.append(alert)

    critical_alerts = sum(1 for a in visible_alerts if a.get("severity") == "CRITICAL")

    dashboard_stats = {
        "total_records": total_records,
        "total_nodes": total_nodes,
        "total_domains": len(visible_stats),
        "domain_breakdown": visible_stats,
        "total_alerts": len(visible_alerts),
        "critical_alerts": critical_alerts,
    }

    # Admin-specific stats
    if config.get("can_manage_users"):
        dashboard_stats["total_users"] = total_users

    return dashboard_stats
