# Архитектура LoraBridge

```
Telegram Bot <-> Telegram Module <-> Queue & Delivery <-> Meshtastic Module <-> Meshtastic Device
                                ^                     |
                                |                     v
                            User Mapping --------> Command Module
```

## Telegram Module
- Использует Telegram Bot API для чтения/отправки сообщений.
- Преобразует медиаконтент в текстовые описания (позже).
- Назначает внутренние ID при первом сообщении.
- Передаёт текст в очередь Outbox.

## Meshtastic Module
- Работает через Serial API и читает LoRa-пакеты.
- Принимает строки вида `#ID текст` и парсит их в структуру.
- Отправляет сообщения из Outbox с учётом троттлинга.

## Queue & Delivery
- Две очереди: `outbound` (Telegram → LoRa) и `inbound` (LoRa → Telegram).
- Delivery Manager отслеживает retry, FloodWait и паузы.
- Повторно ставит сообщения в очередь при сбое, пока не достигнут лимит.

## User Mapping Module
- Хранит `TelegramUser ↔ #ID` + историю последних 48 часов.
- Обновляет JSON/SQLite хранилище и отдает список активных пользователей.

## Command Module
- Регистрирует обработчики `/ulist`, `/history`, `/msg`, `/status`, `/net`, `/mesh`, `/flush`, `/help`.
- Отдельный рантайм обрабатывает команды, пришедшие из LoRa.

## Дополнительно
- Utils содержит конфигурацию, логирование, хранилище.
- CLI (`src/main.py`) управляет запуском сервисов и служит точкой входа для EXE/CLI.
