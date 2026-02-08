"""Tests for Pydantic models."""

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from src.models import (
    Article,
    ArticleSummary,
    ChannelConfig,
    DigestConfig,
    DigestItem,
    Embedding,
    SearchResult,
    AppConfig,
    Video,
    Transcript,
    Summary,
    VideoWithDetails,
)


class TestChannelConfig:
    """Tests for ChannelConfig model."""

    def test_valid_channel(self):
        channel = ChannelConfig(id="UC123", name="Test Channel")
        assert channel.id == "UC123"
        assert channel.name == "Test Channel"

    def test_missing_id(self):
        with pytest.raises(ValidationError):
            ChannelConfig(name="Test Channel")

    def test_missing_name(self):
        with pytest.raises(ValidationError):
            ChannelConfig(id="UC123")


class TestDigestConfig:
    """Tests for DigestConfig model."""

    def test_defaults(self):
        config = DigestConfig()
        assert config.max_videos_per_channel == 5
        assert config.max_age_days == 7

    def test_custom_values(self):
        config = DigestConfig(max_videos_per_channel=10, max_age_days=14)
        assert config.max_videos_per_channel == 10
        assert config.max_age_days == 14


class TestVideo:
    """Tests for Video model."""

    def test_valid_video(self):
        video = Video(
            id="abc123",
            channel_id="UC123",
            channel_name="Test Channel",
            title="Test Video",
            published_at=datetime.now(timezone.utc),
            thumbnail_url="https://example.com/thumb.jpg",
            video_url="https://youtube.com/watch?v=abc123",
        )
        assert video.id == "abc123"
        assert video.duration is None  # Optional field

    def test_video_with_duration(self):
        video = Video(
            id="abc123",
            channel_id="UC123",
            channel_name="Test Channel",
            title="Test Video",
            published_at=datetime.now(timezone.utc),
            thumbnail_url="https://example.com/thumb.jpg",
            video_url="https://youtube.com/watch?v=abc123",
            duration="PT15M33S",
        )
        assert video.duration == "PT15M33S"


class TestTranscript:
    """Tests for Transcript model."""

    def test_valid_transcript(self):
        transcript = Transcript(
            video_id="abc123",
            content="This is the transcript content.",
            fetched_at=datetime.now(timezone.utc),
        )
        assert transcript.video_id == "abc123"
        assert "transcript" in transcript.content


class TestSummary:
    """Tests for Summary model."""

    def test_valid_summary(self):
        summary = Summary(
            video_id="abc123",
            summary="This is a summary of the video.",
            topics=["python", "testing", "pytest"],
            generated_at=datetime.now(timezone.utc),
        )
        assert summary.video_id == "abc123"
        assert len(summary.topics) == 3

    def test_empty_topics(self):
        summary = Summary(
            video_id="abc123",
            summary="This is a summary.",
            topics=[],
            generated_at=datetime.now(timezone.utc),
        )
        assert summary.topics == []


class TestVideoWithDetails:
    """Tests for VideoWithDetails model."""

    def test_video_only(self):
        video = Video(
            id="abc123",
            channel_id="UC123",
            channel_name="Test Channel",
            title="Test Video",
            published_at=datetime.now(timezone.utc),
            thumbnail_url="https://example.com/thumb.jpg",
            video_url="https://youtube.com/watch?v=abc123",
        )
        details = VideoWithDetails(video=video)
        assert details.video.id == "abc123"
        assert details.transcript is None
        assert details.summary is None

    def test_with_all_details(self):
        now = datetime.now(timezone.utc)
        video = Video(
            id="abc123",
            channel_id="UC123",
            channel_name="Test Channel",
            title="Test Video",
            published_at=now,
            thumbnail_url="https://example.com/thumb.jpg",
            video_url="https://youtube.com/watch?v=abc123",
        )
        transcript = Transcript(
            video_id="abc123",
            content="Transcript content",
            fetched_at=now,
        )
        summary = Summary(
            video_id="abc123",
            summary="Summary content",
            topics=["topic1"],
            generated_at=now,
        )
        details = VideoWithDetails(
            video=video,
            transcript=transcript,
            summary=summary,
        )
        assert details.transcript is not None
        assert details.summary is not None


class TestArticle:
    """Tests for Article model."""

    def test_valid_article(self):
        now = datetime.now(timezone.utc)
        article = Article(
            id="abc123def456",
            url="https://example.com/post",
            domain="example.com",
            title="Test Article",
            author="John Doe",
            published_at=now,
            added_at=now,
            content="This is the article content.",
            word_count=5,
            extract_status="extracted",
        )
        assert article.id == "abc123def456"
        assert article.url == "https://example.com/post"
        assert article.domain == "example.com"
        assert article.title == "Test Article"
        assert article.author == "John Doe"
        assert article.word_count == 5
        assert article.extract_status == "extracted"

    def test_article_defaults(self):
        now = datetime.now(timezone.utc)
        article = Article(
            id="abc123def456",
            url="https://example.com/post",
            domain="example.com",
            title="Test Article",
            added_at=now,
            content="Some content here.",
            word_count=3,
        )
        assert article.author is None
        assert article.published_at is None
        assert article.extract_status == "pending"
        assert article.is_completed is False
        assert article.sentiment is None
        assert article.completed_at is None

    def test_article_required_fields(self):
        with pytest.raises(ValidationError):
            Article(
                id="abc123def456",
                url="https://example.com/post",
                # missing domain, title, added_at, content, word_count
            )

    def test_article_invalid_extract_status(self):
        now = datetime.now(timezone.utc)
        with pytest.raises(ValidationError):
            Article(
                id="abc123def456",
                url="https://example.com/post",
                domain="example.com",
                title="Test",
                added_at=now,
                content="Content",
                word_count=1,
                extract_status="invalid_status",
            )


class TestArticleSummary:
    """Tests for ArticleSummary model."""

    def test_valid_summary(self):
        now = datetime.now(timezone.utc)
        summary = ArticleSummary(
            article_id="abc123def456",
            summary="This is a summary of the article.",
            topics=["python", "web", "testing"],
            category="Programming & Development",
            generated_at=now,
        )
        assert summary.article_id == "abc123def456"
        assert summary.summary == "This is a summary of the article."
        assert len(summary.topics) == 3
        assert summary.category == "Programming & Development"

    def test_empty_topics(self):
        now = datetime.now(timezone.utc)
        summary = ArticleSummary(
            article_id="abc123def456",
            summary="A summary with no topics.",
            topics=[],
            generated_at=now,
        )
        assert summary.topics == []

    def test_category_defaults_to_none(self):
        now = datetime.now(timezone.utc)
        summary = ArticleSummary(
            article_id="abc123def456",
            summary="A summary.",
            topics=["topic1"],
            generated_at=now,
        )
        assert summary.category is None


class TestDigestItem:
    """Tests for DigestItem model."""

    def test_video_type(self):
        now = datetime.now(timezone.utc)
        item = DigestItem(
            item_type="video",
            id="vid123",
            title="Test Video",
            url="https://youtube.com/watch?v=vid123",
            source_name="Test Channel",
            published_at=now,
            thumbnail_url="https://example.com/thumb.jpg",
            duration="PT10M30S",
            transcript_status="fetched",
        )
        assert item.item_type == "video"
        assert item.thumbnail_url == "https://example.com/thumb.jpg"
        assert item.duration == "PT10M30S"
        assert item.domain is None
        assert item.word_count is None

    def test_article_type(self):
        now = datetime.now(timezone.utc)
        item = DigestItem(
            item_type="article",
            id="art123",
            title="Test Article",
            url="https://example.com/post",
            source_name="example.com",
            published_at=now,
            author="Jane Doe",
            domain="example.com",
            word_count=500,
        )
        assert item.item_type == "article"
        assert item.author == "Jane Doe"
        assert item.domain == "example.com"
        assert item.word_count == 500
        assert item.thumbnail_url is None
        assert item.duration is None

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            DigestItem(
                item_type="video",
                id="vid123",
                # missing title, url, source_name, published_at
            )

    def test_invalid_item_type(self):
        now = datetime.now(timezone.utc)
        with pytest.raises(ValidationError):
            DigestItem(
                item_type="podcast",
                id="pod123",
                title="Test Podcast",
                url="https://example.com/podcast",
                source_name="Test Source",
                published_at=now,
            )

    def test_defaults(self):
        now = datetime.now(timezone.utc)
        item = DigestItem(
            item_type="video",
            id="vid123",
            title="Test Video",
            url="https://youtube.com/watch?v=vid123",
            source_name="Test Channel",
            published_at=now,
        )
        assert item.added_at is None
        assert item.is_completed is False
        assert item.sentiment is None
        assert item.completed_at is None
        assert item.summary is None
        assert item.topics == []
        assert item.category is None


class TestEmbedding:
    """Tests for Embedding model."""

    def test_valid_summary_embedding(self):
        emb = Embedding(
            item_id="vid123",
            item_type="video",
            content_type="video_summary",
            vector=[0.1, 0.2, 0.3],
        )
        assert emb.item_id == "vid123"
        assert emb.item_type == "video"
        assert emb.content_type == "video_summary"
        assert emb.chunk_index is None

    def test_valid_chunk_embedding(self):
        emb = Embedding(
            item_id="art456",
            item_type="article",
            content_type="article_chunk",
            vector=[0.1, 0.2],
            chunk_index=3,
        )
        assert emb.content_type == "article_chunk"
        assert emb.chunk_index == 3

    def test_invalid_item_type(self):
        with pytest.raises(ValidationError):
            Embedding(
                item_id="x",
                item_type="podcast",
                content_type="video_summary",
                vector=[0.1],
            )

    def test_invalid_content_type(self):
        with pytest.raises(ValidationError):
            Embedding(
                item_id="x",
                item_type="video",
                content_type="unknown_type",
                vector=[0.1],
            )


class TestSearchResult:
    """Tests for SearchResult model."""

    def test_valid_search_result(self):
        now = datetime.now(timezone.utc)
        item = DigestItem(
            item_type="video",
            id="vid123",
            title="Test Video",
            url="https://youtube.com/watch?v=vid123",
            source_name="Test Channel",
            published_at=now,
        )
        result = SearchResult(item=item, score=0.87)
        assert result.score == 0.87
        assert result.item.id == "vid123"
