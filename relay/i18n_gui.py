"""
Минимальный i18n-словарь для GUI.

Поддержка RU (по умолчанию) и EN. Язык хранится в settings.gui_lang.
Меняется на первом запуске в wizard'е и через Settings dialog.

Перевод покрывает:
- OnboardingDialog (wizard первого запуска)
- System tray меню
- Главный toolbar и menu bar
- Базовые кнопки и статусы

Не покрывает (на потом отдельной сессией):
- SettingsDialog (большой, ~30 строк перевести)
- AboutDialog, UsersDialog, SlotsDialog
- Тексты ошибок и логов

Использование:
    from i18n_gui import t
    label.setText(t("wizard.title", lang))
"""
from __future__ import annotations

from typing import Dict


SUPPORTED = ("ru", "en")
DEFAULT_LANG = "ru"


def t(key: str, lang: str = DEFAULT_LANG) -> str:
    """Get translated string. Falls back to RU if missing in target lang.
    Falls back to the key itself if missing in RU too (developer mistake)."""
    lang = lang if lang in SUPPORTED else DEFAULT_LANG
    bucket = _STRINGS.get(lang) or _STRINGS[DEFAULT_LANG]
    if key in bucket:
        return bucket[key]
    return _STRINGS[DEFAULT_LANG].get(key, key)


# ────────────────────────────────────────────────────────────────────────
_STRINGS: Dict[str, Dict[str, str]] = {
    "ru": {
        # Wizard (OnboardingDialog)
        "wizard.title":      "Первый запуск — настройка",
        "wizard.welcome":    "Добро пожаловать в Meshgram Relay",
        "wizard.step_of":    "Шаг {n} из {total}",

        "wizard.step_lang.title":   "Язык / Language",
        "wizard.step_lang.hint":    "На каком языке показывать интерфейс? "
                                    "Можно потом сменить в настройках.",
        "wizard.step_lang.option_ru": "Русский",
        "wizard.step_lang.option_en": "English",

        "wizard.step_token.title": "1. Токен бота",
        "wizard.step_token.lede":  "Бот в Telegram, через который тебя будут писать другие люди.",
        "wizard.step_token.hint":  "Создай нового бота: открой @BotFather в Telegram, "
                                   "отправь /newbot, следуй подсказкам. В конце получишь "
                                   "строку формата 'NNNNN:XXXX...'. Скопируй её сюда.",

        "wizard.step_owner.title": "2. Твой Telegram ID",
        "wizard.step_owner.lede":  "Чтобы бот узнавал тебя как админа.",
        "wizard.step_owner.hint":  "Открой в Telegram бота @my_id_bot и нажми /start. "
                                   "Он ответит твоим numeric ID — большое число. "
                                   "Скопируй и вставь сюда.",

        "wizard.step_pocket.title": "3. ID карманной ноды",
        "wizard.step_pocket.lede":  "Meshtastic-устройство, которое будешь носить с собой.",
        "wizard.step_pocket.hint":  "Подключи карманную ноду к Meshtastic-приложению "
                                    "или к веб-клиенту (client.meshtastic.org). "
                                    "В списке узлов её ID показан как !xxxxxxxx — "
                                    "8 hex-символов с восклицательным знаком. Скопируй сюда.",

        "wizard.btn_skip":   "Сделаю позже",
        "wizard.btn_back":   "Назад",
        "wizard.btn_next":   "Дальше",
        "wizard.btn_done":   "Готово",

        "wizard.warn_token":  "Вставь токен от @BotFather.",
        "wizard.warn_owner":  "Вставь свой numeric ID от @my_id_bot.",
        "wizard.warn_pocket": "ID карманной ноды должен быть формата !xxxxxxxx (8 hex-знаков).",
        "wizard.warn_save":   "Ошибка записи",
        "wizard.warn_validation": "Не сохранено",
        "wizard.warn_need":   "Нужно",

        # Tray
        "tray.tooltip":      "Meshgram Relay",
        "tray.open":         "Открыть",
        "tray.start":        "Старт релея",
        "tray.stop":         "Стоп релея",
        "tray.quit":         "Выйти",
        "tray.minimize_title": "Meshgram свёрнут",
        "tray.minimize_text":  "Релей продолжает работать в фоне. "
                               "Полное закрытие — через меню в трее.",

        # Main window — toolbar / menu / status
        "main.title":        "Meshgram Relay",
        "main.menu_file":    "Файл",
        "main.menu_settings": "Настройки",
        "main.menu_help":    "Справка",
        "main.act_settings": "Настройки…",
        "main.act_users":    "Пользователи…",
        "main.act_slots":    "Активные слоты",
        "main.act_about":    "О программе",
        "main.act_quit":     "Выйти",
        "main.btn_start":    "Старт",
        "main.btn_stop":     "Стоп",
        "main.btn_pause":    "Пауза",
        "main.btn_resume":   "Возобновить",
        "main.lbl_port":     "Порт",
        "main.lbl_status":   "Статус",
        "main.status_idle":  "Не запущен",
        "main.status_running": "Работает",
        "main.status_paused":  "Приостановлен",

        # Single-instance
        "single.title":      "Meshgram уже запущен",
        "single.text":       "Meshgram Relay уже работает (см. иконку в системном трее).\n"
                             "Если это ошибка — закрой все процессы Meshgram в диспетчере "
                             "задач и запусти заново.",

        # Confirm-on-quit
        "quit.relay_running.title": "Релей работает",
        "quit.relay_running.text":  "Релей ещё запущен. Остановить и выйти?",
    },

    "en": {
        # Wizard
        "wizard.title":      "First run — setup",
        "wizard.welcome":    "Welcome to Meshgram Relay",
        "wizard.step_of":    "Step {n} of {total}",

        "wizard.step_lang.title":   "Язык / Language",
        "wizard.step_lang.hint":    "Pick the interface language. "
                                    "You can change it later in Settings.",
        "wizard.step_lang.option_ru": "Русский",
        "wizard.step_lang.option_en": "English",

        "wizard.step_token.title": "1. Bot token",
        "wizard.step_token.lede":  "The Telegram bot that other people will message you through.",
        "wizard.step_token.hint":  "Create a new bot: open @BotFather in Telegram, "
                                   "send /newbot, follow the prompts. You'll receive a "
                                   "string like 'NNNNN:XXXX...'. Paste it here.",

        "wizard.step_owner.title": "2. Your Telegram ID",
        "wizard.step_owner.lede":  "So the bot recognises you as the admin.",
        "wizard.step_owner.hint":  "Open @my_id_bot in Telegram and tap /start. "
                                   "It will reply with your numeric ID — a large number. "
                                   "Copy and paste it here.",

        "wizard.step_pocket.title": "3. Pocket node ID",
        "wizard.step_pocket.lede":  "The Meshtastic device you'll carry with you.",
        "wizard.step_pocket.hint":  "Connect your pocket node to the Meshtastic app or the web "
                                    "client (client.meshtastic.org). Its ID appears in the "
                                    "node list as !xxxxxxxx — 8 hex characters prefixed with "
                                    "an exclamation mark. Paste it here.",

        "wizard.btn_skip":   "Later",
        "wizard.btn_back":   "Back",
        "wizard.btn_next":   "Next",
        "wizard.btn_done":   "Done",

        "wizard.warn_token":  "Paste the token from @BotFather.",
        "wizard.warn_owner":  "Paste your numeric ID from @my_id_bot.",
        "wizard.warn_pocket": "Pocket node ID must be in the form !xxxxxxxx (8 hex chars).",
        "wizard.warn_save":   "Save failed",
        "wizard.warn_validation": "Not saved",
        "wizard.warn_need":   "Required",

        # Tray
        "tray.tooltip":      "Meshgram Relay",
        "tray.open":         "Open",
        "tray.start":        "Start relay",
        "tray.stop":         "Stop relay",
        "tray.quit":         "Quit",
        "tray.minimize_title": "Meshgram minimised",
        "tray.minimize_text":  "Relay keeps running in the background. "
                               "Use the tray menu to fully exit.",

        # Main window
        "main.title":        "Meshgram Relay",
        "main.menu_file":    "File",
        "main.menu_settings": "Settings",
        "main.menu_help":    "Help",
        "main.act_settings": "Settings…",
        "main.act_users":    "Users…",
        "main.act_slots":    "Active slots",
        "main.act_about":    "About",
        "main.act_quit":     "Quit",
        "main.btn_start":    "Start",
        "main.btn_stop":     "Stop",
        "main.btn_pause":    "Pause",
        "main.btn_resume":   "Resume",
        "main.lbl_port":     "Port",
        "main.lbl_status":   "Status",
        "main.status_idle":  "Idle",
        "main.status_running": "Running",
        "main.status_paused":  "Paused",

        # Single-instance
        "single.title":      "Meshgram is already running",
        "single.text":       "Meshgram Relay is already running (see the system tray icon).\n"
                             "If this is a mistake — kill all Meshgram processes in Task "
                             "Manager and start again.",

        # Confirm-on-quit
        "quit.relay_running.title": "Relay is running",
        "quit.relay_running.text":  "The relay is still active. Stop it and quit?",
    },
}
