# Meshgram on Linux — quickstart

Тестировано на Ubuntu 22.04 LTS / Debian 12 / Arch (rolling). Под другие
дистрибутивы — суть та же, отличается только пакетный менеджер и группа
для доступа к serial-устройству (`dialout` в Debian-семействе, `uucp` в Arch).

---

## Вариант A — запуск из консоли (без systemd)

Просто запускаешь `run_relay.sh` от своего юзера. Подходит для разовых
тестов или если у тебя ноут с GUI.

```bash
# 1. Клонировать репо и установить системные пакеты
git clone https://github.com/XYZ-WEB3/MESHGRAM.git
cd MESHGRAM
sudo apt install -y python3 python3-venv python3-pip          # Ubuntu/Debian
# или: sudo dnf install -y python3 python3-pip               # Fedora
# или: sudo pacman -S --needed python python-pip             # Arch

# 2. Доступ к /dev/ttyUSB* для своего юзера (раз и навсегда)
sudo usermod -a -G dialout "$USER"   # Ubuntu/Debian
# или: sudo usermod -a -G uucp "$USER"   # Arch
# затем перелогиниться (или `newgrp dialout` в текущем шелле)

# 3. Сконфигурировать
cd relay
cp .env.example .env
nano .env           # заполнить BOT_TOKEN, OWNER_ID, POCKET_NODE_ID

# 4. Запустить
chmod +x run_relay.sh
./run_relay.sh      # на первом запуске создаст venv, поставит зависимости
```

## Вариант Б — systemd-сервис (production)

Подходит для VPS / Raspberry Pi / любого always-on хоста.

```bash
# 1. Системные пакеты
sudo apt install -y python3 python3-venv python3-pip git

# 2. Создать юзера
sudo useradd --system --home /opt/meshgram --shell /bin/false meshgram
sudo usermod -a -G dialout meshgram   # или uucp на Arch

# 3. Установить код
sudo mkdir -p /opt/meshgram
sudo chown meshgram:meshgram /opt/meshgram
sudo -u meshgram git clone https://github.com/XYZ-WEB3/MESHGRAM.git /opt/meshgram

# 4. venv + зависимости
sudo -u meshgram bash -lc '
    cd /opt/meshgram/relay
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -r ../requirements.txt
'

# 5. .env
sudo -u meshgram cp /opt/meshgram/relay/.env.example /opt/meshgram/relay/.env
sudo -u meshgram nano /opt/meshgram/relay/.env
sudo chmod 600 /opt/meshgram/relay/.env

# 6. systemd unit
sudo cp /opt/meshgram/relay/deploy/meshgram-relay.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now meshgram-relay
sudo systemctl status meshgram-relay

# 7. Логи
sudo journalctl -u meshgram-relay -f
```

## GUI (опционально)

PyQt6-GUI запускается через `./run_gui.sh` — нужны X11 или Wayland.
Через SSH работает с `ssh -X user@host` (X11-forwarding).

## Troubleshooting

**Permission denied на /dev/ttyUSB0** — юзер не в группе dialout/uucp,
надо перелогиниться после `usermod -a -G ...`.

**`ModuleNotFoundError`** — venv не активирован. Скрипт сам всё ставит,
но если запускаешь руками — `source .venv/bin/activate`.

**LoRa-нода не находится** — проверь `dmesg | tail` после подключения USB,
там должно быть `cdc_acm` или `ch341 ttyUSB0 attached`. Если нет —
драйвер не подхватился (старое ядро / не та версия чипа).

**Bot does nothing on Telegram** — `journalctl -u meshgram-relay` покажет
конкретную ошибку. Самые частые: неверный `BOT_TOKEN` или нет интернета.

**ROUTER-режим / mesh-релей** — для расширения покрытия по городу через
твою ноду в роли ретранслятора см. `docs/RELAY_NETWORK.md` (TBD в roadmap).
