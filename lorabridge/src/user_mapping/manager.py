"""User mapping between Telegram users and mesh IDs."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from ..utils.storage import read_json, write_json


@dataclass
class UserRecord:
    telegram_id: str
    mesh_id: str
    assigned_at: datetime
    history: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, str]:
        return {
            "telegram_id": self.telegram_id,
            "mesh_id": self.mesh_id,
            "assigned_at": self.assigned_at.isoformat(),
            "history": self.history,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, str]) -> "UserRecord":
        return cls(
            telegram_id=payload["telegram_id"],
            mesh_id=payload["mesh_id"],
            assigned_at=datetime.fromisoformat(payload["assigned_at"]),
            history=payload.get("history", []),
        )


class UserMappingManager:
    """Persist user mappings and provide ID assignment logic."""

    def __init__(self, storage_path: Path, expiration_hours: int = 48) -> None:
        self.storage_path = storage_path
        self.expiration = timedelta(hours=expiration_hours)
        self.data = read_json(storage_path)
        self.records: Dict[str, UserRecord] = {}
        for payload in self.data.get("users", []):
            record = UserRecord.from_dict(payload)
            self.records[record.telegram_id] = record
        self.last_id = int(self.data.get("last_id", 0))

    def assign_id(self, telegram_id: str) -> str:
        record = self.records.get(telegram_id)
        if record and not self._is_expired(record):
            return record.mesh_id
        self.last_id += 1
        mesh_id = f"#{self.last_id}"
        record = UserRecord(
            telegram_id=telegram_id,
            mesh_id=mesh_id,
            assigned_at=datetime.now(timezone.utc),
        )
        self.records[telegram_id] = record
        self._persist()
        return mesh_id

    def record_history(self, telegram_id: str, direction: str, text: str) -> None:
        record = self.records.get(telegram_id)
        if not record:
            mesh_id = self.assign_id(telegram_id)
            record = self.records[telegram_id]
            record.mesh_id = mesh_id
        record.history.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "direction": direction,
                "text": text,
            }
        )
        record.history = record.history[-50:]
        self._persist()

    def list_active_users(self) -> List[UserRecord]:
        return [record for record in self.records.values() if not self._is_expired(record)]

    def _persist(self) -> None:
        payload = {
            "last_id": self.last_id,
            "users": [record.to_dict() for record in self.records.values()],
        }
        write_json(self.storage_path, payload)

    def _is_expired(self, record: UserRecord) -> bool:
        return datetime.now(timezone.utc) - record.assigned_at > self.expiration
