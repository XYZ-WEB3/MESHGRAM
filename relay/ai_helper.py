"""
AI-помощник через OpenAI-совместимый endpoint.

Целевой сценарий: локальный LM Studio (или Ollama / vLLM) на порту 1234,
к которому подключается relay.py. Пользователь с pocket-ноды пишет
«@ai <вопрос>» — приходит ответ. Продолжение диалога — «@ai1 <вопрос>».

Ничего OpenAI-облачного по дефолту: AI_BASE_URL=http://localhost:1234/v1,
AI_API_KEY=lm-studio (LM Studio принимает любой непустой). Если
пользователь хочет OpenAI/Anthropic/etc — меняет URL и ключ в .env.

Зависит от пакета `openai` (>=1.0). Импорт ленивый — если pip install
не сделан или AI_ENABLED=False, релей всё равно стартует.
"""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger(__name__)


_client = None
_initialized = False
_init_error: Optional[str] = None


def _normalize_base_url(url: str) -> str:
    """Гарантирует что base_url содержит path-segment (/v1 по умолчанию).

    LM Studio, Ollama, OpenAI ждут endpoints на `<base>/chat/completions`,
    `<base>/models` и т.п. Если юзер впишет в GUI просто `http://127.0.0.1:1234`
    (без `/v1`) — AsyncOpenAI отправит запрос на `/chat/completions` минуя
    нужный prefix, LM Studio вернёт 200 с пустым body и наш парсинг упадёт.

    Правило: если URL не содержит path (только хост:порт) или path = `/` —
    добавляем `/v1`. Иначе оставляем как есть (юзер мог явно указать `/v2`,
    кастомный proxy и т.п.).
    """
    from urllib.parse import urlparse

    if not url:
        return url
    try:
        parsed = urlparse(url)
    except Exception:
        return url
    if not parsed.scheme:
        return url
    path = (parsed.path or "").strip("/")
    if path == "":
        return url.rstrip("/") + "/v1"
    return url


def _try_init(base_url: str, api_key: str, timeout_sec: int) -> bool:
    """Ленивая инициализация AsyncOpenAI. Падение → сохраняем причину
    в _init_error, релей продолжает работать без AI."""
    global _client, _initialized, _init_error
    if _initialized:
        return _client is not None
    _initialized = True
    try:
        from openai import AsyncOpenAI  # type: ignore
    except ImportError as exc:
        _init_error = (
            f"Пакет `openai` не установлен ({exc}). "
            "Поставь: pip install openai"
        )
        log.warning("AI helper: %s", _init_error)
        return False
    try:
        normalized_url = _normalize_base_url(base_url)
        if normalized_url != base_url:
            log.info("AI base URL normalized: %r → %r", base_url, normalized_url)
        _client = AsyncOpenAI(
            base_url=normalized_url,
            api_key=api_key or "lm-studio",
            timeout=timeout_sec,
        )
    except Exception as exc:
        _init_error = f"AsyncOpenAI init failed: {exc}"
        log.warning("AI helper: %s", _init_error)
        _client = None
        return False
    return True


async def chat(
    history: list[dict],
    *,
    model: str,
    base_url: str,
    api_key: str,
    timeout_sec: int = 30,
) -> str:
    """Отправить chat-completion запрос.

    `history` — список сообщений в OpenAI-формате:
        [{"role": "system", "content": "..."},
         {"role": "user", "content": "..."},
         {"role": "assistant", "content": "..."},
         ...]

    Возвращает текст ответа модели. Бросает исключение если AI недоступен,
    сетевая ошибка, или модель вернула пустой ответ. Вызывающий код должен
    обернуть в try/except.
    """
    if not _try_init(base_url, api_key, timeout_sec):
        raise RuntimeError(_init_error or "AI client not initialized")
    assert _client is not None

    resp = await _client.chat.completions.create(
        model=model,
        messages=history,
        temperature=0.7,
        max_tokens=512,    # режем длинные ответы; chunking всё равно сделает
                          # своё дело, но не хочется ждать бесконечный stream
    )

    if not resp.choices:
        raise RuntimeError("AI вернул пустой response")
    text = (resp.choices[0].message.content or "").strip()
    if not text:
        raise RuntimeError("AI вернул пустой текст")
    return text


def is_available() -> bool:
    """True если последняя попытка инициализации прошла успешно."""
    return _initialized and _client is not None


def init_error() -> Optional[str]:
    """Последняя ошибка инициализации (для отладочного сообщения юзеру)."""
    return _init_error


def list_models(base_url: str, api_key: str = "lm-studio",
                timeout: int = 5) -> list[str]:
    """Sync HTTP GET на ${base_url}/models. Возвращает список model id'шников.

    Используется в Settings dialog для авто-заполнения дропдауна моделей.
    Не использует AsyncOpenAI чтоб не блокировать GUI и не требовать
    asyncio. Простой requests.get.

    Бросает исключение при сетевой ошибке / non-200 / битом JSON —
    вызывающий код покажет это юзеру в виде «⚠ <тип>: <текст>».
    """
    import requests   # уже в зависимостях через meshtastic-python

    base_url = _normalize_base_url(base_url)
    url = base_url.rstrip("/") + "/models"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    # OpenAI-совместимый формат: {"data": [{"id": "...", ...}, ...]}
    items = payload.get("data") or payload.get("models") or []
    out: list[str] = []
    for item in items:
        if isinstance(item, dict):
            mid = item.get("id") or item.get("name")
            if mid:
                out.append(str(mid))
        elif isinstance(item, str):
            out.append(item)
    return out
