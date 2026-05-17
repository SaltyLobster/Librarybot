import ast
import csv
import html
import hashlib
import logging
import os
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, InputMediaPhoto, KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

CSV_PATH = Path(__file__).parent / "kindle_books.csv"
ENV_PATH = Path(__file__).parent / ".env"
PAGE_SIZE = 8
CALLBACK_DATA_STORE: Dict[str, Dict[str, str]] = {}
SUPPORTED_COVER_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
COVER_FILE_CATALOG: Optional[List[Path]] = None
COVER_CANDIDATE_INDEX: Optional[List[Tuple[Path, str, Set[str]]]] = None

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


@dataclass
class Book:
    title: str
    authors: str
    tags: List[str]
    description: Optional[str] = None
    cover_path: Optional[str] = None
    id: Optional[str] = None


def parse_tags(raw_value: str) -> List[str]:
    value = raw_value.strip()
    if not value:
        return []

    try:
        if value.startswith("[") and value.endswith("]"):
            parsed = ast.literal_eval(value)
            if isinstance(parsed, str):
                parsed = [parsed]
            if isinstance(parsed, (list, tuple)):
                return [tag.strip() for tag in parsed if isinstance(tag, str) and tag.strip()]
    except (ValueError, SyntaxError):
        pass

    # Fallback for comma-separated values
    return [tag.strip() for tag in value.split(",") if tag.strip()]


def get_covers_root() -> Path:
    env_root = os.environ.get("BOOK_COVERS_ROOT")
    if env_root:
        return Path(env_root).expanduser()

    app_root = Path(__file__).parent
    for folder in ("Bookcovers", "bookcovers", "covers"):
        candidate = app_root / folder
        if candidate.exists():
            return candidate

    return app_root / "Bookcovers"


def normalize_cover_path(raw_value: Optional[str]) -> Optional[str]:
    if not raw_value:
        return None

    value = str(raw_value).strip()
    if not value:
        return None

    if value.startswith("http://") or value.startswith("https://"):
        return value

    cover_path = Path(value)
    if not cover_path.is_absolute():
        cover_path = get_covers_root() / cover_path

    if cover_path.exists():
        return str(cover_path)

    return None


def normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.lower()
    for char in "-_./\\'\"()[]{}:;,&!?$@#%^*+=~`|<>" + "“”‘’”–—“”":
        normalized = normalized.replace(char, " ")
    normalized = " ".join(normalized.split())
    return normalized


def get_cover_file_catalog() -> List[Path]:
    global COVER_FILE_CATALOG
    if COVER_FILE_CATALOG is not None:
        return COVER_FILE_CATALOG

    covers_root = get_covers_root()
    if not covers_root.exists():
        COVER_FILE_CATALOG = []
        return COVER_FILE_CATALOG

    COVER_FILE_CATALOG = [
        path
        for path in covers_root.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_COVER_EXTENSIONS
    ]
    return COVER_FILE_CATALOG


def get_cover_file_candidates() -> List[Tuple[Path, str, Set[str]]]:
    global COVER_CANDIDATE_INDEX
    if COVER_CANDIDATE_INDEX is not None:
        return COVER_CANDIDATE_INDEX

    covers_root = get_covers_root()
    COVER_CANDIDATE_INDEX = []
    for path in get_cover_file_catalog():
        try:
            relative = str(path.relative_to(covers_root))
        except Exception:
            relative = str(path)
        normalized = normalize_name(relative)
        tokens = set(normalized.split())
        COVER_CANDIDATE_INDEX.append((path, normalized, tokens))
    return COVER_CANDIDATE_INDEX


def find_cover_for_book(book: Book) -> Optional[str]:
    covers_root = get_covers_root()
    if not covers_root.exists():
        return None

    title_key = normalize_name(book.title)
    author_key = normalize_name(book.authors)
    title_tokens = set(title_key.split())
    author_tokens = set(author_key.split())
    best_match: Optional[Path] = None
    best_score = -1

    for cover_file, candidate, candidate_tokens in get_cover_file_candidates():
        score = 0
        if title_key and title_key in candidate:
            score += 10
        if author_key and author_key in candidate:
            score += 5
        if title_tokens and title_tokens <= candidate_tokens:
            score += 8
        if author_tokens and author_tokens <= candidate_tokens:
            score += 3

        score += len(title_tokens & candidate_tokens) * 2
        score += len(author_tokens & candidate_tokens)

        if score > best_score:
            best_score = score
            best_match = cover_file

    if best_match and best_score > 0:
        return str(best_match)
    return None


def load_books(csv_path: Path) -> Tuple[List[Book], List[str]]:
    books: List[Book] = []
    genres: set[str] = set()

    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            title = (row.get("title") or "").strip()
            authors = (row.get("authors") or "").strip()
            tags = parse_tags(row.get("tags") or "")
            description = (row.get("description") or "").strip()
            cover_path = normalize_cover_path(row.get("cover_path") or row.get("cover_url"))

            if not title or not authors:
                continue

            book = Book(
                title=title,
                authors=authors,
                tags=tags,
                description=description,
                cover_path=cover_path,
                id=row.get("id"),
            )
            if not book.cover_path:
                book.cover_path = find_cover_for_book(book)
            books.append(book)
            genres.update(tags)

    return books, sorted(genres, key=lambda item: item.lower())


def load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return

    with dotenv_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value



def build_callback_id(kind: str, value: str) -> str:
    identifier = hashlib.sha256(f"{kind}:{value}".encode("utf-8")).hexdigest()[:10]
    CALLBACK_DATA_STORE[identifier] = {"kind": kind, "value": value}
    return identifier


def get_callback_payload(callback_id: str) -> Optional[Dict[str, str]]:
    return CALLBACK_DATA_STORE.get(callback_id)


def build_main_menu() -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton("Search by Name or Author"), KeyboardButton("Genres")],
        [KeyboardButton("Help")],
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=False)


def format_book_item(book: Book, index: Optional[int] = None) -> str:
    safe_title = html.escape(book.title)
    safe_author = html.escape(book.authors)
    safe_tags = html.escape(", ".join(book.tags)) if book.tags else "None"
    safe_desc = html.escape(book.description) if book.description else None
    cover_note = "\n📷 Cover available" if book.cover_path else ""
    title_text = f"<b>{index}. {safe_title}</b>" if index is not None else f"<b>{safe_title}</b>"
    lines = [f"{title_text} — {safe_author}", f"Genres: {safe_tags}"]
    if safe_desc:
        lines.append(safe_desc)
    if cover_note:
        lines.append(cover_note)
    return "\n".join(lines)


def render_books_page(
    books: List[Book],
    page: int,
    filter_kind: str,
    callback_id: str,
    label: str,
) -> Tuple[str, InlineKeyboardMarkup]:
    total = len(books)
    if total == 0:
        message = f"No books found for {label}. Try another search or select a different genre."
        return message, InlineKeyboardMarkup([[InlineKeyboardButton("Menu", callback_data="menu")]])

    page_count = (total + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(0, min(page, page_count - 1))
    start = page * PAGE_SIZE
    page_books = books[start : start + PAGE_SIZE]

    lines = [f"<b>{total}</b> books found for {label}. Showing page {page + 1} of {page_count}.\n"]
    has_any_covers = any(book.cover_path for book in page_books)
    if has_any_covers:
        lines.append("Cover images are shown below as part of each book’s caption.")

    for index, book in enumerate(page_books, start=1):
        lines.append(format_book_item(book, index=index))

    message = "\n\n".join(lines)

    buttons = []
    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(
                "Previous", callback_data=f"{filter_kind}|{callback_id}|{page - 1}"
            )
        )
    if page < page_count - 1:
        nav_buttons.append(
            InlineKeyboardButton("Next", callback_data=f"{filter_kind}|{callback_id}|{page + 1}")
        )
    if nav_buttons:
        buttons.append(nav_buttons)

    detail_rows: List[InlineKeyboardButton] = []
    row: List[InlineKeyboardButton] = []
    for item_index, book in enumerate(page_books):
        if book.cover_path:
            row.append(
                InlineKeyboardButton(
                    str(item_index + 1),
                    callback_data=f"detail|{callback_id}|{page}|{item_index}",
                )
            )
            if len(row) >= 4:
                detail_rows.append(row)
                row = []
    if row:
        detail_rows.append(row)
    if detail_rows:
        buttons.extend(detail_rows)

    buttons.append([InlineKeyboardButton("Menu", callback_data="menu")])
    return message, InlineKeyboardMarkup(buttons)


async def send_book_cover_messages(
    message,
    page_books: List[Book],
    page_start: int = 0,
    fallback_text: Optional[str] = None,
    final_markup: Optional[InlineKeyboardMarkup] = None,
    final_message: Optional[str] = None,
) -> None:
    """Send one photo message per book in `page_books`.

    After sending all photos, send a small navigation message with
    `final_markup` (if provided) so the user can navigate pages. The
    optional `final_message` is used as the text shown above the
    navigation buttons (e.g. "Page X of Y").
    """
    sent_any = False
    for offset, book in enumerate(page_books):
        if not book.cover_path:
            continue

        sent_any = True
        safe_title = html.escape(book.title)
        safe_author = html.escape(book.authors)
        safe_tags = html.escape(", ".join(book.tags)) if book.tags else "None"
        safe_desc = html.escape(book.description) if book.description else "No description available."
        caption = (
            f"<b>{page_start + offset + 1}. {safe_title}</b> — {safe_author}\n"
            f"Genres: {safe_tags}\n\n"
            f"{safe_desc}"
        )

        try:
            await message.reply_photo(
                photo=book.cover_path,
                caption=caption,
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            logger.exception("Failed to send cover image for %s", book.title)

    # If we didn't send any covers, send the fallback text (if provided).
    if not sent_any:
        if fallback_text:
            await message.reply_text(fallback_text)
        return

    # After sending all photos, send a short navigation message with markup
    # so the user can go to the next/previous page.
    if final_markup:
        try:
            await message.reply_text(final_message or "", reply_markup=final_markup)
        except Exception:
            # Fallback to a small text if empty message is rejected
            try:
                await message.reply_text(final_message or "Current page", reply_markup=final_markup)
            except Exception:
                logger.exception("Failed to send navigation markup")


def find_books_by_query(query: str) -> List[Book]:
    needle = query.lower()
    return [
        book
        for book in BOOKS
        if needle in book.title.lower() or needle in book.authors.lower()
    ]


def find_books_by_genre(genre: str) -> List[Book]:
    needle = genre.lower()
    return [book for book in BOOKS if any(tag.lower() == needle for tag in book.tags)]


def get_results_from_payload(payload: Dict[str, str]) -> List[Book]:
    kind = payload.get("kind")
    value = payload.get("value", "")
    if kind == "search":
        return find_books_by_query(value)
    if kind == "genre":
        return find_books_by_genre(value)
    return []


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Welcome to your library bot!\n\n"
        "Use the buttons below to search by title or author, or choose a genre.",
        reply_markup=build_main_menu(),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Use the buttons below or type one of the options:\n"
        "• Search by Name or Author\n"
        "• Genres\n"
        "• Help\n\n"
        "If you choose Search, type any part of a title or author name.\n"
        "If you choose Genres, tap a genre button to browse books in that tag.",
        reply_markup=build_main_menu(),
    )


async def ask_for_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["awaiting_search"] = True
    await update.message.reply_text(
        "Enter a book title or author name to search for.",
        reply_markup=build_main_menu(),
    )


async def send_genre_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    buttons = []
    row: List[InlineKeyboardButton] = []
    for genre in GENRES:
        callback_id = build_callback_id("genre", genre)
        row.append(
            InlineKeyboardButton(genre, callback_data=f"genre|{callback_id}|0")
        )
        if len(row) >= 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton("Menu", callback_data="menu")])
    await update.message.reply_text(
        "Choose a genre:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text.strip()

    if context.user_data.get("awaiting_search"):
        context.user_data["awaiting_search"] = False
        query = text
        if not query:
            await update.message.reply_text(
                "Please send a non-empty search query.", reply_markup=build_main_menu()
            )
            return

        results = find_books_by_query(query)
        callback_id = build_callback_id("search", query.lower())
        message, markup = render_books_page(
            results, 0, filter_kind="search", callback_id=callback_id, label=f"search \"{html.escape(query)}\"",
        )
        # Send per-book photo messages followed by navigation buttons.
        page_books = results[:PAGE_SIZE]
        page_count = (len(results) + PAGE_SIZE - 1) // PAGE_SIZE
        final_message = f"Page 1 of {page_count}"
        await send_book_cover_messages(
            update.message,
            page_books,
            page_start=0,
            fallback_text="I could not send cover images for this search page.",
            final_markup=markup,
            final_message=final_message,
        )
        return

    lowered = text.lower()
    if lowered == "search by name or author":
        await ask_for_search(update, context)
        return
    if lowered == "genres":
        await send_genre_menu(update, context)
        return
    if lowered == "help":
        await help_command(update, context)
        return

    await update.message.reply_text(
        "Please use the menu buttons below or type Help for instructions.",
        reply_markup=build_main_menu(),
    )


async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    data = query.data

    if data == "menu":
        await query.answer()
        await query.message.reply_text(
            "Back to the main menu.",
            reply_markup=build_main_menu(),
        )
        return

    segments = data.split("|")
    if len(segments) not in (3, 4):
        await query.answer("Unknown command", show_alert=True)
        return

    kind, callback_id, page_token = segments[0], segments[1], segments[2]
    item_index: Optional[int] = None
    if len(segments) == 4:
        try:
            item_index = int(segments[3])
        except ValueError:
            item_index = None

    payload = get_callback_payload(callback_id)
    if payload is None or payload.get("kind") != kind:
        await query.answer("This selection is no longer available.", show_alert=True)
        return

    page = 0
    try:
        page = int(page_token)
    except ValueError:
        page = 0

    if kind == "detail":
        if item_index is None:
            await query.answer("Book selection is invalid.", show_alert=True)
            return

        results = get_results_from_payload(payload)
        item_offset = page * PAGE_SIZE + item_index
        if item_offset < 0 or item_offset >= len(results):
            await query.answer("This book is no longer available.", show_alert=True)
            return

        book = results[item_offset]
        safe_title = html.escape(book.title)
        safe_author = html.escape(book.authors)
        safe_tags = html.escape(", ".join(book.tags)) if book.tags else "None"
        safe_desc = html.escape(book.description) if book.description else "No description available."
        caption = (
            f"<b>{safe_title}</b> — {safe_author}\n"
            f"Genres: {safe_tags}\n\n"
            f"{safe_desc}"
        )
        await query.answer()
        buttons = [
            [
                InlineKeyboardButton(
                    "Back to results",
                    callback_data=f"{payload['kind']}|{callback_id}|{page}",
                )
            ],
            [InlineKeyboardButton("Menu", callback_data="menu")],
        ]
        if book.cover_path:
            try:
                await query.message.reply_photo(
                    photo=book.cover_path,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup(buttons),
                )
            except Exception:
                await query.message.reply_text(
                    caption,
                    reply_markup=InlineKeyboardMarkup(buttons),
                    parse_mode=ParseMode.HTML,
                )
        else:
            await query.message.reply_text(
                caption,
                reply_markup=InlineKeyboardMarkup(buttons),
                parse_mode=ParseMode.HTML,
            )
        return

    if kind == "covers":
        results = get_results_from_payload(payload)
        page_count = (len(results) + PAGE_SIZE - 1) // PAGE_SIZE
        page = max(0, min(page, page_count - 1))
        start = page * PAGE_SIZE
        page_books = results[start : start + PAGE_SIZE]
        medias = []
        for book in page_books:
            if not book.cover_path:
                continue
            safe_title = html.escape(book.title)
            safe_author = html.escape(book.authors)
            caption = f"<b>{safe_title}</b> — {safe_author}"
            try:
                medias.append(
                    InputMediaPhoto(
                        media=InputFile(book.cover_path),
                        caption=caption,
                        parse_mode=ParseMode.HTML,
                    )
                )
            except Exception:
                continue

        if not medias:
            await query.answer("No covers found for this page.", show_alert=True)
            return

        await query.answer()
        try:
            await query.message.reply_media_group(media=medias)
        except Exception:
            await query.message.reply_text(
                "Unable to send cover thumbnails for this page.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Back to results", callback_data=f"{payload['kind']}|{callback_id}|{page}")],
                    [InlineKeyboardButton("Menu", callback_data="menu")],
                ]),
            )
            return

        await query.message.reply_text(
            "Here are the covers for this page.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Back to results", callback_data=f"{payload['kind']}|{callback_id}|{page}")],
                [InlineKeyboardButton("Menu", callback_data="menu")],
            ]),
        )
        return

    if kind == "genre":
        genre = payload["value"]
        results = find_books_by_genre(genre)
        label = f"genre \"{html.escape(genre)}\""
        message, markup = render_books_page(
            results, page, filter_kind="genre", callback_id=callback_id, label=label
        )
        # Send only the per-book photo messages and a navigation message
        await query.answer()
        start = page * PAGE_SIZE
        page_books = results[start : start + PAGE_SIZE]
        page_count = (len(results) + PAGE_SIZE - 1) // PAGE_SIZE
        final_message = f"Page {page+1} of {page_count}"
        await send_book_cover_messages(
            query.message,
            page_books,
            page_start=start,
            fallback_text="I could not send cover images for this genre page.",
            final_markup=markup,
            final_message=final_message,
        )
        return

    if kind == "search":
        query_text = payload["value"]
        results = find_books_by_query(query_text)
        label = f"search \"{html.escape(query_text)}\""
        message, markup = render_books_page(
            results, page, filter_kind="search", callback_id=callback_id, label=label
        )
        await query.answer()
        start = page * PAGE_SIZE
        page_books = results[start : start + PAGE_SIZE]
        page_count = (len(results) + PAGE_SIZE - 1) // PAGE_SIZE
        final_message = f"Page {page+1} of {page_count}"
        await send_book_cover_messages(
            query.message,
            page_books,
            page_start=start,
            fallback_text="I could not send cover images for this search page.",
            final_markup=markup,
            final_message=final_message,
        )
        return

    await query.answer("Unsupported action", show_alert=True)


def create_application() -> ApplicationBuilder:
    load_dotenv(ENV_PATH)
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "The TELEGRAM_BOT_TOKEN environment variable is required to run the bot."
        )

    logger.info("Telegram token loaded; building application.")
    print("Starting Librarybot application...", flush=True)
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(handle_callback_query))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    logger.info("Application built successfully.")
    return app


def main() -> None:
    global BOOKS, GENRES
    load_dotenv(ENV_PATH)
    BOOKS, GENRES = load_books(CSV_PATH)
    logger.info("Loaded %d books and %d genres.", len(BOOKS), len(GENRES))
    print(f"Loaded {len(BOOKS)} books and {len(GENRES)} genres.", flush=True)

    app = create_application()
    logger.info("Startup complete. Bot is now polling Telegram updates.")
    print("Startup complete. Bot is now polling Telegram updates.", flush=True)
    app.run_polling()


if __name__ == "__main__":
    main()
