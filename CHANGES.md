# Что нового

Журнал изменений с момента последнего пуша (commit `342eb84` — v0.5 full rewrite).

---

## v0.5.1 — стабильность и скорость

### 🛡 Auto-restart на сетевых сбоях Telegram

Раньше: `NetworkError` (DNS-сбой, обрыв канала к `api.telegram.org`) ронял весь процесс. Юзеру нужно было руками перезапускать. Теперь — `_run_polling_with_retry()` в `relay.py`:

- Ловит `NetworkError`, `TimedOut`, `Conflict`, `RetryAfter`, `KeyboardInterrupt` и любые непредвиденные исключения по отдельности
- Экспоненциальный backoff: 5с → 10с → 20с → 40с → 80с → ... → cap 5 минут
- Если бот успел проработать стабильно ≥ 60 секунд — backoff сбрасывается к initial. Иначе разовый моргнувший интернет раскручивал бы паузу до 5 минут
- `RetryAfter` (Telegram прямо говорит «подожди N сек») — уважаем точно столько, потом сразу пробуем
- `KeyboardInterrupt` и нормальный return — выходят из цикла чисто

**Подтверждение:** smoke-тесты с моками — 4 сценария проходят (NetworkError, Conflict, KeyboardInterrupt, clean shutdown) с правильной таймингом backoff'а.

### 📝 Logging в файл с ротацией

Раньше: только stdout. Если GUI закрыли или бот рухнул — история событий потеряна.

Теперь: `RotatingFileHandler` пишет `relay/relay.log` параллельно stdout. Тот же формат:

```
2026-04-28 14:42:39,636 [INFO] relay: Mesh RX from !1ba6795c: @1 ок
```

Настройки в `.env` (с дефолтами):

```env
LOG_FILE_ENABLED=true        # master-switch
LOG_FILE_MAX_MB=5            # размер файла перед ротацией
LOG_FILE_KEEP=5              # сколько бэкапов хранить (relay.log.1 ... .5)
```

Файл сам ротируется: `relay.log` растёт до 5 МБ → переименуется в `.1`, новый идёт в `relay.log`. Хранится 5 поколений = ~25 МБ истории. Если лог-файл нельзя открыть (read-only fs / permission) — бот не падает, продолжает писать в stdout с warning'ом.

`relay.log*` уже в `.gitignore` — случайно не закоммитится.

### ⚡ Latency batch — TG → pocket стало быстрее

**Проблема которую решали:** на тесте с двумя нодами в 1м друг от друга TG → pocket шло 10–15 секунд, а pocket → TG ровно те же 3–5 секунд. Асимметрия 3×, не из-за радио (канал идеален) — из-за кода и default'ов прошивки.

#### FIX-2: `hopLimit=1` на исходящих DM

`_mesh_iface.sendText` раньше шёл с дефолтным `hopLimit` (~3) → пакет ждал окно ретрансляции через до 2 промежуточных нод, даже когда они напрямую видят друг друга. Теперь:

```env
MESH_HOP_LIMIT=1
```

`1` = только прямая видимость, без ретрансляторов. Если pocket-нода уйдёт за угол и нужны промежуточные — поднять до `3` в `.env` без правки кода. Поведение прошивки идентично — она всё равно ждёт ACK от destination, просто без бесконечной ретрансляции.

**Выигрыш:** −5…15 секунд на пакет в локальной сети.

#### FIX-1: параллелизация TG-статуса и LoRa-передачи в `handle_text`

Раньше:

```
1. await reply_text("📨 Передаю...")     # 500-1000 мс HTTP RTT
2. send_dm_to_pocket(payload)             # ПОТОМ — в эфир
```

Теперь обе операции идут параллельно через `asyncio.create_task` + `asyncio.to_thread`. ACK callback захватывает `chat_id` через closure (не зависит от `status_msg`) — race-condition нет. Если placeholder упал (TG NetworkError), но mesh-передача прошла — «✓ Доставлено» всё равно дойдёт юзеру через `_handle_ack_event`.

**Выигрыш:** −300…1000 мс на каждое сообщение.

#### FIX-3: `threading.Lock` внутри `send_dm_to_pocket` + `send_dm_to_pocket_async()` обёртка

Раньше `_mesh_iface.sendText(...)` синхронно блокировал asyncio event loop на 50–200 мс. Под нагрузкой 5+ конкурентных пользователей это ощутимо. Теперь:

```python
_mesh_send_lock = threading.Lock()      # внутри send_dm_to_pocket

async def send_dm_to_pocket_async(text, on_ack=None):
    await asyncio.to_thread(send_dm_to_pocket, text, on_ack)
```

Все async-callers (22 сайта в `_handle_mesh_event`, `_handle_sos`, `retry_worker`, `cmd_retry_cb`, `handle_text` admin echo и main) переехали на `await send_dm_to_pocket_async(...)`. USB-write теперь идёт в thread-pool, event loop живой, остальные обработчики (TG-команды, mesh_dispatcher) не подвисают.

**Лок** гарантирует серийность отправок: радио всё равно физически передаёт один пакет в моменте — лок просто матчит реальность и убирает любые гонки на `_mesh_iface`. `threading.Lock` работает и для sync-, и для async-callers (последние используют `to_thread`, не блокируют loop).

**Подтверждение:** smoke-тест с 3 параллельными `send_dm_to_pocket_async()` — 0 overlapping write-окон, лок работает.

#### FIX-5: `poll_interval=0.3, timeout=30` для `app.run_polling()`

Стандартные production-значения PTB — раньше дефолты были немного медленнее на reception side.

**Выигрыш:** −0…700 мс задержки на входящие TG-сообщения.

### ⚙️ FIX-4 (manual tweak, не код): Modem Preset на нодах

Не правка проекта — настройка прошивки Meshtastic через мобильное приложение. На **обеих** нодах:

> Settings → LoRa → Modem Preset → MediumFast (или ShortFast если ноды в 1 м)

| Preset | Airtime ~200B | Дистанция |
|---|---|---|
| LongFast (default) | ~1.5 с | 5+ км |
| MediumFast | ~0.4 с | 2-3 км |
| ShortFast | ~0.15 с | <1 км |

**Critical:** preset должен совпадать на обеих нодах, иначе они не услышат друг друга вообще. Срезает ~70% airtime пакета — самый большой выигрыш для близкого расстояния, но требует пользовательского действия (мы из Python это не переключаем).

---

## Резюме что осталось от прошлого пуша

| Что | Где | Эффект |
|---|---|---|
| Auto-restart `NetworkError` | `relay.py` `_run_polling_with_retry` | Бот не падает на DNS-сбое |
| Logging в файл с ротацией | `relay.py` `_setup_logging` + 3 ключа `.env` | Журнал не теряется при закрытии GUI |
| `MESH_HOP_LIMIT=1` | `settings.py` + `send_dm_to_pocket` | −5…15 с / пакет |
| Параллель TG/LoRa | `handle_text` | −0.3…1 с / сообщение |
| `_mesh_send_lock` + `send_dm_to_pocket_async` | 22 сайта | Event loop живой под нагрузкой |
| `poll_interval=0.3` | `_run_polling_with_retry` | −0…0.7 с на reception |

**Что НЕ изменилось:** retry_queue + retry_worker, slot-менеджер `@N` с sticky-TTL, `_mesh_queue` декаплинг, ACK-флоу через `onResponse`, `_show_status` fallback с edit на новое сообщение, whitelist / ban / SOS / GPS / categories, контракт `send_dm_to_pocket(text, on_ack)`.

**Миграция для пользователя:** ничего делать не нужно. Новые ключи `.env` (`MESH_HOP_LIMIT`, `LOG_FILE_*`) подцепятся из DEFAULTS если в локальном `.env` их нет. Хочешь перетюнить — добавь руками или через GUI.

---

## За пределами кода (production deploy)

В этой же сессии (но на сервере, не в репо):

- **meshgram.site обновлён** — задеплоена готовая статика (index.html + lora_map.html + screenshots)
- **Голоса сброшены** на нули (все `base: 0`, localStorage ключ bumped до v3)
- **Telegram brand убран** из видимых текстов сайта (`Telegram` → `мессенджер`, `TG-бот` → `чат-бот`, и т.п. — 30+ замен)
- **Backend admin password** настроен и работает (`/api/admin/login` отвечает токеном)
- **HTTPS / Let's Encrypt** — автоматически через Caddy, auto-renew работает

Эта часть не попадает в коммиты репо (сайт в отдельной папке, бэкенд только на сервере), но является частью прогресса проекта за день.
