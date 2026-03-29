"""Integration tests for the article fetch-and-summarize pipeline.

These tests hit real network endpoints and the Anthropic API.
Run them explicitly with:  pytest -m integration
"""

import os

import pytest

from src import database
from src.articles import fetch_article
from src.models import CATEGORIES, Article, ArticleSummary
from src.summarizer import summarize_content

pytestmark = pytest.mark.integration

# A short, stable, public-domain page unlikely to disappear.
TEST_URL = "https://www.python.org/about/"


@pytest.fixture
async def test_db(tmp_path, monkeypatch):
    """Create a temporary database for integration tests."""
    db_path = tmp_path / "integration.db"
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)
    await database.init_db()
    yield db_path


def _require_api_key():
    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")


# ── Fetch ────────────────────────────────────────────────────────────────


class TestArticleFetch:
    """Test real article extraction via trafilatura."""

    def test_fetch_real_article(self):
        """Fetch a live page and verify the extracted Article fields."""
        article, error = fetch_article(TEST_URL)

        assert error is None, f"fetch_article returned error: {error}"
        assert isinstance(article, Article)
        assert article.url == TEST_URL
        assert article.domain == "python.org"
        assert article.extract_status == "extracted"
        assert len(article.title) > 0  # falls back to "Untitled" at minimum
        assert article.word_count > 50  # page has substantial content
        assert len(article.content) > 200
        assert article.id  # deterministic hash, non-empty

    def test_fetch_bad_url_returns_error(self):
        """A clearly broken URL should return an error, not an exception."""
        article, error = fetch_article("https://thisdomaindoesnotexist.invalid/nope")

        assert article is None
        assert error is not None


# ── Fetch + DB round-trip ────────────────────────────────────────────────


class TestArticleDatabase:
    """Fetch a real article and verify it round-trips through the DB."""

    async def test_save_and_retrieve(self, test_db):
        """Fetched article survives a save/load cycle unchanged."""
        article, error = fetch_article(TEST_URL)
        assert error is None

        is_new = await database.save_article(article)
        assert is_new is True

        retrieved = await database.get_article(article.id)
        assert retrieved is not None
        assert retrieved.url == article.url
        assert retrieved.title == article.title
        assert retrieved.content == article.content
        assert retrieved.word_count == article.word_count
        assert retrieved.domain == article.domain

    async def test_get_by_url(self, test_db):
        """Fetched article can be looked up by URL."""
        article, _ = fetch_article(TEST_URL)
        await database.save_article(article)

        retrieved = await database.get_article_by_url(TEST_URL)
        assert retrieved is not None
        assert retrieved.id == article.id

    async def test_duplicate_save_is_update(self, test_db):
        """Saving the same article twice updates rather than duplicates."""
        article, _ = fetch_article(TEST_URL)
        first = await database.save_article(article)
        second = await database.save_article(article)

        assert first is True
        assert second is False


# ── Summarize ────────────────────────────────────────────────────────────


class TestArticleSummarize:
    """Test real summarization via the Anthropic API."""

    def test_summarize_real_article(self):
        """Fetch an article and summarize it with Claude."""
        _require_api_key()

        article, error = fetch_article(TEST_URL)
        assert error is None

        summary = summarize_content(
            item_id=article.id,
            title=article.title,
            source_name=article.domain,
            content=article.content,
            content_type="article",
            author=article.author,
        )

        assert summary is not None
        assert isinstance(summary, ArticleSummary)
        assert summary.article_id == article.id
        assert len(summary.summary) > 50
        assert len(summary.topics) >= 1
        assert summary.category in CATEGORIES
        assert summary.generated_at is not None


# ── Full pipeline: Fetch → DB → Summarize → DB ──────────────────────────


class TestFullPipeline:
    """End-to-end: fetch article, persist, summarize, persist summary."""

    async def test_end_to_end(self, test_db):
        """Run the complete article pipeline and verify final DB state."""
        _require_api_key()

        # 1. Fetch
        article, error = fetch_article(TEST_URL)
        assert error is None

        # 2. Save article
        await database.save_article(article)

        # 3. Summarize
        summary = summarize_content(
            item_id=article.id,
            title=article.title,
            source_name=article.domain,
            content=article.content,
            content_type="article",
            author=article.author,
        )
        assert summary is not None

        # 4. Save summary
        await database.save_article_summary(summary)

        # 5. Verify both come back from the DB intact
        db_article = await database.get_article(article.id)
        db_summary = await database.get_article_summary(article.id)

        assert db_article is not None
        assert db_article.title == article.title
        assert db_article.word_count == article.word_count

        assert db_summary is not None
        assert db_summary.article_id == article.id
        assert len(db_summary.summary) > 50
        assert len(db_summary.topics) >= 1
        assert db_summary.category in CATEGORIES
