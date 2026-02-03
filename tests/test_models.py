"""Tests for Pydantic models."""

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from src.models import (
    ChannelConfig,
    DigestConfig,
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
