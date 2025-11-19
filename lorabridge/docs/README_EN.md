# LoraBridge Messenger

## About
LoraBridge Messenger is a Python service that bridges remote Meshtastic nodes with Telegram even when no cellular network is available. A camper types messages through the LoRa mesh and the Telegram user replies without noticing the difference.

## Installation
1. Clone the repository and change into `lorabridge`.
2. Create a virtual environment `python -m venv .venv` and activate it.
3. Install dependencies with `pip install -r requirements.txt`.
4. (Optional) Enable pre-commit by running `pre-commit install`.

## Running
```bash
python -m src.main run
```
Use `python -m src.main status` for a quick health check and `python -m src.main flush` to purge queues.

## Configuration
- Core settings: `config/settings.json`.
- Secrets: `config/.env` (copy from `.env.example`).
- User storage and logs: `data/users.json` and `data/logs/`.

## Telegram account setup
1. Create a bot with [BotFather](https://t.me/BotFather).
2. Place the API token into `config/.env` under `TELEGRAM_TOKEN`.
3. Restart the service so the bot connects automatically.

## Meshtastic setup
1. Attach the device through USB and locate the serial port (e.g., `/dev/ttyUSB0`).
2. Update the port, baudrate, and throttle in `config/settings.json`.
3. When the bridge starts, the Meshtastic module opens the Serial API and exchanges packets.

## Supported commands
| Command | Description |
| --- | --- |
| `/ulist` | list active users |
| `/history #ID` | show dialog history |
| `/msg #ID text` | manually send a message |
| `/status` | link status |
| `/net` | Telegram status and errors |
| `/mesh` | Meshtastic parameters |
| `/flush` | purge queues |
| `/help` | show help |

## ID logic
- Every unique Telegram user automatically receives an ID `#1`, `#2`, ...
- IDs expire after 48 hours and can be reassigned.
- Records are stored in `data/users.json`; the history keeps the latest 50 events.

## Implemented today
- Bi-directional queues for Telegram ↔ Meshtastic.
- CLI for run/status/flush.
- ID issuance and persistence module.
- Command processor with basic handlers.
- Rotating log files.

## Roadmap
See `docs/wiki/future_plans.md` for the long-term backlog: media expansion, LoRa device control, GUI app, and more.

## Feature table
| Feature | Status |
| --- | --- |
| Telegram → LoRa text | ✔ Implemented |
| LoRa → Telegram text | ✔ Implemented |
| Message queue | ✔ Implemented |
| /ulist command | ✔ Implemented |
| Automatic ID assignment | ✔ Implemented |
| Photo recognition | ✖ Planned |
| Voice transcription | ✖ Planned |
| Video to description | ✖ Planned |
| LoRa control commands | ✖ Planned |
| GUI EXE app | ✖ Later |
