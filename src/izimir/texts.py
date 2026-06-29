"""All bot interface strings (Russian, per the client spec).

Kept in a single module so the interface is easy to maintain and localize.
The wording follows the examples from the technical specification (ТЗ).
"""

from __future__ import annotations

# --- /start, /help -------------------------------------------------------

START = (
    "👋 Привет! Я бот для мониторинга объявлений по недвижимости в Измире.\n"
    "Используйте /help, чтобы увидеть список команд."
)

HELP = (
    "📊 **Статус**\n"
    "Групп: {groups}\n"
    "Ключевых слов: {keywords}\n"
    "Найдено объявлений всего: {total_found}\n"
    "Последний скан: {last_scan}\n"
    "Следующий скан: {next_scan}\n"
    "Окно поиска: последние {scan_hours} ч\n\n"
    "**Команды:**\n"
    "/add_group <ссылка> — добавить группу\n"
    "/remove_group <ссылка> — удалить группу\n"
    "/list_groups — список групп\n"
    "/add_keyword <слово> — добавить ключевое слово\n"
    "/remove_keyword <слово> — удалить ключевое слово\n"
    "/list_keywords — список ключевых слов\n"
    "/scan [дни] — скан сейчас (по умолч. за {scan_hours} ч; напр. /scan 7 — за неделю)\n"
    "/stats — статистика по найденным\n"
    "/export — выгрузить найденное в CSV\n"
    "/reset_seen — сбросить «уже отправленные»"
)

LAST_SCAN_NONE = "—"
LAST_SCAN = "{started_at}, найдено: {found}, статус: {status}"
NEXT_SCAN_NONE = "—"

# --- группы --------------------------------------------------------------

GROUP_ADDED = "✅ Группа добавлена (аккаунт вступил): {title}"
GROUP_EXISTS = "ℹ️ Группа уже в списке: {title}"
GROUP_JOIN_FAILED = "❌ Не удалось найти или вступить в группу: {error}"
GROUP_FLOOD = "⏳ Flood-ожидание {seconds} c, попробуйте позже."
GROUP_REMOVED = "✅ Группа удалена, аккаунт вышел из группы."
GROUP_NOT_FOUND = "❌ Группа не найдена в списке."
GROUPS_EMPTY = "Список групп пуст."

# --- ключевые слова ------------------------------------------------------

KEYWORD_ADDED = "✅ Ключевое слово добавлено: {keyword}"
KEYWORD_EXISTS = "ℹ️ Ключевое слово уже существует: {keyword}"
KEYWORD_REMOVED = "✅ Ключевое слово удалено: {keyword}"
KEYWORD_NOT_FOUND = "❌ Ключевое слово не найдено: {keyword}"
KEYWORDS_EMPTY = "Список ключевых слов пуст."
KEYWORDS_HEADER = "🔑 Ключевые слова:"

# --- скан ----------------------------------------------------------------

SCAN_STARTED = "🔍 Запускаю сканирование…"
SCAN_IN_PROGRESS = "⏳ Сканирование уже выполняется…"
SCAN_DONE = (
    "✅ Сканирование завершено.\n"
    "Окно: {window}\n"
    "Групп просканировано: {groups}\n"
    "Сообщений проверено: {checked}\n"
    "Найдено: {found}\n"
    "Ошибок: {errors}"
)
SCAN_NOTHING_NEW = (
    "ℹ️ Новых совпадений нет. Возможно, они уже отправлялись ранее — "
    "используйте /reset_seen, чтобы переслать заново."
)
SCAN_ERROR = "❌ Ошибка сканирования: {error}"
SCAN_FAILED = "⚠️ Плановое сканирование завершилось с ошибкой. Подробности в логах."

# Префикс для действий, запущенных из мини-приложения (дублируются в чат).
MINIAPP_ACTION = "🔄 Из мини-приложения"

# --- статистика / экспорт / сброс ----------------------------------------

STATS = "📈 Статистика лидов\nВсего: {total}\nСегодня: {today}\nЗа неделю: {week}"
STATS_BY_GROUP_HEADER = "\nПо группам:"
STATS_BY_GROUP_ROW = "• {title}: {count}"
STATS_EMPTY = "📈 Пока нет сохранённых лидов. Запустите /scan."

RESET_DONE = (
    "🧹 Сброшено «уже отправленных»: {count}.\n"
    "Следующий скан пришлёт совпадения заново."
)

EXPORT_EMPTY = "Пока нечего экспортировать — лидов нет."
EXPORT_CAPTION = "📄 Экспорт лидов: {count}"

# --- уведомление о найденном объявлении (ТЗ п.4) -------------------------

FOUND_HEADER = "📢 Найдено потенциальное объявление"
FOUND_AUTHOR = "👤 Автор: {author}"
FOUND_GROUP = "👥 Группа: {group}"
FOUND_DATE = "🕒 Дата: {date}"
FOUND_MESSAGE = "💬 Сообщение:\n{text}"

BTN_OPEN_MESSAGE = "🔎 Открыть сообщение"
BTN_OPEN_GROUP = "👥 Открыть группу"
BTN_WRITE_AUTHOR = "✉ Написать автору"

AUTHOR_UNKNOWN = "Неизвестно"
AUTHOR_NO_NAME = "Без имени"

# --- меню команд Telegram (slash-подсказки) ------------------------------

BOT_COMMANDS: list[tuple[str, str]] = [
    ("help", "Статус и список команд"),
    ("scan", "Запустить скан (можно /scan 72)"),
    ("add_group", "Добавить группу по ссылке"),
    ("remove_group", "Удалить группу"),
    ("list_groups", "Список групп"),
    ("add_keyword", "Добавить ключевое слово"),
    ("remove_keyword", "Удалить ключевое слово"),
    ("list_keywords", "Список ключевых слов"),
    ("stats", "Статистика по найденным"),
    ("export", "Выгрузить найденное в CSV"),
    ("reset_seen", "Сбросить «уже отправленные»"),
]


def detect_language(word: str) -> str:
    """Rough language guess for the keywords.language field.

    Cyrillic → ``ru`` (Russian/Ukrainian not distinguished), Latin → ``tr``
    (Turkish, per the ТЗ examples: Izmir, ev, satılık). Informational only.
    """
    if any("Ѐ" <= ch <= "ӿ" for ch in word):
        return "ru"
    return "tr"
