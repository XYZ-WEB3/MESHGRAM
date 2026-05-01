"""
Тесты UTF-8 chunking длинных сообщений (v0.6) и формата LoRa-пакета.
"""


class _FakeUser:
    """Минимальный Telegram-User-like объект для _format_lora_packet."""
    def __init__(self, username=None, first_name=None, id_=1):
        self.username = username
        self.first_name = first_name
        self.id = id_


def test_chunk_short_text(relay_module):
    """Короткий текст — один чанк, без изменений."""
    chunks = relay_module._chunk_text("hello world", 100)
    assert chunks == ["hello world"]


def test_chunk_empty_text(relay_module):
    chunks = relay_module._chunk_text("", 100)
    assert chunks == [""]


def test_chunk_exact_fit(relay_module):
    """Текст ровно в max_chars — один чанк."""
    text = "a" * 100
    chunks = relay_module._chunk_text(text, 100)
    assert chunks == [text]


def test_chunk_long_text_no_spaces(relay_module):
    """Длинный текст без пробелов — режется по символам."""
    text = "a" * 350
    chunks = relay_module._chunk_text(text, 100)
    assert len(chunks) == 4
    assert chunks[0] == "a" * 100
    assert chunks[1] == "a" * 100
    assert chunks[2] == "a" * 100
    assert chunks[3] == "a" * 50


def test_chunk_long_text_with_spaces(relay_module):
    """Длинный текст с пробелами — режется по последнему пробелу в окне."""
    text = "слово " * 50  # ≈ 350 символов
    chunks = relay_module._chunk_text(text, 100)
    assert len(chunks) >= 3
    # Никакой чанк не превышает max
    for c in chunks:
        assert len(c) <= 100
    # Все слова сохранились (можно склеить с пробелом и сравнить)
    rejoined = " ".join(chunks).replace("  ", " ").strip()
    assert "слово слово слово" in rejoined


def test_chunk_total_length_preserved(relay_module):
    """Сумма длин чанков ≈ длине оригинала (с поправкой на trim)."""
    text = "Lorem ipsum dolor sit amet, " * 20
    chunks = relay_module._chunk_text(text, 80)
    total = sum(len(c) for c in chunks)
    # +/- небольшая разница из-за trim'а пробелов
    assert abs(total - len(text.strip())) <= len(chunks) * 2


# ---------------------- format_lora_packet ----------------------

def test_format_single_no_tag(relay_module):
    user = _FakeUser(username="vasya")
    out = relay_module._format_lora_packet(3, user, "hello")
    assert out.startswith("[@3 vasya ")
    assert out.endswith("] hello")
    # Не содержит chunks-marker
    assert "/" not in out.split("] ")[0]


def test_format_single_with_tag(relay_module):
    user = _FakeUser(username="vasya")
    out = relay_module._format_lora_packet(3, user, "hello", entry_tag="work")
    assert "work:vasya" in out


def test_format_multi_chunk(relay_module):
    user = _FakeUser(username="vasya")
    out1 = relay_module._format_lora_packet(
        3, user, "first part", chunk_idx=0, chunks_total=3,
    )
    assert " 1/3]" in out1
    assert out1.endswith("] first part")

    out3 = relay_module._format_lora_packet(
        3, user, "last part", chunk_idx=2, chunks_total=3,
    )
    assert " 3/3]" in out3


def test_format_user_without_username_fallback_first_name(relay_module):
    user = _FakeUser(username=None, first_name="Иван")
    out = relay_module._format_lora_packet(1, user, "hi")
    assert "Иван" in out


def test_format_user_without_anything_fallback_id(relay_module):
    user = _FakeUser(username=None, first_name=None, id_=42)
    out = relay_module._format_lora_packet(1, user, "hi")
    assert "42" in out


def test_format_user_none(relay_module):
    out = relay_module._format_lora_packet(1, None, "hi")
    # _sender_tag returns "?" for None
    assert "?" in out


def test_format_username_truncated(relay_module):
    """Длинный username режется до MAX_USERNAME_IN_PREFIX (default 10)."""
    user = _FakeUser(username="vasyapupkinverylonghandle")
    out = relay_module._format_lora_packet(1, user, "hi")
    # vasyapupki — первые 10 символов
    assert "vasyapupki" in out
    assert "vasyapupkinverylong" not in out
