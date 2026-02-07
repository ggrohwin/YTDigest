"""Tests for database operations."""

import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
import tempfile
import aiosqlite

from src.models import Article, ArticleSummary, Video, Transcript, Summary
from src import database


@pytest.fixture
async def test_db(tmp_path, monkeypatch):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)
    await database.init_db()
    yield db_path


class TestInitDb:
    """Tests for database initialization."""

    async def test_creates_tables(self, test_db):
        """Verify all tables are created."""
        async with aiosqlite.connect(test_db) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = {row[0] for row in await cursor.fetchall()}

        assert "videos" in tables
        assert "transcripts" in tables
        assert "summaries" in tables


class TestVideoOperations:
    """Tests for video CRUD operations."""

    @pytest.fixture
    def sample_video(self):
        return Video(
            id="test123",
            channel_id="UC123",
            channel_name="Test Channel",
            title="Test Video Title",
            published_at=datetime.now(timezone.utc),
            thumbnail_url="https://example.com/thumb.jpg",
            video_url="https://youtube.com/watch?v=test123",
            duration="PT10M30S",
        )

    async def test_save_and_get_video(self, test_db, sample_video):
        """Test saving and retrieving a video."""
        await database.save_video(sample_video)
        retrieved = await database.get_video("test123")

        assert retrieved is not None
        assert retrieved.id == sample_video.id
        assert retrieved.title == sample_video.title
        assert retrieved.channel_name == sample_video.channel_name
        assert retrieved.duration == sample_video.duration

    async def test_get_nonexistent_video(self, test_db):
        """Test retrieving a video that doesn't exist."""
        retrieved = await database.get_video("nonexistent")
        assert retrieved is None

    async def test_save_video_updates_existing(self, test_db, sample_video):
        """Test that saving a video with same ID updates it."""
        await database.save_video(sample_video)

        # Update the video
        updated_video = Video(
            id="test123",
            channel_id="UC123",
            channel_name="Test Channel",
            title="Updated Title",
            published_at=sample_video.published_at,
            thumbnail_url="https://example.com/thumb.jpg",
            video_url="https://youtube.com/watch?v=test123",
        )
        await database.save_video(updated_video)

        retrieved = await database.get_video("test123")
        assert retrieved.title == "Updated Title"

    async def test_get_videos_since(self, test_db):
        """Test retrieving videos within a date range."""
        now = datetime.now(timezone.utc)

        # Create videos at different times
        old_video = Video(
            id="old",
            channel_id="UC123",
            channel_name="Test",
            title="Old Video",
            published_at=now - timedelta(days=30),
            thumbnail_url="https://example.com/thumb.jpg",
            video_url="https://youtube.com/watch?v=old",
        )
        recent_video = Video(
            id="recent",
            channel_id="UC123",
            channel_name="Test",
            title="Recent Video",
            published_at=now - timedelta(days=2),
            thumbnail_url="https://example.com/thumb.jpg",
            video_url="https://youtube.com/watch?v=recent",
        )

        await database.save_video(old_video)
        await database.save_video(recent_video)

        # Get videos from last 7 days
        videos = await database.get_videos_since(7)

        assert len(videos) == 1
        assert videos[0].id == "recent"


class TestTranscriptOperations:
    """Tests for transcript CRUD operations."""

    @pytest.fixture
    def sample_transcript(self):
        return Transcript(
            video_id="test123",
            content="This is the transcript content for the test video.",
            fetched_at=datetime.now(timezone.utc),
        )

    async def test_save_and_get_transcript(self, test_db, sample_transcript):
        """Test saving and retrieving a transcript."""
        await database.save_transcript(sample_transcript)
        retrieved = await database.get_transcript("test123")

        assert retrieved is not None
        assert retrieved.video_id == sample_transcript.video_id
        assert retrieved.content == sample_transcript.content

    async def test_get_nonexistent_transcript(self, test_db):
        """Test retrieving a transcript that doesn't exist."""
        retrieved = await database.get_transcript("nonexistent")
        assert retrieved is None


class TestSummaryOperations:
    """Tests for summary CRUD operations."""

    @pytest.fixture
    def sample_summary(self):
        return Summary(
            video_id="test123",
            summary="This is a test summary of the video content.",
            topics=["python", "testing", "databases"],
            generated_at=datetime.now(timezone.utc),
        )

    async def test_save_and_get_summary(self, test_db, sample_summary):
        """Test saving and retrieving a summary."""
        await database.save_summary(sample_summary)
        retrieved = await database.get_summary("test123")

        assert retrieved is not None
        assert retrieved.video_id == sample_summary.video_id
        assert retrieved.summary == sample_summary.summary
        assert retrieved.topics == sample_summary.topics

    async def test_get_nonexistent_summary(self, test_db):
        """Test retrieving a summary that doesn't exist."""
        retrieved = await database.get_summary("nonexistent")
        assert retrieved is None

    async def test_topics_stored_correctly(self, test_db, sample_summary):
        """Test that topics list is stored and retrieved correctly."""
        await database.save_summary(sample_summary)
        retrieved = await database.get_summary("test123")

        assert isinstance(retrieved.topics, list)
        assert len(retrieved.topics) == 3
        assert "python" in retrieved.topics


class TestArticleOperations:
    """Tests for article CRUD operations."""

    @pytest.fixture
    def sample_article(self):
        return Article(
            id="abc123def456",
            url="https://example.com/test-post",
            domain="example.com",
            title="Test Article Title",
            author="Jane Doe",
            published_at=datetime.now(timezone.utc),
            added_at=datetime.now(timezone.utc),
            content="This is the full article content for the test article.",
            word_count=10,
            extract_status="extracted",
        )

    async def test_save_and_get_article(self, test_db, sample_article):
        """Test saving and retrieving an article."""
        await database.save_article(sample_article)
        retrieved = await database.get_article("abc123def456")

        assert retrieved is not None
        assert retrieved.id == sample_article.id
        assert retrieved.title == sample_article.title
        assert retrieved.domain == sample_article.domain
        assert retrieved.author == sample_article.author
        assert retrieved.word_count == sample_article.word_count
        assert retrieved.extract_status == "extracted"

    async def test_get_nonexistent_article(self, test_db):
        """Test retrieving an article that doesn't exist."""
        retrieved = await database.get_article("nonexistent")
        assert retrieved is None

    async def test_get_article_by_url(self, test_db, sample_article):
        """Test retrieving an article by its URL."""
        await database.save_article(sample_article)
        retrieved = await database.get_article_by_url("https://example.com/test-post")

        assert retrieved is not None
        assert retrieved.id == sample_article.id
        assert retrieved.url == sample_article.url

    async def test_get_article_by_url_nonexistent(self, test_db):
        """Test retrieving an article by a URL that doesn't exist."""
        retrieved = await database.get_article_by_url("https://example.com/nope")
        assert retrieved is None

    async def test_get_articles_since(self, test_db):
        """Test retrieving articles within a date range."""
        now = datetime.now(timezone.utc)

        old_article = Article(
            id="old_article_id",
            url="https://example.com/old",
            domain="example.com",
            title="Old Article",
            added_at=now - timedelta(days=30),
            content="Old content.",
            word_count=2,
            extract_status="extracted",
        )
        recent_article = Article(
            id="recent_art_id",
            url="https://example.com/recent",
            domain="example.com",
            title="Recent Article",
            added_at=now - timedelta(days=2),
            content="Recent content.",
            word_count=2,
            extract_status="extracted",
        )

        await database.save_article(old_article)
        await database.save_article(recent_article)

        # Get articles from last 7 days
        articles = await database.get_articles_since(7)

        assert len(articles) == 1
        assert articles[0].id == "recent_art_id"

    async def test_save_article_updates_existing(self, test_db, sample_article):
        """Test that saving an article with same ID updates it."""
        await database.save_article(sample_article)

        updated_article = Article(
            id="abc123def456",
            url="https://example.com/test-post",
            domain="example.com",
            title="Updated Title",
            added_at=sample_article.added_at,
            content="Updated content.",
            word_count=2,
            extract_status="extracted",
        )
        await database.save_article(updated_article)

        retrieved = await database.get_article("abc123def456")
        assert retrieved.title == "Updated Title"
        assert retrieved.content == "Updated content."


class TestArticleSummaryOperations:
    """Tests for article summary CRUD operations."""

    @pytest.fixture
    def sample_article(self):
        return Article(
            id="abc123def456",
            url="https://example.com/test-post",
            domain="example.com",
            title="Test Article",
            added_at=datetime.now(timezone.utc),
            content="Content here.",
            word_count=2,
            extract_status="extracted",
        )

    @pytest.fixture
    def sample_article_summary(self):
        return ArticleSummary(
            article_id="abc123def456",
            summary="This is a test summary of the article content.",
            topics=["python", "web", "databases"],
            category="Programming & Development",
            generated_at=datetime.now(timezone.utc),
        )

    async def test_save_and_get_article_summary(
        self, test_db, sample_article, sample_article_summary
    ):
        """Test saving and retrieving an article summary."""
        await database.save_article(sample_article)
        await database.save_article_summary(sample_article_summary)
        retrieved = await database.get_article_summary("abc123def456")

        assert retrieved is not None
        assert retrieved.article_id == sample_article_summary.article_id
        assert retrieved.summary == sample_article_summary.summary
        assert retrieved.category == "Programming & Development"

    async def test_get_nonexistent_article_summary(self, test_db):
        """Test retrieving an article summary that doesn't exist."""
        retrieved = await database.get_article_summary("nonexistent")
        assert retrieved is None

    async def test_topics_stored_correctly(
        self, test_db, sample_article, sample_article_summary
    ):
        """Test that topics list is stored and retrieved correctly."""
        await database.save_article(sample_article)
        await database.save_article_summary(sample_article_summary)
        retrieved = await database.get_article_summary("abc123def456")

        assert isinstance(retrieved.topics, list)
        assert len(retrieved.topics) == 3
        assert "python" in retrieved.topics
        assert "web" in retrieved.topics
        assert "databases" in retrieved.topics
