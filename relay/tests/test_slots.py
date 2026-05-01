"""
Тесты sticky-слотов: allocate_or_reuse, lookup, mark_replied, expire,
free_all_for_user, list_active. Используется in-memory SQLite через
fixture relay_with_db.
"""
import time


def test_alloc_first_slot(relay_with_db):
    """Первый allocation для нового юзера → slot 1, reused=False."""
    n, reused = relay_with_db.slot_allocate_or_reuse(101)
    assert n == 1
    assert reused is False


def test_alloc_unique_slots_for_different_users(relay_with_db):
    n1, _ = relay_with_db.slot_allocate_or_reuse(101)
    n2, _ = relay_with_db.slot_allocate_or_reuse(102)
    n3, _ = relay_with_db.slot_allocate_or_reuse(103)
    assert {n1, n2, n3} == {1, 2, 3}


def test_alloc_reuses_lowest_free_slot(relay_with_db):
    """После DELETE slot 2, новый юзер получает slot 2 (не 4)."""
    n1, _ = relay_with_db.slot_allocate_or_reuse(101)
    n2, _ = relay_with_db.slot_allocate_or_reuse(102)
    n3, _ = relay_with_db.slot_allocate_or_reuse(103)
    relay_with_db.slot_free(n2)
    n4, _ = relay_with_db.slot_allocate_or_reuse(104)
    assert n4 == 2  # переиспользовали освободившийся


def test_alloc_sticky_reuses_active_slot_for_same_user(relay_with_db):
    """Тот же юзер — тот же slot, reused=True."""
    n1, reused1 = relay_with_db.slot_allocate_or_reuse(101)
    n2, reused2 = relay_with_db.slot_allocate_or_reuse(101)
    assert n1 == n2
    assert reused1 is False
    assert reused2 is True


def test_lookup_valid(relay_with_db):
    relay_with_db.slot_allocate_or_reuse(555)
    n_active = relay_with_db.slot_lookup(1)
    assert n_active == 555


def test_lookup_missing(relay_with_db):
    assert relay_with_db.slot_lookup(99) is None


def test_lookup_expired(relay_with_db):
    """Slot с expires_at в прошлом — lookup возвращает None."""
    relay_with_db.slot_allocate_or_reuse(101)
    # Принудительно делаем expired
    with relay_with_db._db_lock:
        relay_with_db._db.execute(
            "UPDATE slots SET expires_at = ? WHERE slot_n = 1",
            (int(time.time()) - 100,),
        )
        relay_with_db._db.commit()
    assert relay_with_db.slot_lookup(1) is None


def test_set_last_message(relay_with_db):
    relay_with_db.slot_allocate_or_reuse(101)
    relay_with_db.slot_set_last_message(1, "Hello there")
    rows = relay_with_db.slot_list_active()
    assert rows[0]["last_message"] == "Hello there"


def test_mark_replied_sets_flag_and_sticky_ttl(relay_with_db):
    """После mark_replied — was_replied=1, expires_at = now + STICKY_HOURS.

    Заметим: STICKY < TTL (default 10ч < 20ч), так что expires_at
    может СОКРАТИТЬСЯ. Это by-design: TTL для незаотвеченных, STICKY —
    для активного диалога после ответа.
    """
    relay_with_db.slot_allocate_or_reuse(101)
    relay_with_db.slot_mark_replied(1)
    rows = relay_with_db.slot_list_active()
    assert rows[0]["was_replied"] == 1
    # expires_at в окрестности now + STICKY_HOURS*3600
    expected = int(time.time()) + relay_with_db.SLOT_STICKY_HOURS * 3600
    assert abs(rows[0]["expires_at"] - expected) <= 5  # секундная дельта


def test_expire_old_removes_only_expired(relay_with_db):
    relay_with_db.slot_allocate_or_reuse(101)
    relay_with_db.slot_allocate_or_reuse(102)
    # Делаем slot 1 expired
    with relay_with_db._db_lock:
        relay_with_db._db.execute(
            "UPDATE slots SET expires_at = ? WHERE slot_n = 1",
            (int(time.time()) - 100,),
        )
        relay_with_db._db.commit()

    freed = relay_with_db.slot_expire_old()
    assert freed == [1]
    # slot 2 жив
    assert relay_with_db.slot_lookup(2) == 102


def test_free_all_for_user(relay_with_db):
    relay_with_db.slot_allocate_or_reuse(101)
    relay_with_db.slot_allocate_or_reuse(101)  # reuse same
    relay_with_db.slot_free_all_for_user(101)
    rows = relay_with_db.slot_list_active()
    assert rows == []
