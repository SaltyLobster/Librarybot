# Librarybot

A simple Telegram bot for filtering your fixed book collection by title/author or genre.

## What it does

- Loads a fixed book list from `kindle_books.csv`
- Provides a Telegram menu with buttons for:
  - `Search by Name or Author`
  - `Genres`
  - `Help`
- Supports one-field search across book titles and authors
- Builds the genre menu from CSV `tags`
- Displays short descriptions and optional cover previews for individual books
- Displays results in pages of up to 8 books with `Previous` / `Next` buttons

## Requirements

- Python 3.12+
- A Telegram bot token from BotFather

## Setup

1. Create or activate the virtual environment in the project folder.

```bash
cd /home/salty/Projects/Librarybot
python -m venv .venv
source .venv/bin/activate
```

2. Install dependencies.

```bash
pip install -r requirements.txt
```

3. Set your bot token.

Option A: Export the token in your shell.

```bash
```

Option B: Create a `.env` file in the project root with:

```text
```

If you want to use local cover images, add these fields to `kindle_books.csv`:

```csv
authors,formats,id,pubdate,tags,title,description,cover_path
```

For `cover_path`, you can use either an absolute file path or a path relative to `/home/salty/Documents/Books`.

4. Run the bot.

```bash
python bot.py
```

## Usage

- Start the bot in Telegram with `/start`
- Tap `Search by Name or Author` and enter any title or author text
- Tap `Genres` and choose a genre
- Use `Previous` / `Next` to browse long result lists

## Notes

- The bot uses the fixed `kindle_books.csv` dataset, so no updates are required for the current list.
- If you want, you can add more genres or adjust the page size in `bot.py`.
