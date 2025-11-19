# Архитектура проекта

## Модульное разделение
- **Telegram Module (`src/lorabridge/telegram/`)** — отвечает за приём/отправку сообщений, выдаёт внутренние ID и сообщает пользователю о буферизации.
- **Meshtastic Module (`src/lorabridge/meshtastic/`)** — работает с Serial API, регулирует скорость отправки, разбирает пакеты формата `#ID текст` и команды `/status`.
- **Queue & Delivery (`src/lorabridge/queue/`)** — централизованные inbound/outbound очереди с повторными попытками и задержками.
- **User Mapping (`src/lorabridge/user_mapping/`)** — выдаёт и хранит ID последние 48 часов.
- **Command Module (`src/lorabridge/commands/`)** — реализует `/ulist`, `/status`, `/flush`, `/help` и расширяется по мере появления новых команд.
- **Utils (`src/lorabridge/utils/`)** — загрузка конфигурации, настройка логирования.

## Потоки данных
1. Telegram сообщение → TelegramClient → QueueManager (outbound) → MeshtasticClient → LoRa сеть.
2. LoRa пакет → MeshtasticClient → dispatcher → TelegramClient → Telegram пользователю.
3. Команды `/...` интерпретируются CommandHandler и сразу возвращают ответ в LoRa.

## Надёжность
- Очереди живут в памяти, но состояние пользователей хранится на диске (`data/users.json`).
- Retry-политика управляется `QueueSettings` (макс. попытки, задержка).
- Логи пишутся в `data/logs/lorabridge.log` с ротацией, что позволяет анализировать сбои на удалённых станциях.
