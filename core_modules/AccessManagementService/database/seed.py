"""
database/seed.py — Database Seed Data (v3 — 7 roles, 9 users).

Seeds all reference tables on first run:
  - 7 roles with permissions & domain access
  - 3 domains (energy, ehs, cam) with node types
  - 9 default users (including 3 residents with personal nodes)
  - User-node mapping for residents

Roles: admin, energy_manager, ehs_manager, analyst, maintenance, researcher, resident

Resident Node Mapping:
  - resident_arjun  → R1-SOL-001, R1-MTR-001, R1-BAT-001, R1-AC-001, R1-AQI-001
  - resident_meera  → R2-SOL-001, R2-MTR-001, R2-BAT-001, R2-AC-001, R2-AQI-001
  - resident_kiran  → R3-SOL-001, R3-MTR-001, R3-BAT-001, R3-AC-001, R3-AQI-001
"""

import hashlib
from datetime import datetime

_SALT = "smartcity-salt-v1"

def hash_password(password: str) -> str:
    return hashlib.sha256(f"{_SALT}:{password}".encode()).hexdigest()


# ═══════════════════════════════════════════
# ROLE DEFINITIONS (7 roles)
# ═══════════════════════════════════════════

ROLES = [
    # (role_name, label, icon, can_see_pii, can_manage_users, data_retention_days)
    ("admin",            "System Administrator",    "🛡️", 1, 1, None),
    ("energy_manager",   "Energy Manager",          "⚡",  0, 0, 90),
    ("ehs_manager",      "EHS Manager",             "🌿",  0, 0, 90),
    ("analyst",          "Data Analyst",            "📊",  0, 0, 90),
    ("maintenance",      "Maintenance Engineer",    "🔧",  0, 0, 30),
    ("researcher",       "Researcher",              "🔬",  0, 0, 30),
    ("resident",         "Resident",                "🏠",  0, 0, 7),
]

ROLE_PERMISSIONS = {
    "admin": [
        "telemetry.read", "telemetry.write",
        "users.read", "users.write", "users.delete",
        "alerts.read", "alerts.manage",
        "dashboard.full", "config.manage",
        "system.health", "system.logs",
    ],
    "energy_manager": [
        "telemetry.read", "alerts.read", "alerts.manage",
        "dashboard.energy", "config.manage",
    ],
    "ehs_manager": [
        "telemetry.read", "alerts.read", "alerts.manage",
        "dashboard.ehs", "config.manage",
    ],
    "analyst": [
        "telemetry.read", "alerts.read",
        "dashboard.analytics", "ml.predictions",
    ],
    "maintenance": [
        "telemetry.read", "alerts.read",
        "dashboard.health", "system.health",
    ],
    "researcher": [
        "telemetry.read", "dashboard.research",
    ],
    "resident": [
        "telemetry.read", "alerts.read",
        "dashboard.personal", "nodes.manage_own",
    ],
}

ROLE_DOMAINS = {
    "admin":            ["energy", "ehs", "cam", "system"],
    "energy_manager":   ["energy"],
    "ehs_manager":      ["ehs"],
    "analyst":          ["energy", "ehs", "cam"],
    "maintenance":      ["energy", "ehs"],
    "researcher":       ["energy", "ehs"],
    "resident":         ["energy", "ehs"],
}


# ═══════════════════════════════════════════
# DOMAIN & NODE TYPE DEFINITIONS
# ═══════════════════════════════════════════

DOMAINS = [
    ("energy", "Energy Management",               "Solar, battery, grid, AC, occupancy, water metering"),
    ("ehs",    "Environmental Health & Safety",    "Air quality, water quality, noise, weather, soil, radiation"),
    ("cam",    "Crowd & Access Management",        "Crowd density, entrance auth, camera feeds"),
]

NODE_TYPES = {
    "energy": [
        ("solar_panel",       "Solar Panel",          "HTTP",  "watts"),
        ("smart_meter",       "Smart Meter",          "HTTP",  "watts"),
        ("battery_storage",   "Battery Storage",      "HTTP",  "%"),
        ("grid_transformer",  "Grid Transformer",     "HTTP",  "%"),
        ("occupancy_sensor",  "Occupancy Sensor",     "MQTT",  "count"),
        ("water_meter",       "Water Meter",          "MQTT",  "lpm"),
        ("ac_unit",           "AC Unit",              "HTTP",  "watts"),
    ],
    "ehs": [
        ("air_quality",    "Air Quality Station",     "MQTT",  "AQI"),
        ("water_quality",  "Water Quality Probe",     "MQTT",  "pH"),
        ("noise_monitor",  "Noise Level Monitor",     "MQTT",  "dB"),
        ("weather_station","Weather Station",         "HTTP",  "°C"),
        ("soil_sensor",    "Soil Sensor",             "CoAP",  "%"),
        ("radiation_gas",  "Radiation/Gas Detector",  "MQTT",  "ppb"),
    ],
    "cam": [
        ("crowd_camera",     "Crowd Camera",          "RTSP",  "density"),
        ("entrance_scanner", "Entrance Scanner",      "HTTP",  "events"),
    ],
}


# ═══════════════════════════════════════════
# DEFAULT USERS (9 users)
# ═══════════════════════════════════════════

DEFAULT_USERS = [
    ("admin",            "admin123",    "admin",            "System Admin",         "admin@smartcity.edu"),
    ("energy_raghuram",  "energy123",   "energy_manager",   "Raghuram K.",          "raghuram@smartcity.edu"),
    ("ehs_saicharan",    "ehs123",      "ehs_manager",      "Saicharan P.",         "saicharan@smartcity.edu"),
    ("analyst_vikram",   "analyst123",  "analyst",          "Vikram Reddy",         "vikram@smartcity.edu"),
    ("maint_raju",       "maint123",    "maintenance",      "Raju Kumar",           "raju@smartcity.edu"),
    ("researcher_ananya","research123", "researcher",       "Dr. Ananya Iyer",      "ananya@smartcity.edu"),
    ("resident_arjun",   "resident123", "resident",         "Arjun Kumar",          "arjun@smartcity.edu"),
    ("resident_meera",   "resident123", "resident",         "Meera Sharma",         "meera@smartcity.edu"),
    ("resident_kiran",   "resident123", "resident",         "Kiran Patel",          "kiran@smartcity.edu"),
]


# ═══════════════════════════════════════════
# RESIDENT → NODE MAPPING
# Each resident has: solar, meter, battery, AC, air quality
# ═══════════════════════════════════════════

RESIDENT_NODES = {
    "resident_arjun": [
        "R1-SOL-001", "R1-MTR-001", "R1-BAT-001", "R1-AC-001", "R1-AQI-001",
    ],
    "resident_meera": [
        "R2-SOL-001", "R2-MTR-001", "R2-BAT-001", "R2-AC-001", "R2-AQI-001",
    ],
    "resident_kiran": [
        "R3-SOL-001", "R3-MTR-001", "R3-BAT-001", "R3-AC-001", "R3-AQI-001",
    ],
}

# Node ID → (domain, node_type) lookup for auto-registration
RESIDENT_NODE_TYPES = {
    "SOL": ("energy", "solar_panel"),
    "MTR": ("energy", "smart_meter"),
    "BAT": ("energy", "battery_storage"),
    "AC":  ("energy", "ac_unit"),
    "AQI": ("ehs",    "air_quality"),
}


# ═══════════════════════════════════════════
# SEED FUNCTION
# ═══════════════════════════════════════════

def seed_database(db) -> dict:
    counts = {"roles": 0, "permissions": 0, "domains": 0, "node_types": 0, "users": 0, "user_nodes": 0}
    conn = db.get_connection()

    # Roles
    for rn, label, icon, pii, manage, retention in ROLES:
        cur = conn.execute(
            "INSERT OR IGNORE INTO roles (role_name, label, icon, can_see_pii, can_manage_users, data_retention_days) "
            "VALUES (?, ?, ?, ?, ?, ?)", (rn, label, icon, pii, manage, retention))
        if cur.rowcount > 0: counts["roles"] += 1
    conn.commit()

    # Role Permissions
    for role_name, perms in ROLE_PERMISSIONS.items():
        role_row = conn.execute("SELECT id FROM roles WHERE role_name = ?", (role_name,)).fetchone()
        if not role_row: continue
        for perm in perms:
            cur = conn.execute("INSERT OR IGNORE INTO role_permissions (role_id, permission) VALUES (?, ?)",
                               (role_row["id"], perm))
            if cur.rowcount > 0: counts["permissions"] += 1

    # Role Domain Access
    for role_name, domains in ROLE_DOMAINS.items():
        role_row = conn.execute("SELECT id FROM roles WHERE role_name = ?", (role_name,)).fetchone()
        if not role_row: continue
        for domain in domains:
            conn.execute("INSERT OR IGNORE INTO role_domain_access (role_id, domain_name) VALUES (?, ?)",
                         (role_row["id"], domain))
    conn.commit()

    # Domains
    for name, label, desc in DOMAINS:
        cur = conn.execute("INSERT OR IGNORE INTO domains (name, label, description) VALUES (?, ?, ?)",
                           (name, label, desc))
        if cur.rowcount > 0: counts["domains"] += 1
    conn.commit()

    # Node Types
    for domain_name, types in NODE_TYPES.items():
        domain_row = conn.execute("SELECT id FROM domains WHERE name = ?", (domain_name,)).fetchone()
        if not domain_row: continue
        for type_name, label, protocol, unit in types:
            cur = conn.execute(
                "INSERT OR IGNORE INTO node_types (domain_id, type_name, label, protocol, unit) VALUES (?, ?, ?, ?, ?)",
                (domain_row["id"], type_name, label, protocol, unit))
            if cur.rowcount > 0: counts["node_types"] += 1
    conn.commit()

    # Users
    now = datetime.now().isoformat()
    for username, password, role_name, fullname, email in DEFAULT_USERS:
        role_row = conn.execute("SELECT id FROM roles WHERE role_name = ?", (role_name,)).fetchone()
        if not role_row: continue
        cur = conn.execute(
            "INSERT OR IGNORE INTO users (username, password_hash, role_id, full_name, email, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?, 1, ?)",
            (username, hash_password(password), role_row["id"], fullname, email, now))
        if cur.rowcount > 0: counts["users"] += 1
    conn.commit()

    # User Node Mapping (for residents)
    for username, node_ids in RESIDENT_NODES.items():
        user_row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if not user_row: continue
        for nid in node_ids:
            cur = conn.execute("INSERT OR IGNORE INTO user_nodes (user_id, node_id_str) VALUES (?, ?)",
                               (user_row["id"], nid))
            if cur.rowcount > 0: counts["user_nodes"] += 1
    conn.commit()

    return counts
