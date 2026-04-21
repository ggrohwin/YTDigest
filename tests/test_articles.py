"""Tests for article utility functions."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.articles import extract_domain, fetch_article, generate_article_id
from src.models import Article


def _mock_response(text: str, status_code: int = 200) -> MagicMock:
    """Build a fake requests.Response."""
    resp = MagicMock()
    resp.text = text
    resp.status_code = status_code
    resp.raise_for_status.return_value = None
    return resp


class TestGenerateArticleId:
    """Tests for generate_article_id."""

    def test_deterministic(self):
        """Same URL always produces the same ID."""
        url = "https://example.com/some-article"
        id1 = generate_article_id(url)
        id2 = generate_article_id(url)
        assert id1 == id2

    def test_length_is_12(self):
        """ID is always 12 characters long."""
        url = "https://example.com/some-article"
        article_id = generate_article_id(url)
        assert len(article_id) == 12

    def test_different_urls_produce_different_ids(self):
        """Different URLs should produce different IDs."""
        id1 = generate_article_id("https://example.com/article-one")
        id2 = generate_article_id("https://example.com/article-two")
        assert id1 != id2

    def test_hex_characters_only(self):
        """ID should contain only hexadecimal characters."""
        article_id = generate_article_id("https://example.com/test")
        assert all(c in "0123456789abcdef" for c in article_id)


class TestExtractDomain:
    """Tests for extract_domain."""

    def test_basic_domain(self):
        """Extract domain from a simple URL."""
        domain = extract_domain("https://example.com/path/to/page")
        assert domain == "example.com"

    def test_strips_www(self):
        """www. prefix should be stripped."""
        domain = extract_domain("https://www.example.com/page")
        assert domain == "example.com"

    def test_handles_subdomains(self):
        """Subdomains other than www should be preserved."""
        domain = extract_domain("https://blog.example.com/post")
        assert domain == "blog.example.com"

    def test_handles_http(self):
        """HTTP URLs should work the same as HTTPS."""
        domain = extract_domain("http://example.com/page")
        assert domain == "example.com"

    def test_empty_url(self):
        """An empty or invalid URL returns an empty string."""
        domain = extract_domain("")
        assert domain == ""


class TestFetchArticle:
    """Tests for fetch_article using mocked requests and trafilatura."""

    @patch("src.articles.trafilatura")
    @patch("src.articles.requests.get")
    def test_successful_fetch(self, mock_get, mock_trafilatura):
        """Test successful article extraction."""
        mock_get.return_value = _mock_response("<html>downloaded content</html>")
        mock_trafilatura.extract.return_value = "Extracted text content"
        mock_trafilatura.bare_extraction.return_value = SimpleNamespace(
            text="This is the extracted article body text.",
            title="Great Article Title",
            author="John Doe",
            date="2025-01-15",
        )

        article, error = fetch_article("https://example.com/great-article")

        assert error is None
        assert article is not None
        assert isinstance(article, Article)
        assert article.title == "Great Article Title"
        assert article.author == "John Doe"
        assert article.domain == "example.com"
        assert article.url == "https://example.com/great-article"
        assert article.content == "This is the extracted article body text."
        assert article.word_count == 7
        assert article.extract_status == "extracted"
        assert article.published_at is not None

    @patch("src.articles.trafilatura")
    @patch("src.articles.requests.get")
    def test_download_failure(self, mock_get, mock_trafilatura):
        """Test when the page body is empty."""
        mock_get.return_value = _mock_response("")

        article, error = fetch_article("https://example.com/broken")

        assert article is None
        assert error == "Failed to download page"

    @patch("src.articles.trafilatura")
    @patch("src.articles.requests.get")
    def test_extract_returns_none(self, mock_get, mock_trafilatura):
        """Test when trafilatura downloads but cannot extract content."""
        mock_get.return_value = _mock_response("<html>some html</html>")
        mock_trafilatura.extract.return_value = None

        article, error = fetch_article("https://example.com/no-content")

        assert article is None
        assert error == "Could not extract article content"

    @patch("src.articles.trafilatura")
    @patch("src.articles.requests.get")
    def test_bare_extraction_returns_none(self, mock_get, mock_trafilatura):
        """Test when extract works but bare_extraction returns None."""
        mock_get.return_value = _mock_response("<html>some html</html>")
        mock_trafilatura.extract.return_value = "Some text"
        mock_trafilatura.bare_extraction.return_value = None

        article, error = fetch_article("https://example.com/partial")

        assert article is None
        assert error == "Could not extract article content"

    @patch("src.articles.trafilatura")
    @patch("src.articles.requests.get")
    def test_bare_extraction_no_text(self, mock_get, mock_trafilatura):
        """Test when bare_extraction result has no text field."""
        mock_get.return_value = _mock_response("<html>some html</html>")
        mock_trafilatura.extract.return_value = "Some text"
        mock_trafilatura.bare_extraction.return_value = SimpleNamespace(title="A Title")

        article, error = fetch_article("https://example.com/empty")

        assert article is None
        assert error == "Could not extract article content"

    @patch("src.articles.trafilatura")
    @patch("src.articles.requests.get")
    def test_missing_title_defaults_to_untitled(self, mock_get, mock_trafilatura):
        """Test that a missing title defaults to 'Untitled'."""
        mock_get.return_value = _mock_response("<html>content</html>")
        mock_trafilatura.extract.return_value = "text"
        mock_trafilatura.bare_extraction.return_value = SimpleNamespace(
            text="Some body text.",
        )

        article, error = fetch_article("https://example.com/no-title")

        assert error is None
        assert article is not None
        assert article.title == "Untitled"
        assert article.author is None
        assert article.published_at is None

    @patch("src.articles.requests.get")
    def test_exception_returns_error(self, mock_get):
        """Test that exceptions are caught and returned as error messages."""
        mock_get.side_effect = ConnectionError("Connection refused")

        article, error = fetch_article("https://example.com/error")

        assert article is None
        assert "Connection refused" in error

    @patch("src.articles.trafilatura")
    @patch("src.articles.requests.get")
    def test_invalid_date_ignored(self, mock_get, mock_trafilatura):
        """Test that an unparseable date does not cause failure."""
        mock_get.return_value = _mock_response("<html>content</html>")
        mock_trafilatura.extract.return_value = "text"
        mock_trafilatura.bare_extraction.return_value = SimpleNamespace(
            text="Article body.",
            title="Date Test",
            date="not-a-valid-date",
        )

        article, error = fetch_article("https://example.com/bad-date")

        assert error is None
        assert article is not None
        assert article.published_at is None
