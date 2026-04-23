"""
storage/base.py — Abstract Storage Backend Interface (Repository Pattern).

Defines the contract that ALL storage backends must implement.
This is the key abstraction that makes migrating from file storage
to PostgreSQL/InfluxDB a single-line change in main.py.

Design Pattern: Repository Pattern
  - FileStorageBackend (current) → stores JSONL files on disk
  - PostgresBackend (future)     → stores in PostgreSQL tables
  - InfluxBackend (future)       → stores telemetry in InfluxDB

Usage in main.py:
  # Current:
  storage = FileStorageBackend(data_dir="./data")
  # Future migration:
  storage = PostgresBackend(dsn="postgresql://...")
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class StorageBackend(ABC):
    """
    Abstract interface for all storage backends.
    Any concrete implementation must provide these methods.
    """

    # ── Telemetry Operations ──

    @abstractmethod
    def save_telemetry(self, domain: str, record: Dict[str, Any]) -> str:
        """
        Store a single telemetry record.
        Returns the record ID.
        """
        ...

    @abstractmethod
    def query_telemetry(
        self,
        domain: Optional[str] = None,
        node_type: Optional[str] = None,
        node_id: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Query telemetry records with optional filters.
        Returns list of matching records (newest first).
        """
        ...

    @abstractmethod
    def count_telemetry(self, domain: Optional[str] = None) -> int:
        """Count telemetry records, optionally filtered by domain."""
        ...

    @abstractmethod
    def get_domains(self) -> List[str]:
        """List all domains that have stored telemetry data."""
        ...

    @abstractmethod
    def get_domain_stats(self) -> Dict[str, Any]:
        """Get per-domain statistics (count, latest timestamp, node types)."""
        ...

    # ── User Operations ──

    @abstractmethod
    def save_user(self, user: Dict[str, Any]) -> None:
        """Create or update a user record."""
        ...

    @abstractmethod
    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        """Get a user by username. Returns None if not found."""
        ...

    @abstractmethod
    def list_users(self) -> List[Dict[str, Any]]:
        """List all users."""
        ...

    @abstractmethod
    def delete_user(self, username: str) -> bool:
        """Delete a user. Returns True if deleted, False if not found."""
        ...

    # ── Alert Operations ──

    @abstractmethod
    def save_alert(self, alert: Dict[str, Any]) -> str:
        """Store an alert record. Returns the alert ID."""
        ...

    @abstractmethod
    def query_alerts(
        self,
        severity: Optional[str] = None,
        domain: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Query alerts with optional filters."""
        ...
