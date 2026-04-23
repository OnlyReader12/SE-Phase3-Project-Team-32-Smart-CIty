"""
auth/rbac.py — Role-Based Access Control & JWT Authentication.

Manages:
  - Role definitions with permissions (8 Smart City roles)
  - JWT token encoding/decoding (using PyJWT)
  - Password hashing (using hashlib + salt for zero-dependency hashing)
  - Permission checking middleware
  - Default user seeding

Design Pattern: Strategy Pattern (per-role permission enforcement)
"""

import hashlib
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import jwt

from models.schemas import UserRole


# ═══════════════════════════════════════════
# JWT Configuration
# ═══════════════════════════════════════════

JWT_SECRET = os.getenv("JWT_SECRET", "smartcity-team32-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_SECONDS = 3600  # 1 hour


# ═══════════════════════════════════════════
# Role Permissions Matrix
# ═══════════════════════════════════════════

ROLE_PERMISSIONS: Dict[str, Dict[str, Any]] = {
    UserRole.ADMIN: {
        "label": "System Administrator",
        "icon": "🛡️",
        "domains": ["energy", "ehs", "cam", "system"],
        "permissions": [
            "telemetry.read", "telemetry.write",
            "users.read", "users.write", "users.delete",
            "alerts.read", "alerts.manage",
            "dashboard.full", "config.manage",
            "system.health", "system.logs",
        ],
        "can_see_pii": True,
        "can_manage_users": True,
        "data_retention_days": None,  # unlimited
    },
    UserRole.CAMPUS_MANAGER: {
        "label": "Campus Manager",
        "icon": "🏛️",
        "domains": ["energy", "ehs", "cam"],
        "permissions": [
            "telemetry.read",
            "alerts.read", "alerts.manage",
            "dashboard.full",
            "config.manage",
        ],
        "can_see_pii": False,
        "can_manage_users": False,
        "data_retention_days": 90,
    },
    UserRole.ANALYST: {
        "label": "Data Analyst",
        "icon": "📊",
        "domains": ["energy", "ehs", "cam"],
        "permissions": [
            "telemetry.read",
            "alerts.read",
            "dashboard.analytics",
            "ml.predictions",
        ],
        "can_see_pii": False,
        "can_manage_users": False,
        "data_retention_days": 90,
    },
    UserRole.MAINTENANCE: {
        "label": "Maintenance Engineer",
        "icon": "🔧",
        "domains": ["energy", "ehs"],
        "permissions": [
            "telemetry.read",
            "alerts.read",
            "dashboard.health",
            "system.health",
        ],
        "can_see_pii": False,
        "can_manage_users": False,
        "data_retention_days": 30,
    },
    UserRole.RESEARCHER: {
        "label": "Researcher",
        "icon": "🔬",
        "domains": ["energy", "ehs"],
        "permissions": [
            "telemetry.read",
            "dashboard.research",
        ],
        "can_see_pii": False,
        "can_manage_users": False,
        "data_retention_days": 30,
    },
    UserRole.RESIDENT: {
        "label": "Resident",
        "icon": "🏠",
        "domains": [],  # only personal data
        "permissions": [
            "alerts.read",
            "dashboard.personal",
        ],
        "can_see_pii": False,
        "can_manage_users": False,
        "data_retention_days": 7,
    },
    UserRole.EMERGENCY_RESPONDER: {
        "label": "Emergency Responder",
        "icon": "🚨",
        "domains": ["energy", "ehs"],
        "permissions": [
            "telemetry.read",
            "alerts.read",
            "dashboard.emergency",
        ],
        "can_see_pii": False,
        "can_manage_users": False,
        "data_retention_days": 7,
    },
    UserRole.OPERATOR: {
        "label": "IoT Operator",
        "icon": "📡",
        "domains": ["energy", "ehs", "cam"],
        "permissions": [
            "telemetry.read", "telemetry.write",
            "alerts.read",
            "dashboard.health",
            "system.health",
        ],
        "can_see_pii": False,
        "can_manage_users": False,
        "data_retention_days": 30,
    },
}


# ═══════════════════════════════════════════
# Password Hashing
# ═══════════════════════════════════════════

_SALT = "smartcity-salt-v1"

def hash_password(password: str) -> str:
    """Hash a password using SHA-256 with salt."""
    return hashlib.sha256(f"{_SALT}:{password}".encode()).hexdigest()

def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    return hash_password(password) == password_hash


# ═══════════════════════════════════════════
# JWT Token Management
# ═══════════════════════════════════════════

def create_token(username: str, role: str) -> str:
    """Create a JWT access token."""
    payload = {
        "sub": username,
        "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + JWT_EXPIRY_SECONDS,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate a JWT token. Returns None on failure."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ═══════════════════════════════════════════
# Permission Checks
# ═══════════════════════════════════════════

def get_role_config(role: str) -> Dict[str, Any]:
    """Get the permission config for a role."""
    return ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS[UserRole.RESIDENT])


def has_permission(role: str, permission: str) -> bool:
    """Check if a role has a specific permission."""
    config = get_role_config(role)
    return permission in config.get("permissions", [])


def get_allowed_domains(role: str) -> List[str]:
    """Get the list of domains a role can access."""
    config = get_role_config(role)
    return config.get("domains", [])


def can_access_domain(role: str, domain: str) -> bool:
    """Check if a role can access a specific domain."""
    config = get_role_config(role)
    allowed = config.get("domains", [])
    if not allowed:
        return False
    return domain in allowed or "system" in allowed


# ═══════════════════════════════════════════
# Default Users (Seeded on First Run)
# ═══════════════════════════════════════════

DEFAULT_USERS = [
    {"username": "admin",       "password": "admin123",    "role": UserRole.ADMIN,                "full_name": "System Admin",         "email": "admin@smartcity.edu"},
    {"username": "manager1",    "password": "manager123",  "role": UserRole.CAMPUS_MANAGER,       "full_name": "Dr. Priya Sharma",     "email": "priya@smartcity.edu"},
    {"username": "analyst1",    "password": "analyst123",  "role": UserRole.ANALYST,              "full_name": "Vikram Reddy",         "email": "vikram@smartcity.edu"},
    {"username": "maint1",      "password": "maint123",    "role": UserRole.MAINTENANCE,          "full_name": "Raju Kumar",           "email": "raju@smartcity.edu"},
    {"username": "researcher1", "password": "research123", "role": UserRole.RESEARCHER,           "full_name": "Dr. Ananya Iyer",      "email": "ananya@smartcity.edu"},
    {"username": "resident1",   "password": "resident123", "role": UserRole.RESIDENT,             "full_name": "Suresh Patel",         "email": "suresh@smartcity.edu"},
    {"username": "responder1",  "password": "respond123",  "role": UserRole.EMERGENCY_RESPONDER,  "full_name": "Inspector Reddy",      "email": "responder@smartcity.edu"},
    {"username": "operator1",   "password": "operator123", "role": UserRole.OPERATOR,             "full_name": "Kiran Tech",           "email": "kiran@smartcity.edu"},
]


def seed_default_users(storage) -> int:
    """Seed default users if the store is empty. Returns count of users created."""
    existing = storage.list_users()
    if existing:
        return 0

    count = 0
    for u in DEFAULT_USERS:
        user_record = {
            "username": u["username"],
            "password_hash": hash_password(u["password"]),
            "role": u["role"].value if hasattr(u["role"], "value") else u["role"],
            "full_name": u.get("full_name"),
            "email": u.get("email"),
            "created_at": datetime.now().isoformat(),
            "is_active": True,
        }
        storage.save_user(user_record)
        count += 1

    return count
