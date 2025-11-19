# LoraBridge Messenger

LoraBridge Messenger связывает Meshtastic-узлы с Telegram: пользователь на LoRa-сетке выбирает COM-порт своего радиомодуля,
а оператор в Telegram ведёт диалог через бота. В репозитории уже есть всё, что нужно, чтобы настроить мост, запустить его в виде
CLI-приложения и собрать самостоятельный `.exe`.

## Структура репозитория

| Путь | Назначение |
| --- | --- |
| `lorabridge/src/` | Исходный код мостовых компонентов (Telegram, Meshtastic, очереди, выдача ID). |
| `lorabridge/config/` | Настройки и `.env` с токеном бота. |
| `lorabridge/data/` | Пользовательские базы (`users.json`) и логи выполнения. |
| `lorabridge/docs/` | Подробное описание архитектуры и сценариев. |
| `lorabridge/tests/` | Юнит‑тесты для очередей и менеджера пользователей. |

> Подробная документация и схемы приведены в `lorabridge/docs/README_RU.md` и `lorabridge/docs/wiki/*`.

## Подготовка окружения

1. Установите Python 3.11+ и Git.
2. Клонируйте проект и перейдите в рабочую папку:
   ```bash
   git clone <repo-url>
   cd MESHGRAM/lorabridge
   ```
3. Создайте и активируйте виртуальное окружение, затем поставьте зависимости:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

## Настройка секретов и параметров

1. Скопируйте пример `.env` и вставьте токен Telegram-бота:
   ```bash
   cp config/.env.example config/.env
   echo "TELEGRAM_TOKEN=123456789:ABCDEF" >> config/.env
   ```
   Переменная `TELEGRAM_TOKEN` обязательна — без неё загрузчик настроек остановит приложение.
2. Отредактируйте `config/settings.json`:
   - `telegram.floodwait_threshold` — лимит, после которого очередь ставится на паузу.
   - `meshtastic.serial_port` — выберите COM-порт Meshtastic (например, `COM3` в Windows или `/dev/ttyUSB0` в Linux).
   - `meshtastic.baudrate` и `meshtastic.throttle_interval` регулируют скорость обмена и интервал дросселирования.
   - `queue_retry_interval` и `history_hours` отвечают за стратегию повторов и срок жизни ID.

Файлы `data/users.json` и `data/logs/*` создаются автоматически при первом запуске и сохраняют историю ID/сообщений.

## Как подключить Telegram и Meshtastic

### Telegram
1. Создайте бота в [@BotFather](https://t.me/BotFather) и скопируйте токен в `config/.env` (`TELEGRAM_TOKEN`).
2. Перезапустите мост — модуль `TelegramClient` возьмёт токен из `.env`, авторизует бота и начнёт обрабатывать команды `/status`,
   `/ulist`, `/history`, `/msg`, `/flush` и другие, перечисленные в `lorabridge/docs/README_RU.md`.

### Meshtastic
1. Подключите Meshtastic-устройство по USB и определите его порт (`COMx` или `/dev/ttyUSBx`).
2. Укажите порт и требуемую скорость в `config/settings.json`.
3. При запуске `MeshtasticClient` автоматически откроет Serial API и синхронизирует очередь сообщений.

## Запуск из исходников

Основные команды CLI находятся в `src/main.py`:

```bash
python -m src.main run     # запустить мост и обработчики
python -m src.main status  # проверить текущие параметры
python -m src.main flush   # вручную очистить очереди
```

Логи пишутся в `data/logs`, а рабочая база пользователей хранится в `data/users.json`.

## Сборка standalone .exe

1. Установите PyInstaller внутри виртуального окружения: `pip install pyinstaller`.
2. Выполните сборку из каталога `lorabridge`:
   ```bash
   pyinstaller \
     --onefile \
     --name LoraBridge \
     --paths src \
     --add-data "config;config" \
     --add-data "data;data" \
     src/main.py
   ```
   Ключ `--paths src` сообщает PyInstaller, где искать пакет `src`, а `--add-data` добавляет в сборку настройки и шаблоны данных.
3. В каталоге `dist/` появится `LoraBridge.exe`. При запуске пользователь сможет выбрать COM-порт (через `config/settings.json` в
   соседней папке) и авторизоваться в Telegram, как и при работе из исходников.

Перед передачей `.exe` не забудьте положить рядом папку `config` с настроенным `.env` и `settings.json`, чтобы конечный пользователь
смог подставить свой токен и параметры Meshtastic.

## Дополнительные материалы
- `lorabridge/docs/wiki/architecture.md` — обзор модулей и потоков данных.
- `lorabridge/docs/wiki/delivery_logic.md` — схема работы очередей.
- `lorabridge/docs/wiki/future_plans.md` — список ближайших задач (GUI, расширение медиа и т.д.).
