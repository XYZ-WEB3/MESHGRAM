**Read in:** English · [Русский](README.ru.md)

# Meshgram

A personal bridge between Telegram and a Meshtastic LoRa mesh. Reachable when you have no internet — as long as your pocket node holds a mesh signal.

[meshgram.site](https://meshgram.site) · [previous prototype (Nov 2025)](https://github.com/XYZ-WEB3/MESHGRAM/tree/old)

## Architecture

```
Telegram user → Telegram bot → home node (USB) ──LoRa DM──► pocket node
                                                                 ↓
                                                            read / reply
                                                                 ↓
Telegram user ← Telegram bot ← home node ──LoRa DM──◄ pocket node
```

Every Telegram conversation is assigned a short slot `@N`. A reply addressed to that slot goes back to the original sender — no shared chat, no broadcast. The two nodes communicate over an encrypted DM; other nodes on the channel only relay the packet.

## Capabilities

- **Sticky slots `@N`** — a single number stays with each contact across multiple messages. The pocket-node screen is therefore predictable.
- **Delivery statuses** comparable to any messenger: *sending → sent → delivered → reply*.
- **Auto-retry queue** — if the pocket is offline, outgoing messages are persisted in SQLite and re-sent later. Survives a process restart.
- **Categories and referral links** — `t.me/bot?start=work`, `?start=family`. The category prefix is shown next to the sender so context is obvious.
- **GPS via `/where`** (beta) — current coordinates available only to whitelisted contacts.
- **SOS** — `#SOS <text>` from the pocket node fans the message out to a configured recipient list, optionally with coordinates.
- **Whitelist mode** — closed bot, ban list, favorites.
- **PyQt6 desktop client** — settings, user list, active slots, live relay log, node-model picker covering 50 boards.
- **Long-message chunking** — input over the LoRa frame limit is split into `[1/N] … [N/N]` parts automatically.
- **Speed / reliability toggle** — `MESH_DELIVERY_MODE=fast` switches to fire-and-forget for short urgent messages, `reliable` (default) keeps ACKs and retries.
- **SOS fast-retry** — messages containing `#SOS`, `urgent` or equivalent are retried at 5/15/30/60/120 second intervals instead of the regular 2–15 minute back-off.
- **AI helper** (optional, off by default) — write `@ai <question>` from the pocket node and a local LLM responds. Continue the dialogue with `@aiN <question>`. Works against any OpenAI-compatible endpoint; the default config targets [LM Studio](https://lmstudio.ai/) on `localhost:1234`, so messages stay on-device. System prompt and TTL are configurable.

## Install

Requirements:

- Python 3.10 or newer
- Two Meshtastic-compatible LoRa nodes
- A Telegram bot from [@BotFather](https://t.me/BotFather) and your numeric Telegram ID from [@my_id_bot](https://t.me/my_id_bot)

```bash
git clone https://github.com/XYZ-WEB3/MESHGRAM.git
cd MESHGRAM
pip install -r requirements.txt
```

### Windows (GUI)

Double-click `relay\run_gui.bat`. On the first run, a wizard collects the bot token, your Telegram ID, the pocket-node ID and the COM port.

### Windows (CLI) / macOS / Linux

```bash
cp relay/.env.example relay/.env
# edit .env: BOT_TOKEN, OWNER_ID, POCKET_NODE_ID
cd relay
python relay.py --port COM3          # Windows
python relay.py --port /dev/ttyUSB0   # Linux / macOS
```

A bash launcher (`relay/run_relay.sh`) is provided as a convenience — it creates a `venv`, installs dependencies and lists serial devices. For a production deployment on Linux see [`relay/deploy/INSTALL_LINUX.md`](relay/deploy/INSTALL_LINUX.md), which includes a `systemd` unit template.

## Project status

### Shipped

- **Slot routing v1** — sticky `@N` slots replacing the earlier broadcast bridge
- **LoRa-side acknowledgements** — wantAck-based delivery statuses, retry queue with exponential back-off
- **GPS / `/where` (beta)**, SOS, whitelist, categories
- **PyQt6 desktop client** with a 50-model node picker
- **meshgram.site** landing page (Caddy + Let's Encrypt)
- **Latency batch** — TG → pocket reduced from 10–15 s to about 3 s (see [CHANGES.md](CHANGES.md))
- **Linux support** — `.sh` launchers, `systemd` unit, install guide
- **UTF-8 chunking** of long messages, speed/reliability toggle, fast-retry for urgent messages

### In progress

- **Cloud mode (MQTT / TCP)** — instead of running `relay.py` locally, the user keeps only a Wi-Fi node on the windowsill; the relay process runs on the project's VPS. Scaffold is in [`cloud/`](cloud/) and the MQTT broker is deployed; integration is paused pending a stable Meshtastic firmware release. Removes the need for a local PC and, in regions with restricted Telegram access, the need for a local VPN.

### Planned

- **Multi-user** — one process serving several bots through a single gateway node
- **Map in the GUI** — Leaflet/OSM view of the latest pocket-node GPS fix
- **In-GUI node controls** — LoRa transmit power, role, region, reboot
- **Self-hosted ROUTER coverage** — guide for setting up router-role nodes for city-scale reach
- **Distributable packages** — `.deb` for Debian/Ubuntu, AUR for Arch, PyInstaller bundle for Windows
- **Localisation** — English and Spanish translations of the site, bot and CLI

A more detailed roadmap and per-feature task list lives in [CHANGES.md](CHANGES.md). Architecture and command reference: [relay/README.md](relay/README.md).

## Stack

Python 3.10+, PyQt6, python-telegram-bot, meshtastic-python, SQLite (WAL), Caddy + Let's Encrypt for the website, optional Mosquitto for the cloud mode.

## Credits

- [Meshtastic](https://meshtastic.org/) — the open-source LoRa-mesh project this is built on
- Node-model SVGs in [`relay/devices/`](relay/devices) come from the [official Meshtastic documentation](https://meshtastic.org/docs/hardware/devices/)
- UI icons follow the Lucide / Feather visual language

Not affiliated with Meshtastic; uses only the public SDK and open assets.

## License

[MIT](LICENSE). A single-author hobby project; issues and pull requests are welcome but the code is provided as-is with no SLA.
