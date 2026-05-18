import ast
import csv
import html
import hashlib
import logging
import os
import unicodedata
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, InputMediaPhoto, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ============================================================================
# Configuration and Constants
# ============================================================================

CSV_PATH = Path(__file__).parent / "kindle_books.csv"
ENV_PATH = Path(__file__).parent / ".env"
PAGE_SIZE = 8
SUPPORTED_COVER_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
COVER_FILE_CATALOG: Optional[List[Path]] = None
COVER_CANDIDATE_INDEX: Optional[List[Tuple[Path, str, Set[str]]]] = None

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ============================================================================
# Enums and Constants
# ============================================================================

class CallbackType(str, Enum):
    """Callback types for button actions."""
    SEARCH = "search"
    GENRE = "genre"
    DETAIL = "detail"
    COVERS = "covers"
    MENU = "menu"


class UserAction(str, Enum):
    """User text actions for main menu."""
    SEARCH = "search by name or author"
    GENRES = "genres"
    HELP = "help"


class MessageKey(str, Enum):
    """Keys for storing user data."""
    AWAITING_SEARCH = "awaiting_search"


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class Book:
    title: str
    authors: str
    tags: List[str]
    description: Optional[str] = None
    cover_path: Optional[str] = None
    id: Optional[str] = None


# ============================================================================
# Utility Functions - File I/O and Cover Discovery
# ============================================================================

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
    for char in "-_./\\'\"()[]{}:;,&!?$@#%^*+=~`|<>" + """''"–—""":
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


def load_books(csv_path: Path) -> List[Book]:
    books: List[Book] = []

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

    return books


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


# ============================================================================
# Callback Data Handler - Manages callback serialization/deserialization
# ============================================================================

class CallbackDataHandler:
    """Handles serialization and deserialization of callback data."""
    
    def __init__(self):
        self._store: Dict[str, Dict[str, str]] = {}
    
    def encode(self, kind: str, value: str) -> str:
        """Encode callback data and return a short identifier."""
        identifier = hashlib.sha256(f"{kind}:{value}".encode("utf-8")).hexdigest()[:10]
        self._store[identifier] = {"kind": kind, "value": value}
        return identifier
    
    def decode(self, callback_id: str) -> Optional[Dict[str, str]]:
        """Decode callback ID back to original kind and value."""
        return self._store.get(callback_id)
    
    def build_callback_data(self, kind: str, callback_id: str, page: int, item_index: Optional[int] = None) -> str:
        """Build complete callback data string for button."""
        if item_index is not None:
            return f"{kind}|{callback_id}|{page}|{item_index}"
        return f"{kind}|{callback_id}|{page}"
    
    def parse_callback_data(self, data: str) -> Optional[Dict[str, Any]]:
        """Parse callback data string into components."""
        segments = data.split("|")
        if len(segments) not in (3, 4):
            return None
        
        kind, callback_id, page_token = segments[0], segments[1], segments[2]
        item_index: Optional[int] = None
        
        if len(segments) == 4:
            try:
                item_index = int(segments[3])
            except ValueError:
                return None
        
        try:
            page = int(page_token)
        except ValueError:
            return None
        
        payload = self.decode(callback_id)
        if payload is None or payload.get("kind") != kind:
            return None
        
        return {
            "kind": kind,
            "callback_id": callback_id,
            "page": page,
            "item_index": item_index,
            "value": payload.get("value", ""),
        }


# ============================================================================
# Message Formatter - Centralized formatting logic (DRY principle)
# ============================================================================

class MessageFormatter:
    """Formats messages and captions for the bot."""
    
    @staticmethod
    def escape_html(text: Optional[str]) -> str:
        """Safely escape HTML in text."""
        return html.escape(text) if text else ""
    
    @staticmethod
    def format_book_item(book: Book, index: Optional[int] = None) -> str:
        """Format a book entry with title, author, genres, and description."""
        safe_title = MessageFormatter.escape_html(book.title)
        safe_author = MessageFormatter.escape_html(book.authors)
        safe_tags = MessageFormatter.escape_html(", ".join(book.tags)) if book.tags else "None"
        safe_desc = MessageFormatter.escape_html(book.description)
        
        cover_note = "\n📷 Cover available" if book.cover_path else ""
        title_text = f"<b>{index}. {safe_title}</b>" if index is not None else f"<b>{safe_title}</b>"
        
        lines = [f"{title_text} — {safe_author}", f"Genres: {safe_tags}"]
        if safe_desc:
            lines.append(safe_desc)
        if cover_note:
            lines.append(cover_note)
        
        return "\n".join(lines)
    
    @staticmethod
    def format_book_caption(book: Book) -> str:
        """Format a book caption for photo/detail messages."""
        safe_title = MessageFormatter.escape_html(book.title)
        safe_author = MessageFormatter.escape_html(book.authors)
        safe_tags = MessageFormatter.escape_html(", ".join(book.tags)) if book.tags else "None"
        safe_desc = MessageFormatter.escape_html(book.description) or "No description available."
        
        return (
            f"<b>{safe_title}</b> — {safe_author}\n"
            f"Genres: {safe_tags}\n\n"
            f"{safe_desc}"
        )
    
    @staticmethod
    def format_book_caption_with_index(book: Book, index: int) -> str:
        """Format a book caption with index for paginated results."""
        safe_title = MessageFormatter.escape_html(book.title)
        safe_author = MessageFormatter.escape_html(book.authors)
        safe_tags = MessageFormatter.escape_html(", ".join(book.tags)) if book.tags else "None"
        safe_desc = MessageFormatter.escape_html(book.description) or "No description available."
        
        return (
            f"<b>{index}. {safe_title}</b> — {safe_author}\n"
            f"Genres: {safe_tags}\n\n"
            f"{safe_desc}"
        )


# ============================================================================
# Book Service - Handles all search and filter operations
# ============================================================================

class BookService:
    """Service class for book search and filtering operations."""
    
    def __init__(self, books: List[Book]):
        self.books = books
        self.genres = sorted(set(tag for book in books for tag in book.tags), key=lambda x: x.lower())
    
    def find_by_query(self, query: str) -> List[Book]:
        """Find books by title or author."""
        needle = query.lower()
        return [
            book for book in self.books
            if needle in book.title.lower() or needle in book.authors.lower()
        ]
    
    def find_by_genre(self, genre: str) -> List[Book]:
        """Find books by genre tag."""
        needle = genre.lower()
        return [book for book in self.books if any(tag.lower() == needle for tag in book.tags)]
    
    def get_results(self, kind: str, value: str) -> List[Book]:
        """Get results based on callback kind and value."""
        if kind == CallbackType.SEARCH.value:
            return self.find_by_query(value)
        elif kind == CallbackType.GENRE.value:
            return self.find_by_genre(value)
        return []


# ============================================================================
# UI Builder - Handles button and keyboard generation
# ============================================================================

class UIBuilder:
    """Builds UI elements (buttons, keyboards) for messages."""
    
    @staticmethod
    def build_main_menu() -> ReplyKeyboardMarkup:
        """Build the main menu keyboard."""
        buttons = [
            [KeyboardButton(UserAction.SEARCH.value), KeyboardButton(UserAction.GENRES.value)],
            [KeyboardButton(UserAction.HELP.value)],
        ]
        return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=False)
    
    @staticmethod
    def build_genre_buttons(genres: List[str], callback_handler: CallbackDataHandler) -> InlineKeyboardMarkup:
        """Build genre selection buttons."""
        buttons = []
        row: List[InlineKeyboardButton] = []
        
        for genre in genres:
            callback_id = callback_handler.encode(CallbackType.GENRE.value, genre)
            callback_data = callback_handler.build_callback_data(CallbackType.GENRE.value, callback_id, 0)
            row.append(InlineKeyboardButton(genre, callback_data=callback_data))
            
            if len(row) >= 2:
                buttons.append(row)
                row = []
        
        if row:
            buttons.append(row)
        
        buttons.append([InlineKeyboardButton("Menu", callback_data=CallbackType.MENU.value)])
        return InlineKeyboardMarkup(buttons)

    @staticmethod
    def build_pagination_buttons(
        kind: str,
        callback_id: str,
        page: int,
        page_count: int,
        callback_handler: CallbackDataHandler,
    ) -> List[List[InlineKeyboardButton]]:
        """Build pagination buttons: Previous/Next row + page number row."""
        if page_count <= 1:
            return []
    
        def make_btn(p: int) -> InlineKeyboardButton:
            data = callback_handler.build_callback_data(kind, callback_id, p)
            return InlineKeyboardButton(f" {p + 1} ", callback_data=data)
    
        rows: List[List[InlineKeyboardButton]] = []
    
        # Row 1: Previous / Next
        nav_row = []
        if page > 0:
            prev_data = callback_handler.build_callback_data(kind, callback_id, page - 1)
            nav_row.append(InlineKeyboardButton("Previous", callback_data=prev_data))
        if page < page_count - 1:
            next_data = callback_handler.build_callback_data(kind, callback_id, page + 1)
            nav_row.append(InlineKeyboardButton("Next", callback_data=next_data))
        if nav_row:
            rows.append(nav_row)
    
        # Row 2: page index buttons
        # Always include page 1 and last page.
        # Between them: up to 3 neighbors on each side of current page, excluding current.
        neighbors = [
            p for p in range(page - 3, page + 4)
            if 0 < p < page_count - 1 and p != page
        ]
        pages_to_show = sorted(set([0] + neighbors + [page_count - 1]))
    
        rows.append([make_btn(p) for p in pages_to_show])
    
        return rows
    
    @staticmethod
    def build_back_to_results_buttons(
        kind: str,
        callback_id: str,
        page: int,
    ) -> List[List[InlineKeyboardButton]]:
        """Build back to results and menu buttons."""
        return [
            [InlineKeyboardButton("Back to results", callback_data=f"{kind}|{callback_id}|{page}")],
            [InlineKeyboardButton("Menu", callback_data=CallbackType.MENU.value)],
        ]


# ============================================================================
# Response Builders - Handles response message and markup generation
# ============================================================================

class PagedResponseBuilder:
    """Builds paginated response messages."""
    
    def __init__(self, service: BookService, callback_handler: CallbackDataHandler):
        self.service = service
        self.callback_handler = callback_handler
    
    def build_results_page(
        self,
        books: List[Book],
        page: int,
        kind: str,
        callback_id: str,
        label: str,
    ) -> Tuple[str, InlineKeyboardMarkup]:
        """Build a paginated results page."""
        total = len(books)
        if total == 0:
            message = f"No books found for {label}. Try another search or select a different genre."
            return message, InlineKeyboardMarkup([[InlineKeyboardButton("Menu", callback_data=CallbackType.MENU.value)]])
        
        page_count = (total + PAGE_SIZE - 1) // PAGE_SIZE
        page = max(0, min(page, page_count - 1))
        start = page * PAGE_SIZE
        page_books = books[start : start + PAGE_SIZE]
        
        # Build message text
        lines = [f"<b>{total}</b> books found for {label}. Showing page {page + 1} of {page_count}.\n"]
        has_any_covers = any(book.cover_path for book in page_books)
        if has_any_covers:
            lines.append("Cover images are shown below as part of each book's caption.")
        
        for index, book in enumerate(page_books, start=1):
            lines.append(MessageFormatter.format_book_item(book, index=index))
        
        message = "\n\n".join(lines)
        
        # Build markup with buttons
        buttons: List[List[InlineKeyboardButton]] = []
        
        # Add pagination buttons
        pagination_rows = UIBuilder.build_pagination_buttons(
            kind, callback_id, page, page_count, self.callback_handler
        )
        buttons.extend(pagination_rows)
        
        # Add menu button
        buttons.append([InlineKeyboardButton("Menu", callback_data=CallbackType.MENU.value)])
        
        return message, InlineKeyboardMarkup(buttons)


# ============================================================================
# Callback Handlers - Handle specific callback types
# ============================================================================

class CallbackHandlerFactory:
    """Factory for creating callback handlers based on type."""
    
    def __init__(self, service: BookService, callback_handler: CallbackDataHandler):
        self.service = service
        self.callback_handler = callback_handler
        self.response_builder = PagedResponseBuilder(service, callback_handler)
    
    async def handle_detail(self, query: Any, data: Dict[str, Any]) -> None:
        """Handle detail view callback."""
        item_index = data["item_index"]
        page = data["page"]
        callback_id = data["callback_id"]
        kind = data["kind"]
        
        if item_index is None:
            await query.answer("Book selection is invalid.", show_alert=True)
            return
        
        results = self.service.get_results(kind, data["value"])
        item_offset = page * PAGE_SIZE + item_index
        if item_offset < 0 or item_offset >= len(results):
            await query.answer("This book is no longer available.", show_alert=True)
            return
        
        book = results[item_offset]
        caption = MessageFormatter.format_book_caption(book)
        await query.answer()
        
        buttons = UIBuilder.build_back_to_results_buttons(kind, callback_id, page)
        
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
    
    async def handle_search(self, query: Any, data: Dict[str, Any]) -> None:
        """Handle search results callback."""
        value = data["value"]
        page = data["page"]
        callback_id = data["callback_id"]
        
        results = self.service.find_by_query(value)
        label = f"search \"{MessageFormatter.escape_html(value)}\""
        message, markup = self.response_builder.build_results_page(
            results, page, CallbackType.SEARCH.value, callback_id, label
        )
        
        await query.answer()
        start = page * PAGE_SIZE
        page_books = results[start : start + PAGE_SIZE]
        page_count = (len(results) + PAGE_SIZE - 1) // PAGE_SIZE
        
        await self._send_book_cover_messages(
            query.message,
            page_books,
            page_start=start,
            final_message=f"Page {page + 1} of {page_count}",
            final_markup=markup,
        )
    
    async def handle_genre(self, query: Any, data: Dict[str, Any]) -> None:
        """Handle genre results callback."""
        value = data["value"]
        page = data["page"]
        callback_id = data["callback_id"]
        
        results = self.service.find_by_genre(value)
        label = f"genre \"{MessageFormatter.escape_html(value)}\""
        message, markup = self.response_builder.build_results_page(
            results, page, CallbackType.GENRE.value, callback_id, label
        )
        
        await query.answer()
        start = page * PAGE_SIZE
        page_books = results[start : start + PAGE_SIZE]
        page_count = (len(results) + PAGE_SIZE - 1) // PAGE_SIZE
        
        await self._send_book_cover_messages(
            query.message,
            page_books,
            page_start=start,
            final_message=f"Page {page + 1} of {page_count}",
            final_markup=markup,
        )
    
    async def _send_book_cover_messages(
        self,
        message,
        page_books: List[Book],
        page_start: int = 0,
        final_message: Optional[str] = None,
        final_markup: Optional[InlineKeyboardMarkup] = None,
    ) -> None:
        """Send one photo message per book, then navigation markup."""
        sent_any = False
        for offset, book in enumerate(page_books):
            if not book.cover_path:
                continue
            
            sent_any = True
            caption = MessageFormatter.format_book_caption_with_index(book, page_start + offset + 1)
            
            try:
                await message.reply_photo(
                    photo=book.cover_path,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                )
            except Exception:
                logger.exception("Failed to send cover image for %s", book.title)
        
        # Send navigation message
        if final_markup:
            try:
                await message.reply_text(final_message or "", reply_markup=final_markup)
            except Exception:
                try:
                    await message.reply_text(final_message or "Current page", reply_markup=final_markup)
                except Exception:
                    logger.exception("Failed to send navigation markup")


# ============================================================================
# Command Handlers
# ============================================================================

class CommandHandlers:
    """Handles all bot commands."""
    
    def __init__(self, service: BookService, callback_handler: CallbackDataHandler):
        self.service = service
        self.callback_handler = callback_handler
        self.response_builder = PagedResponseBuilder(service, callback_handler)
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        await update.message.reply_text(
            "Welcome to your library bot!\n\n"
            "Use the buttons below to search by title or author, or choose a genre.",
            reply_markup=UIBuilder.build_main_menu(),
        )
    
    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command."""
        await update.message.reply_text(
            "Use the buttons below or type one of the options:\n"
            "• Search by Name or Author\n"
            "• Genres\n"
            "• Help\n\n"
            "If you choose Search, type any part of a title or author name.\n"
            "If you choose Genres, tap a genre button to browse books in that tag.",
            reply_markup=UIBuilder.build_main_menu(),
        )
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle text messages."""
        text = update.message.text.strip()
        
        # Handle awaiting search
        if context.user_data.get(MessageKey.AWAITING_SEARCH.value):
            context.user_data[MessageKey.AWAITING_SEARCH.value] = False
            await self._handle_search_query(update, context, text)
            return
        
        # Handle menu actions
        lowered = text.lower()
        if lowered == UserAction.SEARCH.value:
            await self._ask_for_search(update, context)
        elif lowered == UserAction.GENRES.value:
            await self._send_genre_menu(update, context)
        elif lowered == UserAction.HELP.value:
            await self.help(update, context)
        else:
            await update.message.reply_text(
                "Please use the menu buttons below or type Help for instructions.",
                reply_markup=UIBuilder.build_main_menu(),
            )
    
    async def _ask_for_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Ask user for search query."""
        context.user_data[MessageKey.AWAITING_SEARCH.value] = True
        await update.message.reply_text(
            "Enter a book title or author name to search for.",
            reply_markup=UIBuilder.build_main_menu(),
        )
    
    async def _send_genre_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send genre selection menu and hide the keyboard."""
        markup = UIBuilder.build_genre_buttons(self.service.genres, self.callback_handler)
        # Send genre buttons and immediately remove keyboard
        await update.message.reply_text(
            "Choose a genre:",
            reply_markup=markup,
        )
        # Remove keyboard by sending an empty message with ReplyKeyboardRemove
        await update.message.reply_text(
            " ",  # Single space to satisfy Telegram's non-empty message requirement
            reply_markup=ReplyKeyboardRemove(),
        )
    
    async def _handle_search_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE, query: str) -> None:
        """Handle search query text."""
        if not query:
            await update.message.reply_text(
                "Please send a non-empty search query.", reply_markup=UIBuilder.build_main_menu()
            )
            return
        
        results = self.service.find_by_query(query)
        callback_id = self.callback_handler.encode(CallbackType.SEARCH.value, query.lower())
        message, markup = self.response_builder.build_results_page(
            results, 0, CallbackType.SEARCH.value, callback_id, f"search \"{MessageFormatter.escape_html(query)}\"",
        )
        
        page_books = results[:PAGE_SIZE]
        page_count = (len(results) + PAGE_SIZE - 1) // PAGE_SIZE
        
        factory = CallbackHandlerFactory(self.service, self.callback_handler)
        await factory._send_book_cover_messages(
            update.message,
            page_books,
            page_start=0,
            final_message=f"Page 1 of {page_count}",
            final_markup=markup,
        )


# ============================================================================
# Callback Query Handler
# ============================================================================

async def handle_callback_query(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    service: BookService,
    callback_handler: CallbackDataHandler,
) -> None:
    """Handle all callback queries."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    
    data = query.data
    
    # Handle menu button
    if data == CallbackType.MENU.value:
        await query.answer()
        await query.message.reply_text(
            reply_markup=UIBuilder.build_main_menu(),
        )
        return
    
    # Parse callback data
    parsed = callback_handler.parse_callback_data(data)
    if not parsed:
        await query.answer("Unknown command", show_alert=True)
        return
    
    kind = parsed["kind"]
    factory = CallbackHandlerFactory(service, callback_handler)
    
    try:
        if kind == CallbackType.DETAIL.value:
            await factory.handle_detail(query, parsed)
        elif kind == CallbackType.SEARCH.value:
            await factory.handle_search(query, parsed)
        elif kind == CallbackType.GENRE.value:
            await factory.handle_genre(query, parsed)
        else:
            await query.answer("Unsupported action", show_alert=True)
    except Exception:
        logger.exception("Error handling callback %s", kind)
        await query.answer("An error occurred processing your request.", show_alert=True)


# ============================================================================
# Application Setup
# ============================================================================

def create_application(service: BookService, callback_handler: CallbackDataHandler) -> Application:
    """Create and configure the Telegram application."""
    load_dotenv(ENV_PATH)
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "The TELEGRAM_BOT_TOKEN environment variable is required to run the bot."
        )
    
    logger.info("Telegram token loaded; building application.")
    print("Starting Librarybot application...", flush=True)
    
    app = ApplicationBuilder().token(token).build()
    
    # Create handlers
    commands = CommandHandlers(service, callback_handler)
    
    # Add handlers
    app.add_handler(CommandHandler("start", commands.start))
    app.add_handler(CommandHandler("help", commands.help))
    app.add_handler(CallbackQueryHandler(
        lambda u, c: handle_callback_query(u, c, service, callback_handler)
    ))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, commands.handle_text))
    
    logger.info("Application built successfully.")
    return app


def main() -> None:
    """Main entry point."""
    load_dotenv(ENV_PATH)
    books = load_books(CSV_PATH)
    logger.info("Loaded %d books.", len(books))
    print(f"Loaded {len(books)} books.", flush=True)
    
    # Create services
    service = BookService(books)
    callback_handler = CallbackDataHandler()
    
    app_instance = create_application(service, callback_handler)
    logger.info("Startup complete. Bot is now polling Telegram updates.")
    print("Startup complete. Bot is now polling Telegram updates.", flush=True)
    app_instance.run_polling()


if __name__ == "__main__":
    main()
