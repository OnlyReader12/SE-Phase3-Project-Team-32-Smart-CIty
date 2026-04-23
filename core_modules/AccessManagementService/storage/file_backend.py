"""
storage/file_backend.py — File-Based Storage Backend (JSONL files).

Concrete implementation of the StorageBackend interface.
Stores telemetry as JSONL (one JSON object per line) organized by domain and date.
Stores users as a single JSON file.

File structure:
  data/
    telemetry/
      energy/
        2026-04-23.jsonl
        2026-04-24.jsonl
      ehs/
        2026-04-23.jsonl
    users.json
    alerts.jsonl

This backend is designed for development and demo purposes.
For production, swap to PostgresBackend or InfluxBackend via the same interface.
"""

import json
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from storage.base import StorageBackend


class FileStorageBackend(StorageBackend):
    """
    JSONL file-based storage implementation.
    Thread-safe via locks for concurrent IoT data ingestion.
    """

    def __init__(self, data_dir: str = "./data"):
        self.data_dir = Path(data_dir)
        self.telemetry_dir = self.data_dir / "telemetry"
        self.users_file = self.data_dir / "users.json"
        self.alerts_file = self.data_dir / "alerts.jsonl"

        # Thread safety
        self._telemetry_lock = threading.Lock()
        self._user_lock = threading.Lock()
        self._alert_lock = threading.Lock()

        # Ensure directories exist
        self.telemetry_dir.mkdir(parents=True, exist_ok=True)

        # Initialize users file if missing
        if not self.users_file.exists():
            self._write_json(self.users_file, {})

        # In-memory cache for fast user lookups
        self._users_cache: Optional[Dict] = None

    # ═══════════════════════════════════════════
    # Telemetry Operations
    # ═══════════════════════════════════════════

    def save_telemetry(self, domain: str, record: Dict[str, Any]) -> str:
        """Append a telemetry record to the domain's daily JSONL file."""
        record_id = str(uuid.uuid4())[:12]
        record["id"] = record_id
        record["ingested_at"] = datetime.now().isoformat()

        # Determine file path: data/telemetry/{domain}/{date}.jsonl
        today = datetime.now().strftime("%Y-%m-%d")
        domain_dir = self.telemetry_dir / domain
        domain_dir.mkdir(parents=True, exist_ok=True)
        file_path = domain_dir / f"{today}.jsonl"

        with self._telemetry_lock:
            with open(file_path, "a") as f:
                f.write(json.dumps(record, default=str) + "\n")

        return record_id

    def query_telemetry(
        self,
        domain: Optional[str] = None,
        node_type: Optional[str] = None,
        node_id: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query telemetry records with optional filters."""
        records = []
        domains_to_scan = [domain] if domain else self.get_domains()

        for d in domains_to_scan:
            domain_path = self.telemetry_dir / d
            if not domain_path.exists():
                continue
            # Get all JSONL files sorted newest first
            files = sorted(domain_path.glob("*.jsonl"), reverse=True)
            for fp in files:
                with self._telemetry_lock:
                    with open(fp, "r") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                rec = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            # Apply filters
                            if node_type and rec.get("node_type") != node_type:
                                continue
                            if node_id and rec.get("node_id") != node_id:
                                continue
                            if since and rec.get("timestamp", "") < since:
                                continue
                            if until and rec.get("timestamp", "") > until:
                                continue
                            records.append(rec)

                if len(records) >= limit * 3:
                    break

        # Sort by timestamp descending and apply limit
        records.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
        return records[:limit]

    def count_telemetry(self, domain: Optional[str] = None) -> int:
        """Count total telemetry records."""
        count = 0
        domains = [domain] if domain else self.get_domains()
        for d in domains:
            domain_path = self.telemetry_dir / d
            if not domain_path.exists():
                continue
            for fp in domain_path.glob("*.jsonl"):
                with open(fp, "r") as f:
                    count += sum(1 for line in f if line.strip())
        return count

    def get_domains(self) -> List[str]:
        """List all domains that have stored data."""
        if not self.telemetry_dir.exists():
            return []
        return [d.name for d in self.telemetry_dir.iterdir() if d.is_dir()]

    def get_domain_stats(self) -> Dict[str, Any]:
        """Get per-domain statistics."""
        stats = {}
        for domain in self.get_domains():
            domain_path = self.telemetry_dir / domain
            files = sorted(domain_path.glob("*.jsonl"), reverse=True)
            total = 0
            latest_ts = ""
            node_types = set()
            node_ids = set()

            for fp in files:
                with open(fp, "r") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rec = json.loads(line)
                            total += 1
                            ts = rec.get("timestamp", "")
                            if ts > latest_ts:
                                latest_ts = ts
                            if rec.get("node_type"):
                                node_types.add(rec["node_type"])
                            if rec.get("node_id"):
                                node_ids.add(rec["node_id"])
                        except json.JSONDecodeError:
                            continue

            stats[domain] = {
                "total_records": total,
                "latest_timestamp": latest_ts if latest_ts else None,
                "node_types": sorted(node_types),
                "unique_nodes": len(node_ids),
                "files": len(files),
            }
        return stats

    # ═══════════════════════════════════════════
    # User Operations
    # ═══════════════════════════════════════════

    def save_user(self, user: Dict[str, Any]) -> None:
        """Create or update a user."""
        with self._user_lock:
            users = self._load_users()
            users[user["username"]] = user
            self._write_json(self.users_file, users)
            self._users_cache = users

    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user by username."""
        users = self._load_users()
        return users.get(username)

    def list_users(self) -> List[Dict[str, Any]]:
        """List all users."""
        users = self._load_users()
        return list(users.values())

    def delete_user(self, username: str) -> bool:
        """Delete a user."""
        with self._user_lock:
            users = self._load_users()
            if username not in users:
                return False
            del users[username]
            self._write_json(self.users_file, users)
            self._users_cache = users
            return True

    def _load_users(self) -> Dict:
        """Load users with caching."""
        if self._users_cache is not None:
            return self._users_cache
        try:
            with open(self.users_file, "r") as f:
                self._users_cache = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self._users_cache = {}
        return self._users_cache

    # ═══════════════════════════════════════════
    # Alert Operations
    # ═══════════════════════════════════════════

    def save_alert(self, alert: Dict[str, Any]) -> str:
        """Append an alert to the alerts JSONL file."""
        alert_id = f"ALERT-{uuid.uuid4().hex[:8]}"
        alert["id"] = alert_id
        alert["created_at"] = datetime.now().isoformat()

        with self._alert_lock:
            with open(self.alerts_file, "a") as f:
                f.write(json.dumps(alert, default=str) + "\n")
        return alert_id

    def query_alerts(
        self,
        severity: Optional[str] = None,
        domain: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Query alerts from the alerts file."""
        alerts = []
        if not self.alerts_file.exists():
            return alerts

        with self._alert_lock:
            with open(self.alerts_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        alert = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if severity and alert.get("severity") != severity:
                        continue
                    if domain and alert.get("domain") != domain:
                        continue
                    alerts.append(alert)

        alerts.sort(key=lambda a: a.get("created_at", ""), reverse=True)
        return alerts[:limit]

    # ═══════════════════════════════════════════
    # Utilities
    # ═══════════════════════════════════════════

    @staticmethod
    def _write_json(path: Path, data: Any) -> None:
        """Atomically write JSON file."""
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2, default=str)
        tmp.replace(path)
