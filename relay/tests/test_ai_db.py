"""
Тесты AI conversation БД-хелперов (v0.7):
ai_alloc_slot, ai_touch_slot, ai_save_message, ai_get_history,
ai_expire_old, ai_slot_exists.
"""
import time


def test_alloc_first_slot(relay_with_db):
    slot = relay_with_db.ai_alloc_slot()
    assert slot == 1
    assert relay_with_db.ai_slot_exists(1) is True


def test_alloc_increment(relay_with_db):
    s1 = relay_with_db.ai_alloc_slot()
    s2 = relay_with_db.ai_alloc_slot()
    s3 = relay_with_db.ai_alloc_slot()
    assert (s1, s2, s3) == (1, 2, 3)


def test_slot_exists_false_for_unknown(relay_with_db):
    assert relay_with_db.ai_slot_exists(99) is False


def test_save_and_get_history(relay_with_db):
    slot = relay_with_db.ai_alloc_slot()
    relay_with_db.ai_save_message(slot, "user", "первый вопрос")
    relay_with_db.ai_save_message(slot, "assistant", "первый ответ")
    relay_with_db.ai_save_message(slot, "user", "второй вопрос")

    hist = relay_with_db.ai_get_history(slot, max_messages=10)
    # asc по ts: старые сначала
    assert len(hist) == 3
    assert hist[0] == {"role": "user", "content": "первый вопрос"}
    assert hist[1] == {"role": "assistant", "content": "первый ответ"}
    assert hist[2] == {"role": "user", "content": "второй вопрос"}


def test_get_history_respects_limit(relay_with_db):
    slot = relay_with_db.ai_alloc_slot()
    for i in range(20):
        relay_with_db.ai_save_message(slot, "user", f"msg {i}")
        # ts увеличивается на 1 секунду чтобы порядок был стабилен
        time.sleep(0.001)

    hist = relay_with_db.ai_get_history(slot, max_messages=5)
    assert len(hist) == 5
    # Последние 5 (msg 15-19) в порядке asc
    assert hist[0]["content"] == "msg 15"
    assert hist[4]["content"] == "msg 19"


def test_get_history_empty(relay_with_db):
    slot = relay_with_db.ai_alloc_slot()
    hist = relay_with_db.ai_get_history(slot, max_messages=10)
    assert hist == []


def test_history_isolated_per_slot(relay_with_db):
    s1 = relay_with_db.ai_alloc_slot()
    s2 = relay_with_db.ai_alloc_slot()
    relay_with_db.ai_save_message(s1, "user", "in slot 1")
    relay_with_db.ai_save_message(s2, "user", "in slot 2")

    h1 = relay_with_db.ai_get_history(s1, 10)
    h2 = relay_with_db.ai_get_history(s2, 10)
    assert len(h1) == 1
    assert len(h2) == 1
    assert h1[0]["content"] == "in slot 1"
    assert h2[0]["content"] == "in slot 2"


def test_touch_slot_returns_true_for_existing(relay_with_db):
    slot = relay_with_db.ai_alloc_slot()
    assert relay_with_db.ai_touch_slot(slot) is True
    assert relay_with_db.ai_touch_slot(99) is False


def test_expire_old_removes_inactive(relay_with_db):
    """Чат, не использовавшийся > ttl — удаляется. Свежий — остаётся."""
    s_old = relay_with_db.ai_alloc_slot()
    s_new = relay_with_db.ai_alloc_slot()
    relay_with_db.ai_save_message(s_old, "user", "стар")
    relay_with_db.ai_save_message(s_new, "user", "свеж")

    # Делаем s_old устаревшим (last_used_at в прошлом)
    with relay_with_db._db_lock:
        relay_with_db._db.execute(
            "UPDATE ai_conversations SET last_used_at = ? WHERE slot_n_ai = ?",
            (int(time.time()) - 8 * 3600, s_old),
        )
        relay_with_db._db.commit()

    # ttl=4 часа: s_old expired (8h назад), s_new ОК
    freed = relay_with_db.ai_expire_old(ttl_hours=4)
    assert s_old in freed
    assert s_new not in freed
    # Сообщения тоже удалились (CASCADE)
    assert relay_with_db.ai_get_history(s_old, 10) == []
    # Слот свежего цел
    assert relay_with_db.ai_slot_exists(s_new) is True


def test_alloc_reuses_lowest_free(relay_with_db):
    """После expire — наименьший свободный slot переиспользуется."""
    s1 = relay_with_db.ai_alloc_slot()
    s2 = relay_with_db.ai_alloc_slot()
    s3 = relay_with_db.ai_alloc_slot()
    assert (s1, s2, s3) == (1, 2, 3)

    # Удаляем slot 2 руками (имитируем expire одного)
    with relay_with_db._db_lock:
        relay_with_db._db.execute("DELETE FROM ai_conversations WHERE slot_n_ai = 2")
        relay_with_db._db.commit()

    s4 = relay_with_db.ai_alloc_slot()
    assert s4 == 2  # переиспользовали освободившийся
