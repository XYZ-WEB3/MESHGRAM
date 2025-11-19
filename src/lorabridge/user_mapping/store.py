"""Persistent user ↔ ID mapping for the bridge."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional


@dataclass
class UserRecord:
    telegram_id: int
    mesh_id: str
    display_name: str
    last_seen: datetime

    def to_dict(self) -> dict:
        return {
            "telegram_id": self.telegram_id,
            "mesh_id": self.mesh_id,
            "display_name": self.display_name,
            "last_seen": self.last_seen.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UserRecord":
        return cls(
            telegram_id=data["telegram_id"],
            mesh_id=data["mesh_id"],
            display_name=data.get("display_name", ""),
            last_seen=datetime.fromisoformat(data["last_seen"]),
        )


class UserMappingStore:
    """Handles ID assignment and persistence."""

    def __init__(self, path: str | Path, expiry_hours: int = 48):
        self.path = Path(path)
        self.expiry = timedelta(hours=expiry_hours)
        self.records: Dict[int, UserRecord] = {}
        self.sequence = 0
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._persist()
            return
        with self.path.open("r", encoding="utf-8") as handle:
            try:
                payload = json.load(handle)
            except json.JSONDecodeError:
                payload = {"sequence": 0, "users": []}
        self.sequence = payload.get("sequence", 0)
        self.records = {
            record["telegram_id"]: UserRecord.from_dict(record)
            for record in payload.get("users", [])
        }
        self.cleanup()

    def _persist(self) -> None:
        data = {
            "sequence": self.sequence,
            "users": [record.to_dict() for record in self.records.values()],
        }
        with self.path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)

    def cleanup(self) -> None:
        now = datetime.now(timezone.utc)
        stale = [
            key for key, record in self.records.items() if now - record.last_seen > self.expiry
        ]
        for key in stale:
            del self.records[key]
        if stale:
            self._persist()

    def assign(self, telegram_id: int, display_name: str) -> UserRecord:
        self.cleanup()
        record = self.records.get(telegram_id)
        now = datetime.now(timezone.utc)
        if record:
            record.last_seen = now
            record.display_name = display_name
        else:
            self.sequence += 1
            mesh_id = f"#{self.sequence}"
            record = UserRecord(
                telegram_id=telegram_id,
                mesh_id=mesh_id,
                display_name=display_name,
                last_seen=now,
            )
            self.records[telegram_id] = record
        self._persist()
        return record

    def find_by_mesh_id(self, mesh_id: str) -> Optional[UserRecord]:
        self.cleanup()
        for record in self.records.values():
            if record.mesh_id == mesh_id:
                return record
        return None

    def all_active(self) -> list[UserRecord]:
        self.cleanup()
        return sorted(self.records.values(), key=lambda rec: rec.mesh_id)
