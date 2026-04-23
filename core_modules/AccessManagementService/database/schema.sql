-- ═══════════════════════════════════════════════════════════
-- Smart City Access Management — Normalized SQL Schema
-- Database: SQLite (with WAL mode for concurrent read/write)
-- ═══════════════════════════════════════════════════════════
-- Normalization: 3NF
-- Tables: 9 (roles, role_permissions, role_domain_access,
--              users, domains, node_types, nodes,
--              telemetry_readings, alerts)
-- ═══════════════════════════════════════════════════════════

-- ─────────────────────────────────────
-- SCHEMA GROUP: AUTH & RBAC
-- ─────────────────────────────────────

CREATE TABLE IF NOT EXISTS roles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    role_name       TEXT    UNIQUE NOT NULL,   -- e.g. 'admin', 'analyst'
    label           TEXT    NOT NULL,           -- e.g. 'System Administrator'
    icon            TEXT    DEFAULT '👤',
    can_see_pii     INTEGER DEFAULT 0,          -- boolean: 1 = can see PII
    can_manage_users INTEGER DEFAULT 0,         -- boolean: 1 = can CRUD users
    data_retention_days INTEGER DEFAULT 30       -- max days of history visible
);

CREATE TABLE IF NOT EXISTS role_permissions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    role_id         INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission      TEXT    NOT NULL,           -- e.g. 'telemetry.read'
    UNIQUE(role_id, permission)
);

CREATE TABLE IF NOT EXISTS role_domain_access (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    role_id         INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    domain_name     TEXT    NOT NULL,           -- FK-less ref to domains.name
    UNIQUE(role_id, domain_name)
);

CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT    UNIQUE NOT NULL,
    password_hash   TEXT    NOT NULL,
    role_id         INTEGER NOT NULL REFERENCES roles(id),
    full_name       TEXT,
    email           TEXT,
    is_active       INTEGER DEFAULT 1,
    created_at      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_users_role ON users(role_id);


-- ─────────────────────────────────────
-- SCHEMA GROUP: USER-NODE MAPPING
-- Maps residents to their personal IoT nodes
-- ─────────────────────────────────────

CREATE TABLE IF NOT EXISTS user_nodes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    node_id_str     TEXT    NOT NULL,            -- e.g. 'R1-SOL-001'
    UNIQUE(user_id, node_id_str)
);

CREATE INDEX IF NOT EXISTS idx_user_nodes_user ON user_nodes(user_id);


-- ─────────────────────────────────────
-- SCHEMA GROUP: IoT REGISTRY
-- ─────────────────────────────────────

CREATE TABLE IF NOT EXISTS domains (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    UNIQUE NOT NULL,    -- 'energy', 'ehs', 'cam'
    label           TEXT    NOT NULL,            -- 'Energy Management'
    description     TEXT
);

CREATE TABLE IF NOT EXISTS node_types (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    domain_id       INTEGER NOT NULL REFERENCES domains(id) ON DELETE CASCADE,
    type_name       TEXT    NOT NULL,            -- 'solar_panel', 'air_quality'
    label           TEXT    NOT NULL,            -- 'Solar Panel'
    protocol        TEXT    DEFAULT 'HTTP',      -- 'MQTT', 'HTTP', 'CoAP'
    unit            TEXT,                         -- 'watts', 'ppm', '%'
    UNIQUE(domain_id, type_name)
);

CREATE TABLE IF NOT EXISTS nodes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id         TEXT    UNIQUE NOT NULL,     -- 'NRG-SOL-001'
    node_type_id    INTEGER NOT NULL REFERENCES node_types(id),
    location        TEXT,
    is_active       INTEGER DEFAULT 1,
    first_seen      TEXT    NOT NULL,
    last_seen       TEXT
);

CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(node_type_id);


-- ─────────────────────────────────────
-- SCHEMA GROUP: TELEMETRY (Time-Series)
-- ─────────────────────────────────────

CREATE TABLE IF NOT EXISTS telemetry_readings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    node_pk         INTEGER NOT NULL REFERENCES nodes(id),
    domain_name     TEXT    NOT NULL,            -- denormalized for fast queries
    node_type_name  TEXT    NOT NULL,            -- denormalized for fast queries
    node_id_str     TEXT    NOT NULL,            -- denormalized: 'NRG-SOL-001'
    timestamp       TEXT    NOT NULL,
    data_json       TEXT    NOT NULL,            -- JSON payload of sensor readings
    is_critical     INTEGER DEFAULT 0,
    ingested_at     TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_telemetry_node   ON telemetry_readings(node_pk);
CREATE INDEX IF NOT EXISTS idx_telemetry_ts     ON telemetry_readings(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_telemetry_domain ON telemetry_readings(domain_name);
CREATE INDEX IF NOT EXISTS idx_telemetry_crit   ON telemetry_readings(is_critical) WHERE is_critical = 1;


-- ─────────────────────────────────────
-- SCHEMA GROUP: ALERTS (placeholder — NULL for now)
-- Will be integrated with Alerting Subsystem (Member 4) later
-- ─────────────────────────────────────

CREATE TABLE IF NOT EXISTS alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    node_pk         INTEGER REFERENCES nodes(id),
    domain_name     TEXT,
    severity        TEXT    NOT NULL DEFAULT 'WARNING',  -- CRITICAL, WARNING, INFO
    message         TEXT,
    data_json       TEXT,
    acknowledged    INTEGER DEFAULT 0,
    resolved        INTEGER DEFAULT 0,
    created_at      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_alerts_sev    ON alerts(severity);
CREATE INDEX IF NOT EXISTS idx_alerts_domain ON alerts(domain_name);


-- ─────────────────────────────────────
-- VIEW: Telemetry with full context
-- ─────────────────────────────────────

CREATE VIEW IF NOT EXISTS v_telemetry_full AS
SELECT
    tr.id,
    tr.node_id_str   AS node_id,
    d.name           AS domain,
    d.label          AS domain_label,
    nt.type_name     AS node_type,
    nt.label         AS node_type_label,
    tr.timestamp,
    tr.data_json,
    tr.is_critical,
    tr.ingested_at,
    n.location       AS node_location
FROM telemetry_readings tr
JOIN nodes n       ON tr.node_pk = n.id
JOIN node_types nt ON n.node_type_id = nt.id
JOIN domains d     ON nt.domain_id = d.id;


-- ─────────────────────────────────────
-- VIEW: Domain statistics
-- ─────────────────────────────────────

CREATE VIEW IF NOT EXISTS v_domain_stats AS
SELECT
    d.name           AS domain,
    d.label          AS domain_label,
    COUNT(DISTINCT n.id)  AS unique_nodes,
    COUNT(DISTINCT nt.id) AS node_type_count,
    COUNT(tr.id)          AS total_readings,
    SUM(tr.is_critical)   AS critical_readings,
    MAX(tr.timestamp)     AS latest_timestamp
FROM domains d
LEFT JOIN node_types nt ON nt.domain_id = d.id
LEFT JOIN nodes n       ON n.node_type_id = nt.id
LEFT JOIN telemetry_readings tr ON tr.node_pk = n.id
GROUP BY d.id;


-- ─────────────────────────────────────
-- VIEW: User profiles (no password hash)
-- ─────────────────────────────────────

CREATE VIEW IF NOT EXISTS v_user_profiles AS
SELECT
    u.id,
    u.username,
    r.role_name AS role,
    r.label     AS role_label,
    r.icon      AS role_icon,
    u.full_name,
    u.email,
    u.is_active,
    u.created_at
FROM users u
JOIN roles r ON u.role_id = r.id;
