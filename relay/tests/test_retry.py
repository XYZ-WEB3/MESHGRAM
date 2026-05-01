"""
Тесты retry_queue: enqueue, due, expired, reschedule, delete.
Включая SOS fast-retry флаг is_sos (v0.6).
"""
import time


def _enqueue(relay, *, tg_user_id=101, tg_chat_id=200, status_msg_id=300,
             slot_n=1, payload="hello",
             deadline_offset=3600, initial_delay_s=120, is_sos=False):
    """Helper: упрощает создание retry-rows."""
    deadline = int(time.time()) + deadline_offset
    return relay.retry_enqueue(
        tg_user_id, tg_chat_id, status_msg_id,
        slot_n, payload, deadline, initial_delay_s, is_sos=is_sos,
    )


def test_enqueue_returns_id(relay_with_db):
    rid = _enqueue(relay_with_db)
    assert isinstance(rid, int)
    assert rid > 0


def test_enqueue_stores_is_sos_flag(relay_with_db):
    rid_normal = _enqueue(relay_with_db, payload="A")
    rid_urgent = _enqueue(relay_with_db, payload="B", is_sos=True)

    row_n = relay_with_db.retry_get(rid_normal)
    row_u = relay_with_db.retry_get(rid_urgent)
    assert row_n["is_sos"] == 0
    assert row_u["is_sos"] == 1


def test_due_returns_only_ready(relay_with_db):
    """initial_delay=0 → due сразу. initial_delay=999 → ещё не время."""
    rid_now = _enqueue(relay_with_db, payload="ready", initial_delay_s=0)
    _enqueue(relay_with_db, payload="later", initial_delay_s=999)

    due = relay_with_db.retry_due()
    due_ids = [r["id"] for r in due]
    assert rid_now in due_ids
    assert len(due) == 1


def test_expired_returns_only_past_deadline(relay_with_db):
    rid_alive = _enqueue(relay_with_db, payload="A")
    rid_dead = _enqueue(relay_with_db, payload="B", deadline_offset=-100)

    expired = relay_with_db.retry_expired()
    expired_ids = [r["id"] for r in expired]
    assert rid_dead in expired_ids
    assert rid_alive not in expired_ids


def test_reschedule_increments_attempts(relay_with_db):
    rid = _enqueue(relay_with_db)
    new_at = int(time.time()) + 600
    relay_with_db.retry_reschedule(rid, new_at)

    row = relay_with_db.retry_get(rid)
    assert row["attempts"] == 1
    assert row["next_try_at"] == new_at

    relay_with_db.retry_reschedule(rid, new_at + 100)
    row = relay_with_db.retry_get(rid)
    assert row["attempts"] == 2


def test_delete(relay_with_db):
    rid = _enqueue(relay_with_db)
    assert relay_with_db.retry_get(rid) is not None
    relay_with_db.retry_delete(rid)
    assert relay_with_db.retry_get(rid) is None


def test_delete_for_slot(relay_with_db):
    """retry_delete_for_slot чистит ВСЕ строки для слота, не одну."""
    rid_a = _enqueue(relay_with_db, slot_n=5, payload="A", initial_delay_s=0)
    rid_b = _enqueue(relay_with_db, slot_n=5, payload="B", initial_delay_s=0)
    rid_c = _enqueue(relay_with_db, slot_n=7, payload="C", initial_delay_s=0)

    relay_with_db.retry_delete_for_slot(5)

    # Slot 5 строки удалены полностью
    assert relay_with_db.retry_get(rid_a) is None
    assert relay_with_db.retry_get(rid_b) is None
    # Slot 7 жив
    assert relay_with_db.retry_get(rid_c) is not None


def test_sos_backoff_constant_present(relay_module):
    """v0.6: _RETRY_SOS_BACKOFF_SEC = (5, 15, 30, 60, 120)."""
    assert relay_module._RETRY_SOS_BACKOFF_SEC == (5, 15, 30, 60, 120)
