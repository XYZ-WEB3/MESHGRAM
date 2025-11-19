# LoraBridge Messenger

## About the project
LoraBridge Messenger is a Python service that builds a resilient bridge between Telegram and Meshtastic so remote users can exchange messages when traditional connectivity is unavailable. The system is split into dedicated modules that can restart independently without losing state.

## Installation
1. Install Python 3.11+ and git.
2. Clone this repository and change into the project directory.
3. Create a virtual environment and install dependencies from `requirements.txt`.
4. (Optional) Enable the bundled pre-commit hooks via `pre-commit install`.

## Running the service
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python src/main.py run --settings config/settings.json --verbose
```
The CLI bootstraps the queue, user mapping store, and mock Telegram/Meshtastic clients. Replace the mock clients with production adapters for the Serial API and Telegram Bot API when deploying in the field.

## Configuration
* `config/settings.json` keeps Telegram, Meshtastic, queue, and storage parameters.
* `config/.env` contains secrets (bot token, admin usernames). Use `config/.env.example` as a template.

## Connecting a Telegram account
1. Create a bot via @BotFather and place the token in `.env` (`TELEGRAM_BOT_TOKEN`).
2. List administrator usernames in `ADMIN_USERNAMES` (comma separated).
3. Ensure the bot accepts private messages.

## Connecting Meshtastic
1. Attach a Meshtastic node via USB and discover its serial port (`/dev/ttyUSB0`, `COM3`).
2. Configure the serial port and baudrate inside `config/settings.json`.
3. Make sure the device is on the expected channel and synchronized with the mesh network.

## Supported commands
Commands transmitted over LoRa (and eventually Telegram) are handled by `CommandHandler`:
- `/ulist` — list active users.
- `/status` — display queue status.
- `/flush` — clear the outbound queue.
- `/help` — print short command help.

## ID logic
* Every Telegram user automatically receives an ID such as `#1`, `#2`, ...
* `data/users.json` stores the mapping for the last 48 hours.
* When inactive, a record expires and the ID can be reused.
* LoRa packets must start with `#ID text` to ensure proper routing.

## What works today
- Modular architecture (Telegram, Meshtastic, queues, commands, ID management).
- Message queues with retry/FloodWait protection.
- CLI `run` command and `show-users` helper.
- Rotating log files.
- Dockerfile plus GitHub Actions CI scaffold.

## Planned work
See `docs/wiki/future_plans.md` for detailed roadmap items such as media transcription, translation, importance detection, and a GUI application.

## Feature table
| Feature | Status |
| --- | --- |
| Telegram text → LoRa | ✔ Implemented |
| LoRa text → Telegram | ✔ Implemented |
| Message queue | ✔ Implemented |
| /ulist command | ✔ Implemented |
| Automatic ID issuing | ✔ Implemented |
| Photo recognition | ✖ In progress |
| Voice transcription | ✖ In progress |
| Video → summary | ✖ In progress |
| LoRa device control | ✖ In progress |
| GUI EXE application | ✖ Planned |
