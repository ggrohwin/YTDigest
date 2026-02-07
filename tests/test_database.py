"""Tests for database operations."""

import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
import tempfile
import aiosqlite

import numpy as np

from src.models import Article, ArticleSummary, Embedding, Video, Transcript, Summary
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


class TestEmbeddingOperations:
    """Tests for embedding CRUD operations."""

    @pytest.fixture
    def sample_embedding(self):
        return Embedding(
            item_id="vid123",
            item_type="video",
            content_type="video_summary",
            vector=[0.1, -0.2, 0.3, 0.4],
        )

    def _to_bytes(self, vector: list[float]) -> bytes:
        """Helper to convert a vector to bytes the same way embedder.py does."""
        return np.array(vector, dtype=np.float32).tobytes()

    async def test_save_and_get_embedding(self, test_db, sample_embedding):
        """Test saving and retrieving an embedding."""
        vector_bytes = self._to_bytes(sample_embedding.vector)
        await database.save_embedding(sample_embedding, vector_bytes)

        result = await database.get_embedding("vid123", "video_summary")
        assert result is not None
        emb, raw_bytes = result
        assert emb.item_id == "vid123"
        assert emb.item_type == "video"
        assert emb.content_type == "video_summary"
        assert emb.chunk_index is None

        # Verify the bytes round-trip correctly
        recovered = np.frombuffer(raw_bytes, dtype=np.float32)
        np.testing.assert_array_almost_equal(
            recovered, [0.1, -0.2, 0.3, 0.4]
        )

    async def test_get_nonexistent_embedding(self, test_db):
        """Test retrieving an embedding that doesn't exist."""
        result = await database.get_embedding("nonexistent", "video_summary")
        assert result is None

    async def test_get_all_embeddings(self, test_db):
        """Test retrieving all embeddings."""
        emb1 = Embedding(
            item_id="vid1", item_type="video",
            content_type="video_summary", vector=[0.1, 0.2],
        )
        emb2 = Embedding(
            item_id="art1", item_type="article",
            content_type="article_summary", vector=[0.3, 0.4],
        )

        await database.save_embedding(emb1, self._to_bytes(emb1.vector))
        await database.save_embedding(emb2, self._to_bytes(emb2.vector))

        all_embs = await database.get_all_embeddings()
        assert len(all_embs) == 2
        item_ids = {e.item_id for e, _ in all_embs}
        assert item_ids == {"vid1", "art1"}

    async def test_upsert_replaces_existing(self, test_db, sample_embedding):
        """Test that saving the same item_id + content_type replaces the vector."""
        await database.save_embedding(
            sample_embedding, self._to_bytes([0.1, 0.2, 0.3, 0.4])
        )

        # Save again with different vector
        updated = Embedding(
            item_id="vid123", item_type="video",
            content_type="video_summary", vector=[0.9, 0.8, 0.7, 0.6],
        )
        await database.save_embedding(
            updated, self._to_bytes([0.9, 0.8, 0.7, 0.6])
        )

        all_embs = await database.get_all_embeddings()
        assert len(all_embs) == 1
        _, raw_bytes = all_embs[0]
        recovered = np.frombuffer(raw_bytes, dtype=np.float32)
        np.testing.assert_array_almost_equal(recovered, [0.9, 0.8, 0.7, 0.6])

    async def test_has_embeddings_empty(self, test_db):
        """Test has_embeddings returns False when no embeddings exist."""
        assert await database.has_embeddings() is False

    async def test_has_embeddings_with_data(self, test_db, sample_embedding):
        """Test has_embeddings returns True when embeddings exist."""
        await database.save_embedding(
            sample_embedding, self._to_bytes(sample_embedding.vector)
        )
        assert await database.has_embeddings() is True

    async def test_count_embeddings(self, test_db, sample_embedding):
        """Test counting embeddings."""
        assert await database.count_embeddings() == 0
        await database.save_embedding(
            sample_embedding, self._to_bytes(sample_embedding.vector)
        )
        assert await database.count_embeddings() == 1

    async def test_embeddings_table_created(self, test_db):
        """Verify embeddings table is created during init_db."""
        async with aiosqlite.connect(test_db) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = {row[0] for row in await cursor.fetchall()}
        assert "embeddings" in tables


class TestGetItemsWithoutEmbeddings:
    """Tests for get_items_without_embeddings()."""

    async def test_returns_video_with_summary_but_no_embedding(self, test_db):
        """A video that has a summary but no embedding should be returned."""
        video = Video(
            id="vid1", channel_id="UC1", channel_name="Chan",
            title="Vid", published_at=datetime.now(timezone.utc),
            thumbnail_url="https://x.com/t.jpg",
            video_url="https://youtube.com/watch?v=vid1",
        )
        await database.save_video(video)
        await database.save_summary(Summary(
            video_id="vid1", summary="A summary", topics=["ai"],
            generated_at=datetime.now(timezone.utc),
        ))

        items = await database.get_items_without_embeddings()
        assert len(items) == 1
        assert items[0] == ("vid1", "video")

    async def test_returns_article_with_summary_but_no_embedding(self, test_db):
        """An article that has a summary but no embedding should be returned."""
        article = Article(
            id="art1", url="https://example.com/a", domain="example.com",
            title="Art", added_at=datetime.now(timezone.utc),
            content="Content.", word_count=1, extract_status="extracted",
        )
        await database.save_article(article)
        await database.save_article_summary(ArticleSummary(
            article_id="art1", summary="A summary", topics=["web"],
            generated_at=datetime.now(timezone.utc),
        ))

        items = await database.get_items_without_embeddings()
        assert len(items) == 1
        assert items[0] == ("art1", "article")

    async def test_excludes_items_that_already_have_embeddings(self, test_db):
        """Items with existing embeddings should not be returned."""
        video = Video(
            id="vid2", channel_id="UC1", channel_name="Chan",
            title="Vid2", published_at=datetime.now(timezone.utc),
            thumbnail_url="https://x.com/t.jpg",
            video_url="https://youtube.com/watch?v=vid2",
        )
        await database.save_video(video)
        await database.save_summary(Summary(
            video_id="vid2", summary="Summary", topics=["ai"],
            generated_at=datetime.now(timezone.utc),
        ))
        # Also save an embedding for this item
        emb = Embedding(
            item_id="vid2", item_type="video",
            content_type="video_summary", vector=[0.1, 0.2],
        )
        vector_bytes = np.array([0.1, 0.2], dtype=np.float32).tobytes()
        await database.save_embedding(emb, vector_bytes)

        items = await database.get_items_without_embeddings()
        assert len(items) == 0

    async def test_empty_when_no_summaries(self, test_db):
        """No summaries means nothing to embed."""
        items = await database.get_items_without_embeddings()
        assert items == []


class TestGetSummaryTextForEmbedding:
    """Tests for get_summary_text_for_embedding()."""

    async def test_video_summary_with_topics(self, test_db):
        """Video summary text should include topics."""
        await database.save_summary(Summary(
            video_id="vid1", summary="Great video about testing.",
            topics=["testing", "python"],
            generated_at=datetime.now(timezone.utc),
        ))
        text = await database.get_summary_text_for_embedding("vid1", "video")
        assert "Great video about testing." in text
        assert "Topics:" in text
        assert "testing" in text

    async def test_article_summary(self, test_db):
        """Article summary text should work similarly."""
        article = Article(
            id="art1", url="https://example.com/a", domain="example.com",
            title="Art", added_at=datetime.now(timezone.utc),
            content="Content.", word_count=1, extract_status="extracted",
        )
        await database.save_article(article)
        await database.save_article_summary(ArticleSummary(
            article_id="art1", summary="Article about web dev.",
            topics=["web"], generated_at=datetime.now(timezone.utc),
        ))
        text = await database.get_summary_text_for_embedding("art1", "article")
        assert "Article about web dev." in text

    async def test_returns_none_for_missing_summary(self, test_db):
        """Returns None when no summary exists for the item."""
        text = await database.get_summary_text_for_embedding("nope", "video")
        assert text is None
