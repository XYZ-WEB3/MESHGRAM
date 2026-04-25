# Meshgram

Личный мост между Telegram и Meshtastic LoRa-сетью. Чтобы с тобой можно было связаться даже без интернета — лишь бы карманная LoRa-нода была в зоне приёма.

🌐 [meshgram.site](https://meshgram.site)
📂 Прежняя версия (ноябрь 2025): [github.com/XYZ-WEB3/MESHGRAM @ tag old](https://github.com/XYZ-WEB3/MESHGRAM)

## Как это работает

```
TG-юзер → Telegram-бот → home-нода (USB) ──LoRa DM──► карманная нода
                                                            ↓
                                                       ты читаешь, отвечаешь
                                                            ↓
TG-юзер ← Telegram-бот ← home-нода ──LoRa DM──◄ карманная нода
```

Каждое сообщение получает свой слот `@N`. Ответ на конкретный `@N` уходит конкретному человеку — никакого общего чата. Между двумя нодами идёт зашифрованный DM, чужие узлы на канале только ретранслируют пакет.

## Что умеет

- **Слоты `@N`** со sticky-логикой — переписка с одним человеком всегда на одном номере, повторные сообщения от него ложатся туда же
- **Статусы доставки** как в мессенджере: «передаю → отправлено → ✓ доставлено → ответ»
- **Авто-ретраи** при потере связи (очередь в SQLite, переживает рестарт)
- **Категории / реферальные ссылки** — `t.me/bot?start=work` для коллег, `?start=family` для семьи; у тебя в кармане видно «откуда» каждое сообщение
- **GPS / `/where`** — координаты для избранных пользователей (бета)
- **SOS** — триггер `#SOS` с карманной ноды → веерная рассылка списку получателей
- **Whitelist** — закрытый режим, бан-лист, избранные
- **GUI на PyQt6** — настройки, юзеры, активные слоты, лог релея, выбор модели ноды (50 SVG)

## Установка

Нужно:
- Python 3.10+
- Две Meshtastic-совместимые ноды
- Telegram-бот ([@BotFather](https://t.me/BotFather)) и свой numeric ID ([@my_id_bot](https://t.me/my_id_bot))

```bash
git clone https://github.com/XYZ-WEB3/MESHGRAM.git
cd MESHGRAM
pip install -r requirements.txt
```

### С GUI (Windows)

Двойной клик по `relay\run_gui.bat`. На первом запуске откроется wizard в три шага: токен → твой Telegram ID → ID карманной ноды → выбор COM-порта → Старт.

### Без GUI (любая ОС)

```bash
cp relay/.env.example relay/.env
# отредактируй .env: BOT_TOKEN, OWNER_ID, POCKET_NODE_ID
cd relay
python relay.py --port COM3        # Windows
python relay.py --port /dev/ttyUSB0 # Linux/macOS
```

Под Linux можно подвесить через systemd — пример unit-файла в [relay/README.md](relay/README.md#cli--headless).

## Дорожная карта

**Сделано**

- **ноябрь 2025** — первый прототип в этом же репо: простой мост Telegram ↔ Meshtastic broadcast, без адресности
- **зима 2025/26** — концептуальный пересмотр: уход от общего чата к адресной маршрутизации (слоты `@N`)
- **март 2026** — UI-прототип с дизайнером
- **апрель 2026** — текущая версия:
  - переписан под слоты `@N` со sticky-логикой
  - ACK по LoRa + retry queue в SQLite
  - GPS / `/where` (бета), SOS, whitelist, категории
  - PyQt6 GUI портирован по дизайнерскому референсу
  - каталог 50 моделей нод с SVG-превью
  - сайт meshgram.site (Caddy + Let's Encrypt)

**В планах**

- 🐧 Linux — `.sh` лаунчеры, тесты на Ubuntu/Debian/Fedora
- 📡 Wi-Fi/TCP подключение к ноде вместо USB
- 👥 Multi-user — одно приложение держит 5+ ботов с одной шлюзовой нодой
- 🤖 AI-помощник — авто-ответы / черновики / суммаризация через OpenAI-совместимый API (cloud или local через [LM Studio](https://lmstudio.ai/))
- 🗺 Карта в GUI для GPS-позиции
- ⚙️ Команды управления нодой (мощность LoRa, role, регион, рестарт) прямо из GUI
- 🌐 Свои ноды-ретрансляторы по городу с ролью ROUTER
- 🔁 Auto-restart при сетевых сбоях
- 📦 Установочные пакеты (deb / AUR)

Подробности по архитектуре, всем командам и конфигу — в [relay/README.md](relay/README.md).

## Стек

Python 3.10+ · PyQt6 · python-telegram-bot · meshtastic-python · SQLite · Caddy + Let's Encrypt (для сайта)

## Кредиты

- [Meshtastic](https://meshtastic.org/) — open-source LoRa-mesh, на котором всё работает
- SVG-картинки моделей нод в [`relay/devices/`](relay/devices) — взяты с [официальной документации Meshtastic](https://meshtastic.org/docs/hardware/devices/)
- Иконки UI нарисованы в стиле Lucide / Feather

Проект не аффилирован с Meshtastic, использует только публичный SDK и открытые иллюстрации с их сайта.

## Лицензия

[MIT](LICENSE). Сольный любительский проект, не для коммерции — issues и PR приветствуются, но без гарантий и SLA.
