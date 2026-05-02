# Что нового

Журнал изменений с момента последнего пуша (commit `342eb84` — v0.5 full rewrite).

---

## v0.7.3 — настройки в GUI, AI-конфиг, security audit

### Settings GUI: 4 новые секции

В `Meshgram.exe` без правки `.env` руками теперь редактируется всё:

- **Mesh · LoRa** — `MESH_HOP_LIMIT` (1 для прямой видимости, 3 для через ROUTER-ноды) и переключатель Reliable / Fast (фича `MESH_DELIVERY_MODE` из v0.6, до сих пор настраивалась только в `.env`)
- **AI-помощник** — все 9 ключей плюс кнопка **Test connection** к OpenAI-совместимому endpoint'у и **dropdown с автозагрузкой моделей** через `GET /v1/models`
- **Логи** — `LOG_FILE_ENABLED`, `LOG_FILE_MAX_MB`, `LOG_FILE_KEEP`
- **Интерфейс** — переключатель языка (RU / EN) с уведомлением «применится после перезапуска»

Существующая секция Limits уже содержала retry-настройки (`RETRY_INITIAL_DELAY_MIN`, `RETRY_MAX_INTERVAL_MIN`) — ничего там не дублирую.

### AI helper: настраиваемый тег команды

Раньше `@ai <вопрос>` был захардкожен в regex. Теперь `AI_TRIGGER_TAG` в настройках (default `ai`, можно `gpt`, `llm` и т.п.). Regex'ы компилируются динамически при старте релея с учётом текущего тега. Все ответы AI пользователю используют этот же тег (`@<tag>N <answer>`).

`ai_helper.list_models(base_url, api_key)` — синхронный HTTP-клиент через `requests` для GET `/v1/models`. Используется в Settings dialog для авто-заполнения dropdown'а — кнопка **⟳** опрашивает endpoint, на основе ответа заполняется список моделей. Кнопка **«Проверить подключение»** отдельно показывает «✓ N моделей доступно» либо ошибку.

### Локализация GUI: меню и toolbar

`gui.py:_build_menu()` теперь использует `i18n_gui.t()` для всех QAction'ов. Файл / Правка / Вид / Сервис / Справка и все элементы под ними переведены на EN. После сохранения нового языка в Settings показывается уведомление, что для полного применения нужен перезапуск (трей и диалоги обновляются на лету).

### Security audit fixes

Внешний аудит обнаружил 4 critical и 5 high. Исправлено:

- **C1+C2**: Caddyfile получил path-based deny через `path_regexp` для `*.py`, `*.env`, `*.db`, `*.spec`, `*.log`, `*.key`, `*.pem` плюс директории `/__pycache__/`, `/.git/`, `/deploy/`, `/handlers/`, `/services/`, `/core/`, `/demo_bot/` и явные пути `/backend.py`, `/requirements.txt`. Защита в два уровня: даже если что-то случайно затащено в `/var/www/` через rsync — Caddy отдаст 404, а не прокинет через `try_files` на `index.html`. Дополнительно `site/deploy/DEPLOY.md` обновлён правильными rsync-флагами `--exclude '.env'` `--exclude '*.db'` `--exclude '*.py'` `--exclude 'demo_bot/'` etc.

- **C3** (X-Forwarded-For без trust check): `backend.py:get_client_ip()` теперь доверяет заголовку **только** если запрос пришёл с loopback (Caddy). Любой другой источник → используется `request.client.host` напрямую. Это закрывает обход rate-limit, brute-force админки и накрутку голосов через подделку IP.

- **C4** (Stored XSS): `index.html` в публичной голосовалке экранирует `opt.title` и `opt.desc` через `escapeHtml()`. Раньше шло как `${opt.title}` в `innerHTML` — админ-вью уже было защищено, публичное — нет.

- **H1** (HTML-инъекция через `first_name` в админ-уведомлениях о донатах): `demo_bot/handlers/donate.py:_notify_donation()` теперь `html.escape()` для `username`, `first_name` и `method` перед подстановкой в HTML-сообщение.

- **H3** (CORS с localhost:8765 + credentials): убран `localhost:8765` из `allow_origins`, оставлен только `https://meshgram.site`.

- **H4** (pre_checkout без validation): `demo_bot/handlers/donate.py:on_pre_checkout()` проверяет формат `invoice_payload` — должен быть `donate:stars:<uid>:<amount>:<ts>`. Невалидный → `query.answer(ok=False)` с сообщением.

Что **не делалось**: `H2` (один пользователь под demo_bot и сайт) — это инфраструктурный refactor, отложен. `H5` (BOT_TOKEN на диске) — design choice, см. README.

Аудит relay-кода (того что в этом репо) ранее проблем не обнаружил.

---

## v0.7.2 — фиксы wizard'а и архитектуры frozen-сборки

В v0.7.1 готовый `.exe` падал в трёх местах. Этот патч их закрывает.

### BUG #1: wizard крашил на «Назад» / «Готово»

`OnboardingDialog._render` пересоздавал страницы через `deleteLater()`, но Python-атрибуты `self.ed_token`, `self.ed_owner`, `self.ed_pocket` оставались как dangling references на уже уничтоженные C++ Qt-объекты. При следующем `_render` проверка `hasattr(self, "ed_token")` возвращала `True`, но `addWidget(self.ed_token)` падал с `RuntimeError: wrapped C/C++ object has been deleted`.

**Фикс**: переписал диалог на `QStackedWidget`. Все 4 страницы создаются один раз в `_build_ui` и переключаются через `setCurrentIndex` — никаких уничтожений-пересозданий, никакого риска dangling-references.

### BUG #2: настройки сохранялись во временную папку и терялись

В onefile-сборке PyInstaller при запуске распаковывает bundle в `%TEMP%\_MEIxxxxx\` и `__file__` указывает туда. `settings.py` вычислял путь к `.env` как `Path(__file__).with_name('.env')` — то есть пытался писать в распакованную временную папку. На каждом запуске PyInstaller создаёт **новую** временную папку, поэтому даже если запись проходила, при следующем запуске настройки терялись.

**Фикс**: новый модуль `relay/paths.py` определяет два разных понятия пути:
- `APP_DATA_DIR` — пользовательские данные (`.env`, `relay.db`, `relay.log`). В frozen — **рядом с `.exe`** (`Path(sys.executable).parent`). В source — рядом с `relay.py`.
- `RESOURCE_DIR` — read-only ресурсы (иконки, SVG моделей нод). В frozen — `sys._MEIPASS`. В source — рядом с `relay.py`.

Юзер теперь может скопировать папку с `Meshgram.exe` и `.env` на другой ПК — всё переедет вместе. Настройки переживают перезапуск.

### BUG #3: кнопка «Старт» в `.exe` не запускала релей

`gui.py` стартовал релей через `QProcess.start(sys.executable, [str(RELAY_SCRIPT)])`. В frozen-сборке `sys.executable` — это `Meshgram.exe`, а не `python.exe`. Передача ему пути к `relay.py` ничего не запускала.

**Фикс**: единый бинарник, два режима. В `gui.py:main()` проверяется флаг `--relay`:

```python
if "--relay" in sys.argv:
    sys.argv.remove("--relay")
    import relay as relay_module
    relay_module.main()
    return
```

Когда GUI хочет запустить релей, он вызывает `sys.executable --relay --port COMx`. Это запускает копию `Meshgram.exe`, которая благодаря флагу превращается в релей-процесс.

### Локализация GUI (RU + EN)

Новый модуль `relay/i18n_gui.py` со словарём строк (~50 ключей покрывают wizard, system tray, single-instance MessageBox, кнопки выхода). Расширяемая структура: `t(key, lang)` падает на RU при отсутствии перевода.

Wizard теперь начинается с **выбора языка** — это шаг 0 из 4. Дальше идут токен / Telegram ID / pocket node ID, как раньше. Язык сохраняется в `settings.gui_lang` и применяется на лету (`@lang en` меняет UI без перезапуска).

Что **переведено** в этом патче:
- Полный wizard первого запуска (4 шага + кнопки + warnings)
- System tray меню (Open / Start / Stop / Quit)
- MessageBox при второй копии («Meshgram уже запущен»)
- Confirm-on-quit диалог
- Уведомление «свёрнут в трей»

Что **пока на русском** (отдельной задачей в roadmap):
- SettingsDialog (~30 строк, объёмно)
- AboutDialog, UsersDialog, SlotsDialog
- Тексты в релей-стороне (`relay.py` user-facing) — через `i18n_gui` придётся, но 200+ строк

### Прочее

- Тесты остались зелёными (67 passed) после рефакторинга
- `Meshgram.spec` подключает новые модули (`paths.py`, `i18n_gui.py`)
- `relay/Meshgram.exe` — пересобран, ~74 МБ

---

## v0.7.1 — тесты, упакованный .exe, tray и single-instance

### Тесты (pytest)

`relay/tests/` — 67 unit-тестов покрывают: парсер mesh-сообщений (все 7 веток включая новые `@ai`/`@aiN`), `_chunk_text` и `_format_lora_packet`, `_is_urgent` для SOS fast-retry, sticky-логику слотов, retry-queue (включая `is_sos` флаг), AI-БД хелперы.

Запуск:

```bash
cd <repo>
python -m pytest relay/tests/ -v
```

Все 67 проходят. Используется in-memory SQLite через фикстуру `relay_with_db` в `conftest.py` — реального оборудования и сети не требуется.

В процессе написания тестов **обнаружен и исправлен реальный баг**: `ai_get_history` сортировала по `ts DESC LIMIT N` без тай-брейка, и при нескольких сообщениях в одну секунду (типичный случай — user сразу получил assistant-ответ) порядок становился неопределённым. На прод это бы означало, что LLM получал перемешанные роли в history и качество ответов падало. Фикс: `ORDER BY ts DESC, id DESC` (`id` autoincrement гарантирует порядок).

### Упакованный `Meshgram.exe` для Windows

Один файл, ~74 МБ, без необходимости ставить Python. Двойной клик → запускается GUI. Внутри:

- `gui.py` как entry-point, релей стартует через `QProcess` из GUI
- Все ассеты (50 SVG моделей нод, иконка) bundle'нуты внутрь
- Иконка приложения `relay/assets/icon.ico` (multi-size 16/24/32/48/64/128/256)
- `console=False` — чёрный терминал не мелькает при старте
- PyInstaller spec — `relay/Meshgram.spec`

Сборка локально:

```bash
cd relay
pip install pyinstaller
pyinstaller Meshgram.spec --clean
# готовый файл: relay/dist/Meshgram.exe
```

Готовый бинарник также доступен в [GitHub Releases](https://github.com/XYZ-WEB3/MESHGRAM/releases).

### System tray

GUI теперь умеет жить в системном трее:

- Иконка в трее показывается всегда пока приложение запущено
- Закрытие крестиком → сворачивает в трей (релей продолжает работать в фоне)
- Tray-меню: «Открыть» / «Старт релея» / «Стоп релея» / «Выйти»
- При первом сворачивании — уведомление «Meshgram свёрнут, релей продолжает работать в фоне»
- Полное закрытие — только через «Выйти» из tray-меню

Реализовано через `QSystemTrayIcon` + `QApplication.setQuitOnLastWindowClosed(False)`.

### Single-instance

`QSharedMemory` с уникальным ключом `Meshgram-Relay-SingleInstance-v1` — попытка запустить вторую копию показывает MessageBox «Meshgram уже запущен» и выходит. Это спасает от двух конкурирующих процессов, борющихся за один COM-порт ноды (что приводило к `Conflict: getUpdates already in progress` от Telegram и `serial.serialutil.SerialException` от ноды).

---

## v0.7 — AI-помощник через локальную LLM

С карманной ноды `@ai <вопрос>` — локальная модель (LM Studio / Ollama / любой OpenAI-совместимый endpoint) отвечает. Продолжение диалога — `@aiN <вопрос>`, история подтягивается в контекст модели. По умолчанию выключен; включается `AI_ENABLED=true` в `.env`.

### Использование

```
с pocket-ноды:    @ai как форматировать дату в Python
обратно:          @ai1 datetime.now().strftime("%Y-%m-%d")

с pocket-ноды:    @ai1 а если с миллисекундами?
обратно:          @ai1 datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
```

Ответы AI шлются обратно в pocket с префиксом `@aiN` — слот за слотом, как у обычных контактов. Длинные ответы автоматически чанкуются (см. v0.6 chunking).

### Настройки в `.env`

```env
AI_ENABLED=false                                # master-switch
AI_BASE_URL=http://localhost:1234/v1            # LM Studio default
AI_API_KEY=lm-studio                            # любой непустой для LM Studio
AI_MODEL=llama-3.2-8b-instruct                  # имя загруженной модели
AI_SYSTEM_PROMPT="Отвечай коротко и ясно. Максимум 2-3 предложения."
AI_TIMEOUT_SEC=30
AI_MAX_HISTORY=10                               # сколько последних пар user/assistant в контекст
AI_TTL_HOURS=168                                # 7 дней — потом slot освобождается
```

### Реализация

- **`relay/ai_helper.py`** — асинхронная обёртка над `openai>=1.0` (`AsyncOpenAI`). Ленивая инициализация: если пакет не установлен или endpoint недоступен — релей продолжает работать, ошибка пишется в лог, юзеру отвечает `@ai{N} ошибка: <тип>. Проверь LM Studio.`
- **БД**: новые таблицы `ai_conversations` (slot_n_ai PRIMARY KEY + created_at + last_used_at) и `ai_messages` (history с role/content/ts). Миграция из старой схемы — через `CREATE TABLE IF NOT EXISTS`.
- **Хелперы** в `relay.py`: `ai_alloc_slot`, `ai_touch_slot`, `ai_save_message`, `ai_get_history`, `ai_expire_old`, `ai_slot_exists`. Аналогично slot-helpers для обычных юзеров.
- **Парсер**: новые `_RE_AI_NEW` (`@ai <текст>`) и `_RE_AI_FOLLOWUP` (`@aiN <текст>`) проверяются ДО общего `@N` regex (иначе «@ai1» матчился бы как slot=ai1 и падал).
- **Диспатчер**: в `_handle_mesh_event` добавлены ветки `ai_new` и `ai_followup` → вызывают `_handle_ai(query, slot_n_ai=None|N)`.
- **Expiry**: `ai_expire_old(ttl_hours)` интегрирован в `expiry_worker` — раз в минуту удаляет неактивные диалоги старше TTL.

### Privacy

При работе с **локальным LM Studio** переписка не покидает устройство. Для облачных провайдеров (OpenAI, Anthropic, etc.) — поменяй `AI_BASE_URL` и `AI_API_KEY`, но помни что в этом случае ваша переписка отправляется в облако того провайдера.

---

## v0.6 — UX-фиксы и Linux-поддержка

### ⚡ SOS fast-retry для срочных сообщений

Раньше: ретрай-очередь с экспоненциальным backoff'ом (2 → 4 → 8 → 15 минут). Для обычной переписки норм, для срочного сообщения — катастрофа.

Теперь: если в тексте есть `#SOS`, `срочно`, `urgent` или `emergency` — короткие интервалы **5 → 15 → 30 → 60 → 120 секунд**. Срабатывает автоматически по детектору `_is_urgent(text)`.

Реализация:
- В `retry_queue` добавлен флаг `is_sos INTEGER NOT NULL DEFAULT 0` с миграцией для старых БД
- `retry_enqueue(..., is_sos=False)` — параметр флага
- `retry_worker` для `is_sos=True` использует таблицу `_RETRY_SOS_BACKOFF_SEC = (5, 15, 30, 60, 120)`
- Poll-интервал воркера снижен с 60 до 5 секунд (один SELECT в БД, нагрузка нулевая)
- Юзер видит другой статус: «срочное сообщение в очереди — повторяю каждые несколько секунд»

### 🚀 Speed / Reliability toggle

Новый ключ `MESH_DELIVERY_MODE` в `.env`:

```env
MESH_DELIVERY_MODE=reliable    # default — wantAck=True, ретраи, статусы
MESH_DELIVERY_MODE=fast        # fire-and-forget — wantAck=False, без ACK/retry
```

**`reliable`**: как сейчас — `wantAck=True`, есть «✓ Доставлено», retry если не дошло, тратится 1-3 сек на ACK-ожидание.

**`fast`**: fire-and-forget. Никаких подтверждений, никаких ретраев, мгновенная отправка. Для срочных коротких пакетов когда «лишь бы быстрее, а не наверняка». Поведение firmware идентично, просто без круга ACK.

Валидация в `settings.py:validate()` — пускает только два значения.

### ✂️ UTF-8 chunking для длинных сообщений

Раньше: при `len(text) > 170` юзер получал отлуп «Слишком длинно, сократи и отправь снова». Это плохой UX — в эпоху мессенджеров без лимитов люди не привыкли считать символы.

Теперь: если сообщение не влезает в один LoRa-пакет, оно разбивается на части `[@N user 14:32 1/3] начало... 2/3] середина... 3/3] конец`. Михаил на pocket-ноде видит части последовательно. Для юзера в TG — никаких ограничений, просто статус «📨 Длинное сообщение разбито на 3 части и отправлено».

Реализация:
- Новая утилита `_chunk_text(text, max_chars)` — режет по словам (по последнему пробелу в окне), не рубит слова посередине если возможно
- `_format_lora_packet(...)` принимает `chunk_idx, chunks_total` — добавляет `i/N` в префикс если нужно
- Multi-chunk шлётся через первый пакет (под ACK + retry-очередь) + остальные подряд best-effort с `asyncio.sleep(0.4)` между ними чтобы не перегружать LoRa-канал
- Если первый чанк упал → ретрай как обычно; остальные не пересылаются (юзер видит «не доставлено», шлёт ещё раз — заново разбивается)
- Если первый ушёл, а второй упал → лог-предупреждение, юзер видит «отправлено» (на pocket пришла только первая часть, но это редкий edge-case)

### 🐧 Linux-поддержка (run_relay.sh + run_gui.sh + systemd)

Раньше из коробки только `.bat`-лаунчеры — Linux-юзеры (а это большая часть mesh-комьюнити, кто на Raspberry Pi) пролетали.

Теперь:
- `relay/run_relay.sh` — bash-аналог `run_relay.bat`. Создаёт venv на первом запуске, ставит зависимости, листит `/dev/ttyUSB*` + `/dev/ttyACM*` + `/dev/serial/by-id/*`, спрашивает порт.
- `relay/run_gui.sh` — для GUI с проверкой `$DISPLAY` / `$WAYLAND_DISPLAY`. Если нет иксов — отказывается с подсказкой запустить CLI-вариант.
- `relay/deploy/meshgram-relay.service` — systemd template для production. С `User=meshgram`, `DeviceAllow=char-ttyUSB rw`, hardening (`NoNewPrivileges`, `ProtectSystem=full`).
- `relay/deploy/INSTALL_LINUX.md` — пошаговая инструкция для Ubuntu/Debian/Fedora/Arch. Два сценария: «запуск из консоли» (быстро потестить) и «systemd-сервис» (production на VPS / Pi).

### 💾 WAL mode на relay.db

Раньше `relay.db` был в дефолтном journal-режиме — конкурентные read/write блокировали друг друга. С тремя пишущими сторонами (relay.py main loop, retry_worker, GUI) это могло выстрелить «database is locked» при росте нагрузки.

Теперь в `db_init()` сразу после connect:

```python
_db.execute("PRAGMA journal_mode=WAL;")
_db.execute("PRAGMA synchronous=NORMAL;")
```

Аналогично тому что уже было на `site.db` сайта.

### 📖 README двуязычный (EN + RU)

`README.md` теперь главный, на английском (для мирового LoRa-комьюнити, которое 99% не читает по-русски). Сверху ссылка-переключатель `**Read in:** English · [Русский](README.ru.md)`. Перевод авторский, не машинный — соответствует тону оригинала.

`README.ru.md` — русская версия с тем же контентом и переключателем обратно. Оба упоминают новый Cloud-режим как planned.

Для бота `@MeshgramDemoBot` параллельно сделана инфраструктура i18n (см. `site/demo_bot/i18n.py`) — но это в репозитории не публикуется (отдельный приватный сервис).

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
