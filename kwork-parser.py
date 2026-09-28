import time
import requests
import os
import getpass
import subprocess
import html
import json
import re
import fcntl
from datetime import datetime, timedelta

KEYCHAIN_ACCOUNT = "kwork-parser"

def get_keychain_value(service, prompt):
    """Reads a value from macOS Keychain, prompting and saving it if missing."""
    result = subprocess.run(
        ["security", "find-generic-password", "-a", KEYCHAIN_ACCOUNT, "-s", service, "-w"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    if result.returncode != 44:
        raise RuntimeError(f"Не удалось прочитать {prompt} из Keychain: {result.stderr.strip()}")

    value = getpass.getpass(f"Введите {prompt}: ").strip()
    if not value:
        raise ValueError(f"Значение «{prompt}» не может быть пустым.")

    subprocess.run(
        ["security", "add-generic-password", "-U", "-a", KEYCHAIN_ACCOUNT, "-s", service, "-w", value],
        check=True,
        capture_output=True,
        text=True,
    )
    return value

# URL страницы проектов Kwork; можно указать ссылку с фильтрами.
PROJECTS_URL = "https://kwork.ru/projects"

# Файл базы данных для хранения ID уже отправленных проектов
SEEN_TASKS_FILE = "seen_tasks.txt"
SUBSCRIBERS_FILE = "subscribers.json"
PROJECT_CHECK_INTERVAL = 900
UPDATE_POLL_TIMEOUT = 20
PROJECT_PAGES_TO_SCAN = 7
PAGE_REQUEST_DELAY = 0.25
HISTORY_DAYS = 7
DEFAULT_TITLE_KEYWORDS = (
    "webflow",
    "вебфлоу",
    "framer",
    "фреймер",
    "tilda",
    "тильда",
    "презентац",
    "pitch deck",
    "pitchdeck",
    "слайд",
    "powerpoint",
    "power point",
    "pptx",
    "google slides",
    "инфограф",
    "infographic",
    "отчет",
    "report",
    "дашборд",
    "dashboard",
    "визуализация данных",
    "data visualization",
)
# -----------------

def get_seen_tasks():
    """Загружает список уже просмотренных ссылок из файла."""
    if not os.path.exists(SEEN_TASKS_FILE):
        return set()
    with open(SEEN_TASKS_FILE, "r", encoding="utf-8") as file:
        return set(line.strip() for line in file.readlines())

def save_seen_task(task_url):
    """Сохраняет новую ссылку в файл."""
    with open(SEEN_TASKS_FILE, "a", encoding="utf-8") as file:
        file.write(f"{task_url}\n")

def matches_project_title(title):
    return matches_keywords(title, DEFAULT_TITLE_KEYWORDS)

def normalize_text(value):
    return html.unescape(str(value)).casefold().replace("ё", "е").strip()

def matches_keywords(title, keywords):
    normalized_title = normalize_text(title)
    return any(normalize_text(keyword) in normalized_title for keyword in keywords if keyword)

def parse_filter_keywords(text):
    keywords = []
    seen = set()
    for keyword in re.split(r"[,;\n]+", text):
        keyword = keyword.strip()
        normalized = normalize_text(keyword)
        if normalized and normalized not in seen:
            keywords.append(keyword)
            seen.add(normalized)
    return keywords

def get_subscribers():
    if not os.path.exists(SUBSCRIBERS_FILE):
        return {}
    try:
        with open(SUBSCRIBERS_FILE, "r", encoding="utf-8") as file:
            subscribers = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        print(f"Не удалось прочитать список подписчиков: {error}")
        return {}
    return subscribers if isinstance(subscribers, dict) else {}

def save_subscribers(subscribers):
    with open(SUBSCRIBERS_FILE, "w", encoding="utf-8") as file:
        json.dump(subscribers, file, ensure_ascii=False, indent=2)
    os.chmod(SUBSCRIBERS_FILE, 0o600)

def get_project_page(page_number):
    """Loads one page of Kwork projects and its pagination metadata."""
    try:
        response = requests.get(PROJECTS_URL, params={"page": page_number}, timeout=20)
        response.raise_for_status()
    except requests.RequestException as error:
        print(f"Ошибка загрузки страницы Kwork: {error}")
        return None

    state_match = re.search(r"window\.stateData\s*=\s*", response.text)
    if not state_match:
        print("Kwork не вернул данные проектов. Возможно, изменилась страница или сработала защита.")
        return None

    try:
        state, _ = json.JSONDecoder().raw_decode(response.text, state_match.end())
    except json.JSONDecodeError as error:
        print(f"Не удалось разобрать данные страницы Kwork: {error}")
        return None

    pagination = state.get("wantsListData", {}).get("pagination", {})
    projects = pagination.get("data", [])
    if not isinstance(projects, list):
        print("Формат списка проектов Kwork изменился.")
        return None
    return projects, pagination.get("last_page", 1)

def get_latest_projects(page_limit=PROJECT_PAGES_TO_SCAN):
    dated_projects = []
    seen_ids = set()
    cutoff = datetime.now() - timedelta(days=HISTORY_DAYS)
    for page_number in range(1, page_limit + 1):
        if page_number > 1:
            time.sleep(PAGE_REQUEST_DELAY)
        page_result = get_project_page(page_number)
        if page_result is None:
            return None
        projects, _ = page_result
        for project in projects:
            project_id = project.get("id")
            if not project_id or str(project_id) in seen_ids:
                continue
            seen_ids.add(str(project_id))
            try:
                created_at = datetime.fromisoformat(project.get("date_create", ""))
            except (TypeError, ValueError):
                continue
            if created_at < cutoff or created_at > datetime.now():
                continue
            project["_created_at"] = created_at
            dated_projects.append(project)

    dated_projects.sort(key=lambda project: project["_created_at"], reverse=True)
    return dated_projects

def format_project_message(project):
    project_id = project.get("id")
    task_url = f"https://kwork.ru/projects/{project_id}/view"
    title = html.escape(html.unescape(str(project.get("name") or f"Проект #{project_id}")))
    description = html.escape(html.unescape(str(project.get("description") or "Описание отсутствует")))
    if len(description) > 300:
        description = description[:300] + "..."
    return (
        f"🟢 <b>{title}</b>\n\n"
        f"📝 <i>{description}</i>\n\n"
        f"🔗 <a href='{task_url}'>Открыть задачу</a>"
    )

def search_latest_for_user(chat_id, telegram_token, subscribers):
    projects = get_latest_projects()
    if projects is None:
        send_telegram_message("Не удалось загрузить проекты Kwork. Попробуйте позже.", telegram_token, chat_id)
        return

    subscriber = subscribers[chat_id]
    keywords = subscriber.get("keywords") or list(DEFAULT_TITLE_KEYWORDS)
    matches = [project for project in projects if matches_keywords(project.get("name", ""), keywords)]
    if not matches:
        send_telegram_message(
            f"За последние {HISTORY_DAYS} дней на первых {PROJECT_PAGES_TO_SCAN} страницах совпадений нет.",
            telegram_token,
            chat_id,
        )
        return

    send_telegram_message(
        f"За последние {HISTORY_DAYS} дней на первых {PROJECT_PAGES_TO_SCAN} страницах найдено совпадений: {len(matches)}.",
        telegram_token,
        chat_id,
    )
    sent_projects = set(subscriber.get("sent_projects", []))
    for project in matches:
        if send_telegram_message(format_project_message(project), telegram_token, chat_id):
            sent_projects.add(str(project.get("id")))
        time.sleep(1)
    subscriber["sent_projects"] = sorted(sent_projects)
    save_subscribers(subscribers)

def send_telegram_message(text, telegram_token, chat_id):
    """Отправляет сообщение в Telegram."""
    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True # Отключает предпросмотр ссылок для компактности
    }
    try:
        response = requests.post(url, data=payload, timeout=15)
        result = response.json()
        if not response.ok or not result.get("ok"):
            print(f"Ошибка Telegram API: {result.get('description', response.text)}")
            return False
        return True
    except requests.RequestException as error:
        print(f"Ошибка соединения с Telegram API: {type(error).__name__}")
        return False
    except ValueError:
        print("Telegram API вернул некорректный ответ.")
        return False

def process_bot_update(update, telegram_token):
    message = update.get("message", {})
    chat = message.get("chat", {})
    if chat.get("type") != "private":
        return

    text = message.get("text", "").strip()
    if not text.startswith("/"):
        return
    command_parts = text.split(maxsplit=1)
    command = command_parts[0].split("@", 1)[0].lower()
    argument = command_parts[1].strip() if len(command_parts) > 1 else ""
    chat_id = str(chat.get("id", ""))
    if not chat_id:
        return

    subscribers = get_subscribers()
    is_registered = chat_id in subscribers

    if command == "/start":
        subscriber = subscribers.get(chat_id, {})
        subscriber.setdefault("keywords", list(DEFAULT_TITLE_KEYWORDS))
        subscriber.setdefault("sent_projects", [])
        subscriber["active"] = True
        subscribers[chat_id] = subscriber
        save_subscribers(subscribers)
        reply = "Вы зарегистрированы, уведомления о новых проектах включены. Это тестовое сообщение: бот может писать вам.\n\nКоманды: /help"
    elif command == "/help":
        reply = (
            "Команды бота:\n"
            "/start - регистрация и включение уведомлений\n"
            "/guide - инструкция по фильтрам\n"
            "/filter ключ1, ключ2 - задать темы поиска\n"
            "/reset_filter - вернуть стандартные ключи\n"
            "/status - статус подписки\n"
            "/stop - приостановить уведомления\n"
            "/resume - снова включить уведомления\n"
            "/help - показать эту справку"
        )
    elif command == "/guide":
        reply = (
            "Инструкция по фильтрам Kwork\n\n"
            "Отправьте /filter, затем ключевые слова через запятую. Например:\n"
            "/filter webflow, framer, презентация, инфографика\n\n"
            "Бот ищет совпадения в названиях проектов за последние 7 дней, "
            "просматривая первые 7 страниц Kwork. Поиск запускается сразу после команды, "
            "затем бот проверяет новые проекты каждые 15 минут.\n\n"
            "/reset_filter - вернуть стандартный набор тем\n"
            "/status - посмотреть текущие темы\n"
            "/stop и /resume - выключить и включить уведомления"
        )
    elif command == "/filter":
        if not is_registered:
            reply = "Сначала зарегистрируйтесь командой /start."
        else:
            keywords = parse_filter_keywords(argument)
            if not keywords:
                reply = "Укажите ключи через запятую. Пример: /filter webflow, framer, презентация"
            elif len(keywords) > 20 or any(len(keyword) > 60 for keyword in keywords):
                reply = "Можно указать не более 20 ключей, длина каждого - до 60 символов."
            else:
                subscribers[chat_id]["keywords"] = keywords
                subscribers[chat_id]["sent_projects"] = []
                save_subscribers(subscribers)
                send_telegram_message(
                    "Фильтр сохранён: " + ", ".join(keywords) + ". Ищу совпадения за 7 дней...",
                    telegram_token,
                    chat_id,
                )
                search_latest_for_user(chat_id, telegram_token, subscribers)
                return
    elif command == "/reset_filter":
        if not is_registered:
            reply = "Сначала зарегистрируйтесь командой /start."
        else:
            subscribers[chat_id]["keywords"] = list(DEFAULT_TITLE_KEYWORDS)
            subscribers[chat_id]["sent_projects"] = []
            save_subscribers(subscribers)
            send_telegram_message(
                "Фильтр сброшен к стандартным темам. Ищу совпадения за 7 дней...",
                telegram_token,
                chat_id,
            )
            search_latest_for_user(chat_id, telegram_token, subscribers)
            return
    elif command == "/status":
        if not is_registered:
            reply = "Вы ещё не зарегистрированы. Отправьте /start."
        elif subscribers[chat_id].get("active", True):
            keywords = subscribers[chat_id].get("keywords") or list(DEFAULT_TITLE_KEYWORDS)
            reply = "Вы зарегистрированы, уведомления включены. Фильтр: " + ", ".join(keywords)
        else:
            reply = "Вы зарегистрированы, уведомления приостановлены. Отправьте /resume, чтобы включить их."
    elif command == "/stop":
        if not is_registered:
            reply = "Вы ещё не зарегистрированы. Отправьте /start."
        else:
            subscribers[chat_id]["active"] = False
            save_subscribers(subscribers)
            reply = "Уведомления приостановлены. Чтобы снова получать проекты, отправьте /resume."
    elif command in ("/resume", "/subscribe"):
        if not is_registered:
            reply = "Вы ещё не зарегистрированы. Отправьте /start."
        else:
            subscribers[chat_id]["active"] = True
            save_subscribers(subscribers)
            reply = "Уведомления включены."
    elif command == "/unsubscribe":
        if not is_registered:
            reply = "Вы ещё не зарегистрированы. Отправьте /start."
        else:
            subscribers[chat_id]["active"] = False
            save_subscribers(subscribers)
            reply = "Уведомления отключены. Чтобы снова получать проекты, отправьте /resume."
    else:
        reply = "Не знаю такую команду. Список команд: /help"

    send_telegram_message(reply, telegram_token, chat_id)

def register_bot_commands(telegram_token):
    commands = [
        {"command": "start", "description": "Зарегистрироваться и включить уведомления"},
        {"command": "help", "description": "Показать команды"},
        {"command": "guide", "description": "Инструкция по фильтрам"},
        {"command": "filter", "description": "Задать ключевые слова"},
        {"command": "reset_filter", "description": "Сбросить фильтр"},
        {"command": "status", "description": "Проверить подписку"},
        {"command": "stop", "description": "Приостановить уведомления"},
        {"command": "resume", "description": "Возобновить уведомления"},
    ]
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{telegram_token}/setMyCommands",
            json={"commands": commands},
            timeout=15,
        )
        result = response.json()
        if not response.ok or not result.get("ok"):
            print(f"Не удалось обновить меню команд: {result.get('description', response.text)}")
    except requests.RequestException as error:
        print(f"Не удалось обновить меню команд: {type(error).__name__}")

def get_bot_updates(telegram_token, offset):
    params = {
        "timeout": UPDATE_POLL_TIMEOUT,
        "allowed_updates": json.dumps(["message"]),
    }
    if offset is not None:
        params["offset"] = offset
    try:
        response = requests.get(
            f"https://api.telegram.org/bot{telegram_token}/getUpdates",
            params=params,
            timeout=UPDATE_POLL_TIMEOUT + 10,
        )
        result = response.json()
        if not response.ok or not result.get("ok"):
            print(f"Ошибка получения команд Telegram: {result.get('description', response.text)}")
            return None
        return result.get("result", [])
    except (requests.RequestException, ValueError) as error:
        print(f"Ошибка получения команд Telegram: {type(error).__name__}")
        return None

def check_new_tasks(telegram_token):
    """Checks Kwork projects and sends new ones."""
    print(f"[{time.strftime('%H:%M:%S')}] Проверка проектов Kwork...")
    subscribers = get_subscribers()
    active_subscribers = [
        (chat_id, user)
        for chat_id, user in subscribers.items()
        if user.get("active", True)
    ]
    if not active_subscribers:
        print("Нет активных подписчиков. Откройте бота в Telegram и отправьте /start.")
        return

    projects = get_latest_projects()
    if projects is None:
        print("Не удалось получить проекты Kwork.")
        return

    changed = False
    for chat_id, subscriber in active_subscribers:
        keywords = subscriber.get("keywords") or list(DEFAULT_TITLE_KEYWORDS)
        sent_projects = set(subscriber.get("sent_projects", []))
        for project in projects:
            project_id = str(project.get("id", ""))
            if not project_id or project_id in sent_projects:
                continue
            if not matches_keywords(project.get("name", ""), keywords):
                continue
            if send_telegram_message(format_project_message(project), telegram_token, chat_id):
                sent_projects.add(project_id)
                changed = True
            time.sleep(1)
        subscriber["sent_projects"] = sorted(sent_projects)

    if changed:
        save_subscribers(subscribers)

def run_bot(telegram_token):
    lock_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".kwork-parser.lock")
    lock_file = open(lock_path, "a", encoding="utf-8")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("Бот уже запущен в другом процессе. Второй экземпляр не стартует.")
        lock_file.close()
        return

    register_bot_commands(telegram_token)
    print("Бот запущен. Откройте его в Telegram и отправьте /start.")
    offset = None
    next_project_check = 0

    while True:
        if time.monotonic() >= next_project_check:
            check_new_tasks(telegram_token)
            next_project_check = time.monotonic() + PROJECT_CHECK_INTERVAL

        updates = get_bot_updates(telegram_token, offset)
        if updates is None:
            time.sleep(5)
            continue
        for update in updates:
            process_bot_update(update, telegram_token)
            offset = update["update_id"] + 1

if __name__ == "__main__":
    TELEGRAM_TOKEN = get_keychain_value("kwork-parser.telegram-token", "токен Telegram-бота")
    run_bot(TELEGRAM_TOKEN)