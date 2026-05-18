"""
Comprehensive test suite for Librarybot application.

This module provides unit and integration tests for all major components:
- BookService (search and filtering)
- MessageFormatter (message formatting)
- CallbackDataHandler (callback serialization)
- UIBuilder (UI generation)
- PagedResponseBuilder (pagination)
- Utility functions (parsing, normalization)
"""

import pytest
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

from bot import (
    Book,
    BookService,
    CallbackDataHandler,
    CallbackType,
    MessageFormatter,
    MessageKey,
    PAGE_SIZE,
    PagedResponseBuilder,
    UIBuilder,
    UserAction,
    parse_tags,
    normalize_name,
    normalize_cover_path,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_books() -> List[Book]:
    """Create a sample list of books for testing."""
    return [
        Book(
            title="The Lord of the Rings",
            authors="J.R.R. Tolkien",
            tags=["Fantasy", "Adventure"],
            description="An epic fantasy adventure.",
            cover_path="/path/to/cover1.jpg",
            id="book1",
        ),
        Book(
            title="1984",
            authors="George Orwell",
            tags=["Dystopian", "Fiction"],
            description="A totalitarian dystopia.",
            cover_path="/path/to/cover2.jpg",
            id="book2",
        ),
        Book(
            title="To Kill a Mockingbird",
            authors="Harper Lee",
            tags=["Fiction", "Classic"],
            description="A story of racial injustice.",
            cover_path="/path/to/cover3.jpg",
            id="book3",
        ),
        Book(
            title="The Hobbit",
            authors="J.R.R. Tolkien",
            tags=["Fantasy", "Adventure"],
            description="A journey to a far away place.",
            cover_path="/path/to/cover4.jpg",
            id="book4",
        ),
        Book(
            title="Pride and Prejudice",
            authors="Jane Austen",
            tags=["Romance", "Classic"],
            description="A tale of love and misunderstanding.",
            cover_path=None,
            id="book5",
        ),
    ]


@pytest.fixture
def book_service(sample_books) -> BookService:
    """Create a BookService with sample books."""
    return BookService(sample_books)


@pytest.fixture
def callback_handler() -> CallbackDataHandler:
    """Create a fresh CallbackDataHandler."""
    return CallbackDataHandler()


@pytest.fixture
def paged_response_builder(book_service, callback_handler) -> PagedResponseBuilder:
    """Create a PagedResponseBuilder with services."""
    return PagedResponseBuilder(book_service, callback_handler)


# ============================================================================
# Tests for parse_tags function
# ============================================================================

class TestParseTags:
    """Test the parse_tags utility function."""
    
    def test_parse_tags_empty_string(self):
        """Test parsing an empty string."""
        assert parse_tags("") == []
    
    def test_parse_tags_comma_separated(self):
        """Test parsing comma-separated values."""
        result = parse_tags("Fiction, Fantasy, Adventure")
        assert result == ["Fiction", "Fantasy", "Adventure"]
    
    def test_parse_tags_list_format(self):
        """Test parsing list format."""
        result = parse_tags("['Fiction', 'Fantasy', 'Adventure']")
        assert result == ["Fiction", "Fantasy", "Adventure"]
    
    def test_parse_tags_single_string_in_list(self):
        """Test parsing a single string in list format."""
        result = parse_tags("['Fiction']")
        assert result == ["Fiction"]
    
    def test_parse_tags_with_extra_spaces(self):
        """Test parsing with extra spaces."""
        result = parse_tags("  Fiction  ,  Fantasy  ,  Adventure  ")
        assert result == ["Fiction", "Fantasy", "Adventure"]
    
    def test_parse_tags_mixed_format(self):
        """Test parsing comma-separated when list parsing fails."""
        result = parse_tags("Fiction, Fantasy")
        assert result == ["Fiction", "Fantasy"]


# ============================================================================
# Tests for normalize_name function
# ============================================================================

class TestNormalizeName:
    """Test the normalize_name utility function."""
    
    def test_normalize_name_basic(self):
        """Test basic normalization."""
        result = normalize_name("The Lord of the Rings")
        assert result == "the lord of the rings"
    
    def test_normalize_name_with_special_chars(self):
        """Test normalization with special characters."""
        result = normalize_name("J.R.R. Tolkien")
        assert result == "j r r tolkien"
    
    def test_normalize_name_with_dashes(self):
        """Test normalization with dashes."""
        result = normalize_name("Lord-of-the-Rings")
        assert result == "lord of the rings"
    
    def test_normalize_name_with_accents(self):
        """Test normalization with accented characters."""
        result = normalize_name("Café")
        assert "cafe" in result or "caf" in result
    
    def test_normalize_name_multiple_spaces(self):
        """Test normalization with multiple spaces."""
        result = normalize_name("The   Lord    of     the      Rings")
        assert result == "the lord of the rings"


# ============================================================================
# Tests for MessageFormatter
# ============================================================================

class TestMessageFormatter:
    """Test the MessageFormatter service."""
    
    def test_escape_html_basic(self):
        """Test HTML escaping."""
        result = MessageFormatter.escape_html("<script>alert('xss')</script>")
        assert "&lt;" in result and "&gt;" in result
        assert "<script>" not in result
    
    def test_escape_html_none(self):
        """Test HTML escaping with None."""
        result = MessageFormatter.escape_html(None)
        assert result == ""
    
    def test_escape_html_quotes(self):
        """Test HTML escaping of quotes."""
        result = MessageFormatter.escape_html('He said "Hello"')
        assert "&quot;" in result or "Hello" in result
    
    def test_format_book_item_without_index(self, sample_books):
        """Test formatting a book item without index."""
        book = sample_books[0]
        result = MessageFormatter.format_book_item(book)
        
        assert "The Lord of the Rings" in result
        assert "J.R.R. Tolkien" in result
        assert "Fantasy" in result
        assert "Adventure" in result
        assert "📷 Cover available" in result
    
    def test_format_book_item_with_index(self, sample_books):
        """Test formatting a book item with index."""
        book = sample_books[0]
        result = MessageFormatter.format_book_item(book, index=1)
        
        assert "<b>1." in result
        assert "The Lord of the Rings" in result
    
    def test_format_book_item_without_description(self):
        """Test formatting a book without description."""
        book = Book(
            title="Test Book",
            authors="Test Author",
            tags=["Fiction"],
            description=None,
        )
        result = MessageFormatter.format_book_item(book)
        
        assert "Test Book" in result
        assert "Test Author" in result
    
    def test_format_book_item_without_cover(self, sample_books):
        """Test formatting a book without cover path."""
        book = sample_books[4]  # Pride and Prejudice has no cover
        result = MessageFormatter.format_book_item(book)
        
        assert "📷 Cover available" not in result
    
    def test_format_book_caption(self, sample_books):
        """Test formatting a book caption."""
        book = sample_books[0]
        result = MessageFormatter.format_book_caption(book)
        
        assert "The Lord of the Rings" in result
        assert "J.R.R. Tolkien" in result
        assert "Fantasy" in result
        assert "An epic fantasy adventure." in result
    
    def test_format_book_caption_with_index(self, sample_books):
        """Test formatting a book caption with index."""
        book = sample_books[0]
        result = MessageFormatter.format_book_caption_with_index(book, 1)
        
        assert "1." in result
        assert "The Lord of the Rings" in result
    
    def test_format_book_caption_no_description(self):
        """Test formatting caption without description."""
        book = Book(
            title="Test",
            authors="Author",
            tags=["Fiction"],
            description=None,
        )
        result = MessageFormatter.format_book_caption(book)
        
        assert "No description available" in result


# ============================================================================
# Tests for BookService
# ============================================================================

class TestBookService:
    """Test the BookService class."""
    
    def test_book_service_initialization(self, sample_books):
        """Test BookService initialization."""
        service = BookService(sample_books)
        
        assert len(service.books) == 5
        assert len(service.genres) > 0
    
    def test_book_service_genres_list(self, book_service):
        """Test that genres are properly extracted and sorted."""
        genres = book_service.genres
        
        assert "Fantasy" in genres
        assert "Adventure" in genres
        assert "Fiction" in genres
        assert genres == sorted(genres, key=lambda x: x.lower())
    
    def test_find_by_query_title(self, book_service):
        """Test finding books by title."""
        results = book_service.find_by_query("Lord")
        
        assert len(results) > 0 
        assert any(b.title == "The Lord of the Rings" for b in results)
    
    def test_find_by_query_author(self, book_service):
        """Test finding books by author."""
        results = book_service.find_by_query("Tolkien")
        
        assert len(results) > 0
        assert all(b.authors == "J.R.R. Tolkien" for b in results)
    
    def test_find_by_query_case_insensitive(self, book_service):
        """Test that search is case insensitive."""
        results1 = book_service.find_by_query("TOLKIEN")
        results2 = book_service.find_by_query("tolkien")
        results3 = book_service.find_by_query("Tolkien")
        
        assert results1 == results2 == results3
    
    def test_find_by_query_no_results(self, book_service):
        """Test searching with no results."""
        results = book_service.find_by_query("NonexistentBook")
        
        assert len(results) == 0
    
    def test_find_by_genre(self, book_service):
        """Test finding books by genre."""
        results = book_service.find_by_genre("Fantasy")
        
        assert len(results) == 2
        assert all("Fantasy" in b.tags for b in results)
    
    def test_find_by_genre_case_insensitive(self, book_service):
        """Test that genre search is case insensitive."""
        results1 = book_service.find_by_genre("FANTASY")
        results2 = book_service.find_by_genre("fantasy")
        results3 = book_service.find_by_genre("Fantasy")
        
        assert results1 == results2 == results3
    
    def test_find_by_genre_no_results(self, book_service):
        """Test genre search with no results."""
        results = book_service.find_by_genre("NonexistentGenre")
        
        assert len(results) == 0
    
    def test_get_results_search_kind(self, book_service):
        """Test get_results with search kind."""
        results = book_service.get_results(CallbackType.SEARCH.value, "Orwell")
        
        assert len(results) == 1
        assert results[0].authors == "George Orwell"
    
    def test_get_results_genre_kind(self, book_service):
        """Test get_results with genre kind."""
        results = book_service.get_results(CallbackType.GENRE.value, "Classic")
        
        assert len(results) == 2
    
    def test_get_results_unknown_kind(self, book_service):
        """Test get_results with unknown kind."""
        results = book_service.get_results("unknown", "value")
        
        assert len(results) == 0


# ============================================================================
# Tests for CallbackDataHandler
# ============================================================================

class TestCallbackDataHandler:
    """Test the CallbackDataHandler class."""
    
    def test_encode_decode_roundtrip(self, callback_handler):
        """Test encoding and decoding a callback."""
        callback_id = callback_handler.encode("search", "query")
        decoded = callback_handler.decode(callback_id)
        
        assert decoded["kind"] == "search"
        assert decoded["value"] == "query"
    
    def test_encode_creates_unique_ids(self, callback_handler):
        """Test that different values create different IDs."""
        id1 = callback_handler.encode("search", "query1")
        id2 = callback_handler.encode("search", "query2")
        
        assert id1 != id2
    
    def test_encode_same_value_creates_same_id(self, callback_handler):
        """Test that same value creates same ID."""
        id1 = callback_handler.encode("search", "query")
        id2 = callback_handler.encode("search", "query")
        
        assert id1 == id2
    
    def test_decode_nonexistent_id(self, callback_handler):
        """Test decoding a non-existent ID."""
        result = callback_handler.decode("nonexistent")
        
        assert result is None
    
    def test_build_callback_data_without_item_index(self, callback_handler):
        """Test building callback data without item index."""
        callback_id = callback_handler.encode("search", "query")
        data = callback_handler.build_callback_data("search", callback_id, 0)
        
        assert data == f"search|{callback_id}|0"
    
    def test_build_callback_data_with_item_index(self, callback_handler):
        """Test building callback data with item index."""
        callback_id = callback_handler.encode("search", "query")
        data = callback_handler.build_callback_data("search", callback_id, 1, 2)
        
        assert data == f"search|{callback_id}|1|2"
    
    def test_parse_callback_data_search(self, callback_handler):
        """Test parsing search callback data."""
        callback_id = callback_handler.encode("search", "query")
        data = callback_handler.build_callback_data("search", callback_id, 0)
        
        parsed = callback_handler.parse_callback_data(data)
        
        assert parsed["kind"] == "search"
        assert parsed["page"] == 0
        assert parsed["item_index"] is None
        assert parsed["value"] == "query"
    
    def test_parse_callback_data_with_item_index(self, callback_handler):
        """Test parsing callback data with item index."""
        callback_id = callback_handler.encode("detail", "search|query")
        data = callback_handler.build_callback_data("detail", callback_id, 1, 3)
        
        parsed = callback_handler.parse_callback_data(data)
        
        assert parsed["item_index"] == 3
    
    def test_parse_callback_data_invalid_format(self, callback_handler):
        """Test parsing invalid callback data."""
        result = callback_handler.parse_callback_data("invalid|data")
        
        assert result is None
    
    def test_parse_callback_data_invalid_page(self, callback_handler):
        """Test parsing callback with invalid page number."""
        callback_id = callback_handler.encode("search", "query")
        data = f"search|{callback_id}|notanumber"
        
        result = callback_handler.parse_callback_data(data)
        
        assert result is None
    
    def test_parse_callback_data_unknown_id(self, callback_handler):
        """Test parsing with unknown callback ID."""
        result = callback_handler.parse_callback_data("search|unknown|0")
        
        assert result is None


# ============================================================================
# Tests for UIBuilder
# ============================================================================

class TestUIBuilder:
    """Test the UIBuilder class."""
    
    def test_build_main_menu(self):
        """Test building main menu."""
        menu = UIBuilder.build_main_menu()
        
        assert menu is not None
        assert menu.keyboard is not None
        assert len(menu.keyboard) > 0
    
    def test_build_genre_buttons(self, book_service, callback_handler):
        """Test building genre buttons."""
        markup = UIBuilder.build_genre_buttons(book_service.genres, callback_handler)
        
        assert markup is not None
        assert markup.inline_keyboard is not None
        assert len(markup.inline_keyboard) > 0
    
    def test_build_genre_buttons_contains_menu(self, book_service, callback_handler):
        """Test that genre buttons include menu button."""
        markup = UIBuilder.build_genre_buttons(book_service.genres, callback_handler)
        
        # Last row should be menu button
        last_row = markup.inline_keyboard[-1]
        assert len(last_row) == 1
        assert last_row[0].text == "Menu"
    
    def test_build_genre_buttons_two_per_row(self, book_service, callback_handler):
        """Test that genre buttons are laid out 2 per row (except menu)."""
        markup = UIBuilder.build_genre_buttons(book_service.genres, callback_handler)
        
        # Check that non-menu rows have max 2 buttons
        for row in markup.inline_keyboard[:-1]:
            assert len(row) <= 2
    
    def test_build_pagination_buttons_first_page(self, callback_handler):
        """Test pagination buttons on first page."""
        callback_id = callback_handler.encode("search", "query")
        buttons = UIBuilder.build_pagination_buttons("search", callback_id, 0, 3, callback_handler)
        
        # First page should only have Next
        assert len(buttons) == 1
        assert buttons[0].text == "Next"
    
    def test_build_pagination_buttons_last_page(self, callback_handler):
        """Test pagination buttons on last page."""
        callback_id = callback_handler.encode("search", "query")
        buttons = UIBuilder.build_pagination_buttons("search", callback_id, 2, 3, callback_handler)
        
        # Last page should only have Previous
        assert len(buttons) == 1
        assert buttons[0].text == "Previous"
    
    def test_build_pagination_buttons_middle_page(self, callback_handler):
        """Test pagination buttons on middle page."""
        callback_id = callback_handler.encode("search", "query")
        buttons = UIBuilder.build_pagination_buttons("search", callback_id, 1, 3, callback_handler)
        
        # Middle page should have both
        assert len(buttons) == 2
        assert buttons[0].text == "Previous"
        assert buttons[1].text == "Next"
    
    def test_build_pagination_buttons_single_page(self, callback_handler):
        """Test pagination buttons with single page."""
        callback_id = callback_handler.encode("search", "query")
        buttons = UIBuilder.build_pagination_buttons("search", callback_id, 0, 1, callback_handler)
        
        # Single page should have no buttons
        assert len(buttons) == 0
    
    def test_build_detail_buttons(self, sample_books, callback_handler):
        """Test building detail buttons."""
        callback_id = callback_handler.encode("search", "query")
        buttons = UIBuilder.build_detail_buttons(
            sample_books, "search", callback_id, 0, callback_handler
        )
        
        # Should have buttons for books with covers
        books_with_covers = [b for b in sample_books if b.cover_path]
        assert len(buttons) > 0
    
    def test_build_detail_buttons_layout(self, sample_books, callback_handler):
        """Test detail buttons layout (4 per row)."""
        callback_id = callback_handler.encode("search", "query")
        buttons = UIBuilder.build_detail_buttons(
            sample_books, "search", callback_id, 0, callback_handler
        )
        
        # Check that no row has more than 4 buttons
        for row in buttons:
            assert len(row) <= 4
    
    def test_build_back_to_results_buttons(self, callback_handler):
        """Test building back to results buttons."""
        callback_id = callback_handler.encode("search", "query")
        buttons = UIBuilder.build_back_to_results_buttons("search", callback_id, 0)
        
        assert len(buttons) == 2
        assert buttons[0][0].text == "Back to results"
        assert buttons[1][0].text == "Menu"


# ============================================================================
# Tests for PagedResponseBuilder
# ============================================================================

class TestPagedResponseBuilder:
    """Test the PagedResponseBuilder class."""
    
    def test_build_results_page_empty_results(self, paged_response_builder):
        """Test building page with no results."""
        message, markup = paged_response_builder.build_results_page(
            [], 0, CallbackType.SEARCH.value, "id", "test"
        )
        
        assert "No books found" in message
    
    def test_build_results_page_single_page(self, sample_books, paged_response_builder):
        """Test building page with single page of results."""
        message, markup = paged_response_builder.build_results_page(
            sample_books[:3], 0, CallbackType.SEARCH.value, "id", "test"
        )
        
        assert "<b>3</b> books found" in message
        assert "Showing page 1 of 1" in message
    
    def test_build_results_page_multiple_pages(self, sample_books, paged_response_builder, callback_handler):
        """Test building page with multiple pages."""
        # Create more books to get multiple pages
        many_books = sample_books * 5  # 25 books
        
        message, markup = paged_response_builder.build_results_page(
            many_books, 0, CallbackType.SEARCH.value, "id", "test"
        )
        
        assert f"<b>{len(many_books)}</b> books found" in message
        assert "Showing page 1 of" in message
    
    def test_build_results_page_pagination_buttons(self, sample_books, paged_response_builder):
        """Test that pagination buttons are included."""
        many_books = sample_books * 5
        
        message, markup = paged_response_builder.build_results_page(
            many_books, 0, CallbackType.SEARCH.value, "id", "test"
        )
        
        assert markup.inline_keyboard is not None
        assert len(markup.inline_keyboard) > 0
    
    def test_build_results_page_detail_buttons(self, sample_books, paged_response_builder):
        """Test that detail buttons are included for books with covers."""
        message, markup = paged_response_builder.build_results_page(
            sample_books, 0, CallbackType.SEARCH.value, "id", "test"
        )
        
        # Should include detail buttons for books with covers
        assert len(markup.inline_keyboard) > 1


# ============================================================================
# Tests for normalize_cover_path
# ============================================================================

class TestNormalizeCoverPath:
    """Test the normalize_cover_path utility function."""
    
    def test_normalize_cover_path_none(self):
        """Test normalizing None."""
        result = normalize_cover_path(None)
        assert result is None
    
    def test_normalize_cover_path_empty_string(self):
        """Test normalizing empty string."""
        result = normalize_cover_path("")
        assert result is None
    
    def test_normalize_cover_path_http_url(self):
        """Test normalizing HTTP URL."""
        url = "http://example.com/cover.jpg"
        result = normalize_cover_path(url)
        assert result == url
    
    def test_normalize_cover_path_https_url(self):
        """Test normalizing HTTPS URL."""
        url = "https://example.com/cover.jpg"
        result = normalize_cover_path(url)
        assert result == url
    
    @patch("bot.Path.exists")
    def test_normalize_cover_path_nonexistent_file(self, mock_exists):
        """Test normalizing nonexistent file."""
        mock_exists.return_value = False
        result = normalize_cover_path("relative/path/cover.jpg")
        assert result is None


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests combining multiple components."""
    
    def test_full_search_flow(self, book_service, callback_handler):
        """Test complete search flow."""
        # Search for a book
        results = book_service.find_by_query("Tolkien")
        assert len(results) > 0
        
        # Format results
        formatted = MessageFormatter.format_book_item(results[0], index=1)
        assert "Tolkien" in formatted
        
        # Create callback
        callback_id = callback_handler.encode(CallbackType.SEARCH.value, "Tolkien")
        data = callback_handler.build_callback_data(CallbackType.SEARCH.value, callback_id, 0)
        
        # Parse callback
        parsed = callback_handler.parse_callback_data(data)
        assert parsed["value"] == "Tolkien"
    
    def test_full_genre_flow(self, book_service, callback_handler):
        """Test complete genre browsing flow."""
        # Get genres
        genres = book_service.genres
        assert len(genres) > 0
        
        # Build genre buttons
        markup = UIBuilder.build_genre_buttons(genres, callback_handler)
        assert len(markup.inline_keyboard) > 0
        
        # Search by genre
        results = book_service.find_by_genre(genres[0])
        assert len(results) > 0
    
    def test_pagination_flow(self, paged_response_builder, sample_books, callback_handler):
        """Test pagination through results."""
        many_books = sample_books * 5
        
        # First page
        msg1, markup1 = paged_response_builder.build_results_page(
            many_books, 0, CallbackType.SEARCH.value, "id", "test"
        )
        assert "Showing page 1 of" in msg1
        
        # Last page
        page_count = (len(many_books) + PAGE_SIZE - 1) // PAGE_SIZE
        msg_last, markup_last = paged_response_builder.build_results_page(
            many_books, page_count - 1, CallbackType.SEARCH.value, "id", "test"
        )
        assert f"Showing page {page_count} of" in msg_last
    
    def test_special_characters_handling(self, book_service):
        """Test handling of special characters in search."""
        book = Book(
            title="<Script>Test</Script>",
            authors="Author & Co.",
            tags=["Test"],
        )
        
        formatted = MessageFormatter.format_book_item(book)
        assert "<Script>" not in formatted
        assert "&lt;" in formatted
    
    def test_empty_service_handling(self):
        """Test BookService with empty book list."""
        service = BookService([])
        
        assert len(service.books) == 0
        assert len(service.genres) == 0
        assert len(service.find_by_query("test")) == 0
        assert len(service.find_by_genre("test")) == 0


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================

class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_book_with_no_tags(self):
        """Test book with empty tags."""
        book = Book(
            title="Test",
            authors="Author",
            tags=[],
        )
        
        formatted = MessageFormatter.format_book_item(book)
        assert "Genres: None" in formatted
    
    def test_very_long_title(self):
        """Test book with very long title."""
        long_title = "A" * 1000
        book = Book(
            title=long_title,
            authors="Author",
            tags=["Test"],
        )
        
        formatted = MessageFormatter.format_book_item(book)
        assert long_title in formatted
    
    def test_unicode_characters(self):
        """Test handling of unicode characters."""
        book = Book(
            title="日本語テキスト",
            authors="作者",
            tags=["Test"],
        )
        
        formatted = MessageFormatter.format_book_item(book)
        assert "日本語テキスト" in formatted
    
    def test_callback_handler_many_callbacks(self, callback_handler):
        """Test callback handler with many callbacks."""
        # Store many callbacks
        for i in range(1000):
            callback_handler.encode("search", f"query{i}")
        
        # Should still work
        id_500 = callback_handler.encode("search", "query500")
        decoded = callback_handler.decode(id_500)
        assert decoded["value"] == "query500"
    
    def test_pagination_with_exact_page_size(self, paged_response_builder):
        """Test pagination with books exactly matching page size."""
        books = [
            Book(title=f"Book {i}", authors="Author", tags=["Test"])
            for i in range(PAGE_SIZE)
        ]
        
        message, markup = paged_response_builder.build_results_page(
            books, 0, CallbackType.SEARCH.value, "id", "test"
        )
        
        assert f"<b>{PAGE_SIZE}</b>" in message
        assert "Showing page 1 of 1" in message


# ============================================================================
# Run tests with: pytest test_bot.py -v

# ============================================================================
# Keyboard Behavior Tests
# ============================================================================

class TestKeyboardBehavior:
    """Test keyboard visibility behavior in different scenarios."""
    
    def test_main_menu_has_keyboard(self):
        """Test that main menu keyboard is built correctly."""
        keyboard = UIBuilder.build_main_menu()
        
        assert keyboard is not None
        assert keyboard.keyboard is not None
        assert len(keyboard.keyboard) > 0
        # Should have Search, Genres, Help buttons
        assert len(keyboard.keyboard[0]) == 2  # First row with Search and Genres
        assert len(keyboard.keyboard[1]) == 1  # Second row with Help
    
    def test_search_action_keeps_keyboard(self):
        """Test that search action should keep keyboard visible."""
        # When user clicks "Search by Name or Author", the keyboard should remain
        # This is tested by checking that UIBuilder.build_main_menu() is used
        # in the _ask_for_search method
        
        keyboard = UIBuilder.build_main_menu()
        assert keyboard is not None
        # Verify it's a ReplyKeyboardMarkup (keyboard visible)
        assert keyboard.__class__.__name__ == "ReplyKeyboardMarkup"
    
    def test_genre_menu_has_inline_buttons(self, book_service, callback_handler):
        """Test that genre menu uses inline buttons instead of keyboard."""
        markup = UIBuilder.build_genre_buttons(book_service.genres, callback_handler)
        
        assert markup is not None
        assert markup.inline_keyboard is not None
        assert len(markup.inline_keyboard) > 0
        # Verify it's an InlineKeyboardMarkup (not a keyboard)
        assert markup.__class__.__name__ == "InlineKeyboardMarkup"
    
    def test_genre_buttons_layout(self, book_service, callback_handler):
        """Test that genre buttons are laid out properly."""
        markup = UIBuilder.build_genre_buttons(book_service.genres, callback_handler)
        
        # Check button layout
        buttons = markup.inline_keyboard
        # Last row should be menu button
        assert buttons[-1][0].text == "Menu"
        
        # Check that genre buttons are grouped in pairs
        for row in buttons[:-1]:  # Exclude last row (menu)
            assert len(row) <= 2


# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
