import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bot import CSV_PATH, Book, BookService, load_books


def book_to_json(book: Book) -> dict:
    return {
        "id": book.id or f"{book.authors}:{book.title}",
        "title": book.title,
        "authors": book.authors,
        "tags": book.tags,
        "description": book.description or "",
        "cover_path": book.cover_path or "",
    }


def build_catalog(csv_path: Path) -> dict:
    books = load_books(csv_path)
    service = BookService(books)
    return {
        "books": [book_to_json(book) for book in books],
        "genres": service.genres,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Librarybot catalog for the Telegram Web App.")
    parser.add_argument("--csv", type=Path, default=CSV_PATH, help="Path to the Librarybot CSV file.")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "webapp" / "catalog.json",
        help="Output catalog JSON path.",
    )
    args = parser.parse_args()

    catalog = build_catalog(args.csv)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Exported {len(catalog['books'])} books to {args.output}")


if __name__ == "__main__":
    main()
