from datetime import datetime, timedelta, timezone
from pathlib import Path

from lorabridge.user_mapping.store import UserMappingStore


def test_assign_and_cleanup(tmp_path: Path) -> None:
    store_path = tmp_path / "users.json"
    store = UserMappingStore(store_path, expiry_hours=1)
    record = store.assign(123, "Alice")
    assert record.mesh_id == "#1"
    record2 = store.assign(124, "Bob")
    assert record2.mesh_id == "#2"

    # Force expiration by editing timestamps
    record.last_seen = datetime.now(timezone.utc) - timedelta(hours=2)
    store._persist()
    store.cleanup()
    assert store.find_by_mesh_id("#1") is None
    assert store.find_by_mesh_id("#2") is not None
