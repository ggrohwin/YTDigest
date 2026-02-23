"""Tests for database operations."""

from datetime import datetime, timedelta, timezone

import aiosqlite
import numpy as np
import pytest

from src import database
from src.models import Article, ArticleSummary, Embedding, Summary, Transcript, Video


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

    async def test_get_all_videos(self, test_db):
        """Test retrieving all videos regardless of age."""
        now = datetime.now(timezone.utc)

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

        # Both videos should be returned regardless of age
        videos = await database.get_all_videos()

        assert len(videos) == 2
        assert videos[0].id == "recent"
        assert videos[1].id == "old"


class TestGetVideosWithoutTranscripts:
    """Tests for get_videos_without_transcripts()."""

    async def test_returns_pending_video(self, test_db):
        """A video with pending transcript status should be returned."""
        video = Video(
            id="pending_vid",
            channel_id="UC123",
            channel_name="Test",
            title="Pending Video",
            published_at=datetime.now(timezone.utc),
            thumbnail_url="https://example.com/thumb.jpg",
            video_url="https://youtube.com/watch?v=pending_vid",
        )
        await database.save_video(video)

        videos = await database.get_videos_without_transcripts(limit=10)
        assert any(v.id == "pending_vid" for v in videos)

    async def test_excludes_completed_video(self, test_db):
        """A completed video should not be returned."""
        video = Video(
            id="done_vid",
            channel_id="UC123",
            channel_name="Test",
            title="Done Video",
            published_at=datetime.now(timezone.utc),
            thumbnail_url="https://example.com/thumb.jpg",
            video_url="https://youtube.com/watch?v=done_vid",
        )
        await database.save_video(video)
        await database.mark_video_completed("done_vid", "like")

        videos = await database.get_videos_without_transcripts(limit=10)
        assert not any(v.id == "done_vid" for v in videos)

    async def test_priority_ordered_first(self, test_db):
        """Prioritized videos should appear before pending ones."""
        now = datetime.now(timezone.utc)
        pending = Video(
            id="pending_vid",
            channel_id="UC123",
            channel_name="Test",
            title="Pending",
            published_at=now - timedelta(days=1),
            thumbnail_url="https://example.com/thumb.jpg",
            video_url="https://youtube.com/watch?v=pending_vid",
        )
        priority = Video(
            id="priority_vid",
            channel_id="UC123",
            channel_name="Test",
            title="Priority",
            published_at=now - timedelta(days=2),
            thumbnail_url="https://example.com/thumb.jpg",
            video_url="https://youtube.com/watch?v=priority_vid",
        )
        await database.save_video(pending)
        await database.save_video(priority)
        await database.update_transcript_status("priority_vid", "priority")

        videos = await database.get_videos_without_transcripts(limit=10)
        assert len(videos) == 2
        assert videos[0].id == "priority_vid"
        assert videos[1].id == "pending_vid"


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

    async def test_get_all_articles(self, test_db):
        """Test retrieving all articles regardless of age."""
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

        # Both articles should be returned regardless of age
        articles = await database.get_all_articles()

        assert len(articles) == 2
        assert articles[0].id == "recent_art_id"
        assert articles[1].id == "old_article_id"

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
        np.testing.assert_array_almost_equal(recovered, [0.1, -0.2, 0.3, 0.4])

    async def test_get_nonexistent_embedding(self, test_db):
        """Test retrieving an embedding that doesn't exist."""
        result = await database.get_embedding("nonexistent", "video_summary")
        assert result is None

    async def test_get_all_embeddings(self, test_db):
        """Test retrieving all embeddings."""
        emb1 = Embedding(
            item_id="vid1",
            item_type="video",
            content_type="video_summary",
            vector=[0.1, 0.2],
        )
        emb2 = Embedding(
            item_id="art1",
            item_type="article",
            content_type="article_summary",
            vector=[0.3, 0.4],
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
            item_id="vid123",
            item_type="video",
            content_type="video_summary",
            vector=[0.9, 0.8, 0.7, 0.6],
        )
        await database.save_embedding(updated, self._to_bytes([0.9, 0.8, 0.7, 0.6]))

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
            id="vid1",
            channel_id="UC1",
            channel_name="Chan",
            title="Vid",
            published_at=datetime.now(timezone.utc),
            thumbnail_url="https://x.com/t.jpg",
            video_url="https://youtube.com/watch?v=vid1",
        )
        await database.save_video(video)
        await database.save_summary(
            Summary(
                video_id="vid1",
                summary="A summary",
                topics=["ai"],
                generated_at=datetime.now(timezone.utc),
            )
        )

        items = await database.get_items_without_embeddings()
        assert len(items) == 1
        assert items[0] == ("vid1", "video")

    async def test_returns_article_with_summary_but_no_embedding(self, test_db):
        """An article that has a summary but no embedding should be returned."""
        article = Article(
            id="art1",
            url="https://example.com/a",
            domain="example.com",
            title="Art",
            added_at=datetime.now(timezone.utc),
            content="Content.",
            word_count=1,
            extract_status="extracted",
        )
        await database.save_article(article)
        await database.save_article_summary(
            ArticleSummary(
                article_id="art1",
                summary="A summary",
                topics=["web"],
                generated_at=datetime.now(timezone.utc),
            )
        )

        items = await database.get_items_without_embeddings()
        assert len(items) == 1
        assert items[0] == ("art1", "article")

    async def test_excludes_items_that_already_have_embeddings(self, test_db):
        """Items with existing embeddings should not be returned."""
        video = Video(
            id="vid2",
            channel_id="UC1",
            channel_name="Chan",
            title="Vid2",
            published_at=datetime.now(timezone.utc),
            thumbnail_url="https://x.com/t.jpg",
            video_url="https://youtube.com/watch?v=vid2",
        )
        await database.save_video(video)
        await database.save_summary(
            Summary(
                video_id="vid2",
                summary="Summary",
                topics=["ai"],
                generated_at=datetime.now(timezone.utc),
            )
        )
        # Also save an embedding for this item
        emb = Embedding(
            item_id="vid2",
            item_type="video",
            content_type="video_summary",
            vector=[0.1, 0.2],
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
        await database.save_summary(
            Summary(
                video_id="vid1",
                summary="Great video about testing.",
                topics=["testing", "python"],
                generated_at=datetime.now(timezone.utc),
            )
        )
        text = await database.get_summary_text_for_embedding("vid1", "video")
        assert "Great video about testing." in text
        assert "Topics:" in text
        assert "testing" in text

    async def test_article_summary(self, test_db):
        """Article summary text should work similarly."""
        article = Article(
            id="art1",
            url="https://example.com/a",
            domain="example.com",
            title="Art",
            added_at=datetime.now(timezone.utc),
            content="Content.",
            word_count=1,
            extract_status="extracted",
        )
        await database.save_article(article)
        await database.save_article_summary(
            ArticleSummary(
                article_id="art1",
                summary="Article about web dev.",
                topics=["web"],
                generated_at=datetime.now(timezone.utc),
            )
        )
        text = await database.get_summary_text_for_embedding("art1", "article")
        assert "Article about web dev." in text

    async def test_returns_none_for_missing_summary(self, test_db):
        """Returns None when no summary exists for the item."""
        text = await database.get_summary_text_for_embedding("nope", "video")
        assert text is None


class TestGetDigestItem:
    """Tests for get_digest_item() — loads a video or article as a DigestItem."""

    async def test_load_video_as_digest_item(self, test_db):
        """A video with a summary should load as a complete DigestItem."""
        video = Video(
            id="vid1",
            channel_id="UC1",
            channel_name="Test Channel",
            title="Test Video",
            published_at=datetime.now(timezone.utc),
            thumbnail_url="https://x.com/t.jpg",
            video_url="https://youtube.com/watch?v=vid1",
            duration="PT10M",
        )
        await database.save_video(video)
        await database.save_summary(
            Summary(
                video_id="vid1",
                summary="A great summary",
                topics=["ai", "ml"],
                category="AI & Machine Learning",
                generated_at=datetime.now(timezone.utc),
            )
        )

        item = await database.get_digest_item("vid1", "video")
        assert item is not None
        assert item.item_type == "video"
        assert item.id == "vid1"
        assert item.title == "Test Video"
        assert item.source_name == "Test Channel"
        assert item.summary == "A great summary"
        assert item.topics == ["ai", "ml"]
        assert item.category == "AI & Machine Learning"
        assert item.duration == "PT10M"

    async def test_load_article_as_digest_item(self, test_db):
        """An article with a summary should load as a complete DigestItem."""
        article = Article(
            id="art1",
            url="https://example.com/post",
            domain="example.com",
            title="Test Article",
            author="Jane",
            added_at=datetime.now(timezone.utc),
            content="Content.",
            word_count=1,
            extract_status="extracted",
        )
        await database.save_article(article)
        await database.save_article_summary(
            ArticleSummary(
                article_id="art1",
                summary="Article summary",
                topics=["web"],
                generated_at=datetime.now(timezone.utc),
            )
        )

        item = await database.get_digest_item("art1", "article")
        assert item is not None
        assert item.item_type == "article"
        assert item.id == "art1"
        assert item.domain == "example.com"
        assert item.author == "Jane"
        assert item.summary == "Article summary"

    async def test_nonexistent_item_returns_none(self, test_db):
        """Requesting a non-existent item returns None."""
        assert await database.get_digest_item("nope", "video") is None
        assert await database.get_digest_item("nope", "article") is None


class TestSaveEmbeddingsBatch:
    """Tests for save_embeddings_batch() — storing multiple chunk embeddings."""

    def _to_bytes(self, vector: list[float]) -> bytes:
        return np.array(vector, dtype=np.float32).tobytes()

    async def test_saves_multiple_chunks(self, test_db):
        """Multiple chunk embeddings for one item should all be stored."""
        embs = []
        for i in range(3):
            emb = Embedding(
                item_id="vid1",
                item_type="video",
                content_type="video_chunk",
                vector=[float(i)],
                chunk_index=i,
            )
            embs.append((emb, self._to_bytes([float(i)])))

        await database.save_embeddings_batch(embs)

        # All 3 should be stored
        all_embs = await database.get_all_embeddings()
        assert len(all_embs) == 3

    async def test_replaces_old_chunks(self, test_db):
        """Re-embedding chunks should replace old ones."""
        # First batch: 2 chunks
        embs1 = []
        for i in range(2):
            emb = Embedding(
                item_id="vid1",
                item_type="video",
                content_type="video_chunk",
                vector=[float(i)],
                chunk_index=i,
            )
            embs1.append((emb, self._to_bytes([float(i)])))
        await database.save_embeddings_batch(embs1)

        # Second batch: 3 chunks (should replace the 2)
        embs2 = []
        for i in range(3):
            emb = Embedding(
                item_id="vid1",
                item_type="video",
                content_type="video_chunk",
                vector=[float(i + 10)],
                chunk_index=i,
            )
            embs2.append((emb, self._to_bytes([float(i + 10)])))
        await database.save_embeddings_batch(embs2)

        all_embs = await database.get_all_embeddings()
        assert len(all_embs) == 3  # replaced, not 5

    async def test_empty_batch_is_noop(self, test_db):
        """Saving an empty batch should not error."""
        await database.save_embeddings_batch([])
        assert await database.count_embeddings() == 0


class TestGetItemsWithoutChunkEmbeddings:
    """Tests for get_items_without_chunk_embeddings()."""

    async def test_video_with_transcript_but_no_chunks(self, test_db):
        """A video with a transcript but no chunk embeddings should be returned."""
        video = Video(
            id="vid1",
            channel_id="UC1",
            channel_name="Chan",
            title="Vid",
            published_at=datetime.now(timezone.utc),
            thumbnail_url="https://x.com/t.jpg",
            video_url="https://youtube.com/watch?v=vid1",
        )
        await database.save_video(video)
        await database.save_transcript(
            Transcript(
                video_id="vid1",
                content="A long transcript...",
                fetched_at=datetime.now(timezone.utc),
            )
        )

        items = await database.get_items_without_chunk_embeddings()
        assert ("vid1", "video") in items

    async def test_article_with_content_but_no_chunks(self, test_db):
        """An article with content but no chunk embeddings should be returned."""
        article = Article(
            id="art1",
            url="https://example.com/a",
            domain="example.com",
            title="Art",
            added_at=datetime.now(timezone.utc),
            content="Full article content here.",
            word_count=5,
            extract_status="extracted",
        )
        await database.save_article(article)

        items = await database.get_items_without_chunk_embeddings()
        assert ("art1", "article") in items

    async def test_excludes_items_with_chunk_embeddings(self, test_db):
        """Items that already have chunk embeddings should not be returned."""
        video = Video(
            id="vid2",
            channel_id="UC1",
            channel_name="Chan",
            title="Vid2",
            published_at=datetime.now(timezone.utc),
            thumbnail_url="https://x.com/t.jpg",
            video_url="https://youtube.com/watch?v=vid2",
        )
        await database.save_video(video)
        await database.save_transcript(
            Transcript(
                video_id="vid2",
                content="Transcript content.",
                fetched_at=datetime.now(timezone.utc),
            )
        )
        # Save a chunk embedding
        emb = Embedding(
            item_id="vid2",
            item_type="video",
            content_type="video_chunk",
            vector=[0.1],
            chunk_index=0,
        )
        await database.save_embedding(emb, np.array([0.1], dtype=np.float32).tobytes())

        items = await database.get_items_without_chunk_embeddings()
        assert ("vid2", "video") not in items


class TestFavorites:
    """Tests for favorite toggle and query operations."""

    @pytest.fixture
    def sample_video(self):
        return Video(
            id="fav_vid_1",
            channel_id="UC123",
            channel_name="Test Channel",
            title="Favoritable Video",
            published_at=datetime.now(timezone.utc),
            thumbnail_url="https://example.com/thumb.jpg",
            video_url="https://youtube.com/watch?v=fav_vid_1",
            duration="PT5M",
        )

    @pytest.fixture
    def sample_article(self):
        return Article(
            id="fav_art_1",
            url="https://example.com/fav-article",
            domain="example.com",
            title="Favoritable Article",
            added_at=datetime.now(timezone.utc),
            content="Some article content.",
            word_count=4,
            extract_status="extracted",
        )

    async def test_toggle_video_favorite_on(self, test_db, sample_video):
        """Toggling an unfavorited video should return True (now favorited)."""
        await database.save_video(sample_video)
        result = await database.toggle_video_favorite("fav_vid_1")
        assert result is True

        video = await database.get_video("fav_vid_1")
        assert video.is_favorited is True
        assert video.favorited_at is not None

    async def test_toggle_video_favorite_off(self, test_db, sample_video):
        """Toggling a favorited video should return False (now unfavorited)."""
        await database.save_video(sample_video)
        await database.toggle_video_favorite("fav_vid_1")  # on
        result = await database.toggle_video_favorite("fav_vid_1")  # off
        assert result is False

        video = await database.get_video("fav_vid_1")
        assert video.is_favorited is False
        assert video.favorited_at is None

    async def test_toggle_video_favorite_nonexistent(self, test_db):
        """Toggling a nonexistent video should return False."""
        result = await database.toggle_video_favorite("nonexistent")
        assert result is False

    async def test_toggle_article_favorite_on(self, test_db, sample_article):
        """Toggling an unfavorited article should return True."""
        await database.save_article(sample_article)
        result = await database.toggle_article_favorite("fav_art_1")
        assert result is True

        article = await database.get_article("fav_art_1")
        assert article.is_favorited is True
        assert article.favorited_at is not None

    async def test_toggle_article_favorite_off(self, test_db, sample_article):
        """Toggling a favorited article should return False."""
        await database.save_article(sample_article)
        await database.toggle_article_favorite("fav_art_1")  # on
        result = await database.toggle_article_favorite("fav_art_1")  # off
        assert result is False

        article = await database.get_article("fav_art_1")
        assert article.is_favorited is False
        assert article.favorited_at is None

    async def test_get_favorite_videos(self, test_db):
        """Only favorited videos should be returned."""
        now = datetime.now(timezone.utc)
        v1 = Video(
            id="v1",
            channel_id="UC1",
            channel_name="C1",
            title="Vid 1",
            published_at=now,
            thumbnail_url="https://example.com/1.jpg",
            video_url="https://youtube.com/watch?v=v1",
        )
        v2 = Video(
            id="v2",
            channel_id="UC1",
            channel_name="C1",
            title="Vid 2",
            published_at=now,
            thumbnail_url="https://example.com/2.jpg",
            video_url="https://youtube.com/watch?v=v2",
        )
        await database.save_video(v1)
        await database.save_video(v2)
        await database.toggle_video_favorite("v1")

        favorites = await database.get_favorite_videos()
        assert len(favorites) == 1
        assert favorites[0].id == "v1"

    async def test_get_favorite_articles(self, test_db, sample_article):
        """Only favorited articles should be returned."""
        await database.save_article(sample_article)

        # Not favorited yet
        favorites = await database.get_favorite_articles()
        assert len(favorites) == 0

        # Favorite it
        await database.toggle_article_favorite("fav_art_1")
        favorites = await database.get_favorite_articles()
        assert len(favorites) == 1
        assert favorites[0].id == "fav_art_1"

    async def test_favorite_persists_across_completion(self, test_db, sample_video):
        """Favoriting a video is independent of completion status."""
        await database.save_video(sample_video)
        await database.toggle_video_favorite("fav_vid_1")
        await database.mark_video_completed("fav_vid_1", "like")

        video = await database.get_video("fav_vid_1")
        assert video.is_favorited is True
        assert video.is_completed is True
