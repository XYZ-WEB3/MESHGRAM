"""
Тесты _is_urgent — детектора SOS-маркеров в тексте сообщения.
Используется для fast-retry (5/15/30/60/120 сек вместо 2-15 минут).
"""


def test_urgent_sos(relay_module):
    assert relay_module._is_urgent("#SOS")
    assert relay_module._is_urgent("#SOS помогите")
    assert relay_module._is_urgent("#sos lowercase")
    assert relay_module._is_urgent("это #SOS внутри текста")


def test_urgent_russian(relay_module):
    assert relay_module._is_urgent("срочно")
    assert relay_module._is_urgent("СРОЧНО")
    assert relay_module._is_urgent("это срочно")
    assert relay_module._is_urgent("надо срочно ответить")


def test_urgent_english(relay_module):
    assert relay_module._is_urgent("urgent")
    assert relay_module._is_urgent("URGENT")
    assert relay_module._is_urgent("emergency")
    assert relay_module._is_urgent("this is urgent please")


def test_not_urgent_plain(relay_module):
    assert not relay_module._is_urgent("привет")
    assert not relay_module._is_urgent("hello world")
    assert not relay_module._is_urgent("любой обычный текст")


def test_not_urgent_substring_safety(relay_module):
    """Слово 'срочно' внутри другого слова не должно матчиться (\\b boundaries)."""
    assert not relay_module._is_urgent("несрочное дело")
    # 'urgent' тоже с word-boundary
    assert not relay_module._is_urgent("urgents")  # не отдельное слово


def test_not_urgent_empty(relay_module):
    assert not relay_module._is_urgent("")
    assert not relay_module._is_urgent(None)


def test_urgent_sos_priority_over_other(relay_module):
    """#SOS внутри текста с другими словами тоже должен сработать."""
    assert relay_module._is_urgent("привет #SOS я в беде")
