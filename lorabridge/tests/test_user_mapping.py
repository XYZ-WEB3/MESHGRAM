from pathlib import Path

from src.user_mapping.manager import UserMappingManager


def test_assign_and_persist(tmp_path: Path) -> None:
    storage = tmp_path / "users.json"
    manager = UserMappingManager(storage)
    mesh_id = manager.assign_id("123")
    assert mesh_id == "#1"
    manager.record_history("123", "out", "hello")
    manager = UserMappingManager(storage)
    assert manager.assign_id("123") == mesh_id
    assert manager.records["123"].history[-1]["text"] == "hello"
