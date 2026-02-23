"""Tests for YouTube URL parsing and video fetching."""

from unittest.mock import MagicMock, patch

from src.youtube import get_video_by_id, is_youtube_url, parse_video_id


class TestParseVideoId:
    """Tests for parse_video_id() — extracting video IDs from URLs."""

    def test_standard_watch_url(self):
        assert (
            parse_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
            == "dQw4w9WgXcQ"
        )

    def test_watch_url_without_www(self):
        assert (
            parse_video_id("https://youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
        )

    def test_watch_url_with_extra_params(self):
        assert (
            parse_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=120")
            == "dQw4w9WgXcQ"
        )

    def test_short_url(self):
        assert parse_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_short_url_with_params(self):
        assert parse_video_id("https://youtu.be/dQw4w9WgXcQ?t=30") == "dQw4w9WgXcQ"

    def test_embed_url(self):
        assert (
            parse_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
        )

    def test_v_url(self):
        assert parse_video_id("https://www.youtube.com/v/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_shorts_url(self):
        assert parse_video_id("https://youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_mobile_url(self):
        assert (
            parse_video_id("https://m.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
        )

    def test_http_url(self):
        assert (
            parse_video_id("http://www.youtube.com/watch?v=dQw4w9WgXcQ")
            == "dQw4w9WgXcQ"
        )

    def test_non_youtube_url(self):
        assert parse_video_id("https://example.com/watch?v=abc123") is None

    def test_empty_string(self):
        assert parse_video_id("") is None

    def test_none(self):
        assert parse_video_id(None) is None

    def test_youtube_url_without_video_id(self):
        assert parse_video_id("https://www.youtube.com/") is None

    def test_watch_url_missing_v_param(self):
        assert parse_video_id("https://www.youtube.com/watch?list=abc") is None


class TestIsYoutubeUrl:
    """Tests for is_youtube_url() — detecting YouTube URLs."""

    def test_youtube_url(self):
        assert is_youtube_url("https://www.youtube.com/watch?v=abc123") is True

    def test_short_url(self):
        assert is_youtube_url("https://youtu.be/abc123") is True

    def test_non_youtube_url(self):
        assert is_youtube_url("https://example.com/article") is False

    def test_empty(self):
        assert is_youtube_url("") is False


class TestGetVideoById:
    """Tests for get_video_by_id() with mocked YouTube API."""

    @patch("src.youtube.get_youtube_client")
    def test_fetches_video(self, mock_get_client):
        """get_video_by_id should return a Video with metadata from the API."""
        mock_youtube = MagicMock()
        mock_get_client.return_value = mock_youtube

        mock_youtube.videos().list().execute.return_value = {
            "items": [
                {
                    "id": "abc123",
                    "snippet": {
                        "title": "Test Video",
                        "channelId": "UCxyz",
                        "channelTitle": "Test Channel",
                        "publishedAt": "2026-01-15T12:00:00Z",
                        "thumbnails": {
                            "high": {
                                "url": "https://i.ytimg.com/vi/abc123/hqdefault.jpg"
                            },
                        },
                    },
                    "contentDetails": {
                        "duration": "PT15M33S",
                    },
                }
            ],
        }

        video = get_video_by_id("abc123")

        assert video is not None
        assert video.id == "abc123"
        assert video.title == "Test Video"
        assert video.channel_name == "Test Channel"
        assert video.channel_id == "UCxyz"
        assert video.duration == "PT15M33S"
        assert "abc123" in video.video_url

    @patch("src.youtube.get_youtube_client")
    def test_video_not_found(self, mock_get_client):
        """get_video_by_id should return None for a non-existent video."""
        mock_youtube = MagicMock()
        mock_get_client.return_value = mock_youtube
        mock_youtube.videos().list().execute.return_value = {"items": []}

        video = get_video_by_id("nonexistent")
        assert video is None
