"""
Тесты parse_mesh_text — парсера mesh-сообщений с pocket-ноды.
Все 7 категорий: sos / ai_followup / ai_new / standalone_cmd / slot_cmd /
slot_reply / raw. Особое внимание ai-парсингу — он добавлен в v0.7 и
должен срабатывать ДО общего @N (иначе «@ai1» матчился бы как N=ai1).
"""


def test_parse_raw(relay_module):
    r = relay_module.parse_mesh_text("просто текст без префиксов")
    assert r == {"kind": "raw", "text": "просто текст без префиксов"}


def test_parse_sos_no_text(relay_module):
    r = relay_module.parse_mesh_text("#SOS")
    assert r["kind"] == "sos"
    assert r["text"] == ""


def test_parse_sos_with_text(relay_module):
    r = relay_module.parse_mesh_text("#SOS помогите")
    assert r == {"kind": "sos", "text": "помогите"}


def test_parse_sos_case_insensitive(relay_module):
    assert relay_module.parse_mesh_text("#sos help")["kind"] == "sos"
    assert relay_module.parse_mesh_text("#Sos Help")["kind"] == "sos"


def test_parse_standalone_cmd_no_args(relay_module):
    r = relay_module.parse_mesh_text("!status")
    assert r == {"kind": "standalone_cmd", "cmd": "status", "args": ""}


def test_parse_standalone_cmd_with_args(relay_module):
    r = relay_module.parse_mesh_text("!fav 12345 заметка")
    assert r == {"kind": "standalone_cmd", "cmd": "fav", "args": "12345 заметка"}


def test_parse_slot_reply(relay_module):
    r = relay_module.parse_mesh_text("@3 ответ юзеру")
    assert r == {"kind": "slot_reply", "n": 3, "text": "ответ юзеру"}


def test_parse_slot_reply_multidigit(relay_module):
    r = relay_module.parse_mesh_text("@42 hi")
    assert r == {"kind": "slot_reply", "n": 42, "text": "hi"}


def test_parse_slot_cmd(relay_module):
    r = relay_module.parse_mesh_text("@5 !ban")
    assert r == {"kind": "slot_cmd", "n": 5, "cmd": "ban", "args": ""}


def test_parse_slot_cmd_with_args(relay_module):
    r = relay_module.parse_mesh_text("@7 !fav заметка для Васи")
    assert r["kind"] == "slot_cmd"
    assert r["n"] == 7
    assert r["cmd"] == "fav"
    assert r["args"] == "заметка для Васи"


# ---------------------- AI parsing (v0.7) ----------------------

def test_parse_ai_new(relay_module):
    r = relay_module.parse_mesh_text("@ai как форматировать дату в Python")
    assert r == {"kind": "ai_new", "text": "как форматировать дату в Python"}


def test_parse_ai_new_case_insensitive(relay_module):
    assert relay_module.parse_mesh_text("@AI hello")["kind"] == "ai_new"
    assert relay_module.parse_mesh_text("@Ai test")["kind"] == "ai_new"


def test_parse_ai_followup(relay_module):
    r = relay_module.parse_mesh_text("@ai1 а если с миллисекундами?")
    assert r == {"kind": "ai_followup", "n": 1, "text": "а если с миллисекундами?"}


def test_parse_ai_followup_multidigit(relay_module):
    r = relay_module.parse_mesh_text("@ai42 продолжай")
    assert r == {"kind": "ai_followup", "n": 42, "text": "продолжай"}


def test_parse_ai_does_not_collide_with_slot(relay_module):
    """«@3 hi» не должен матчиться как ai (ai требует «@ai»)."""
    r = relay_module.parse_mesh_text("@3 hi")
    assert r["kind"] == "slot_reply"


def test_parse_ai_followup_does_not_match_short_at(relay_module):
    """«@a 123» — не AI (должно быть @ai), и не slot (не цифра)."""
    r = relay_module.parse_mesh_text("@a 123")
    # Не sos, не ai_*, не standalone (нет !), не slot (не цифра) → raw
    assert r["kind"] == "raw"


def test_parse_ai_no_args(relay_module):
    """«@ai» без вопроса — пустой запрос. Regex требует пробел + текст."""
    # Голое @ai — должно попасть в raw (нет matching на @ai\s+(.+))
    r = relay_module.parse_mesh_text("@ai")
    assert r["kind"] == "raw"


def test_parse_empty(relay_module):
    r = relay_module.parse_mesh_text("")
    assert r["kind"] == "raw"
    assert r["text"] == ""
