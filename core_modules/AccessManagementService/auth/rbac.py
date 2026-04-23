"""
auth/rbac.py — Role-Based Access Control & JWT (Database-Backed).

All role information is read from the SQL database (roles, role_permissions,
role_domain_access tables) rather than hardcoded dicts.
"""

import hashlib
import os
import time
from typing import Any, Dict, List, Optional

import jwt

JWT_SECRET = os.getenv("JWT_SECRET", "smartcity-team32-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_SECONDS = 3600

_SALT = "smartcity-salt-v1"


def hash_password(password: str) -> str:
    return hashlib.sha256(f"{_SALT}:{password}".encode()).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    return hash_password(password) == password_hash


def create_token(username: str, role: str) -> str:
    payload = {
        "sub": username, "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + JWT_EXPIRY_SECONDS,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


# ═══════════════════════════════════════════
# DB-Backed Permission Checks
# ═══════════════════════════════════════════

def get_role_info(db, role_name: str) -> Optional[Dict[str, Any]]:
    """Get full role info from DB including permissions and domains."""
    role = db.fetchone("SELECT * FROM roles WHERE role_name = ?", (role_name,))
    if not role:
        return None

    perms = db.fetchall(
        "SELECT permission FROM role_permissions WHERE role_id = ?", (role["id"],)
    )
    domains = db.fetchall(
        "SELECT domain_name FROM role_domain_access WHERE role_id = ?", (role["id"],)
    )

    return {
        **role,
        "permissions": [p["permission"] for p in perms],
        "domains": [d["domain_name"] for d in domains],
    }


def has_permission(db, role_name: str, permission: str) -> bool:
    """Check if a role has a specific permission."""
    role = db.fetchone("SELECT id FROM roles WHERE role_name = ?", (role_name,))
    if not role:
        return False
    row = db.fetchone(
        "SELECT 1 FROM role_permissions WHERE role_id = ? AND permission = ?",
        (role["id"], permission)
    )
    return row is not None


def get_allowed_domains(db, role_name: str) -> List[str]:
    """Get list of domains a role can access."""
    role = db.fetchone("SELECT id FROM roles WHERE role_name = ?", (role_name,))
    if not role:
        return []
    rows = db.fetchall(
        "SELECT domain_name FROM role_domain_access WHERE role_id = ?", (role["id"],)
    )
    return [r["domain_name"] for r in rows]


def get_user_with_role(db, username: str) -> Optional[Dict[str, Any]]:
    """Get user joined with their role info."""
    user = db.fetchone(
        """SELECT u.*, r.role_name, r.label AS role_label, r.icon AS role_icon,
                  r.can_see_pii, r.can_manage_users
           FROM users u
           JOIN roles r ON u.role_id = r.id
           WHERE u.username = ?""",
        (username,)
    )
    return user
