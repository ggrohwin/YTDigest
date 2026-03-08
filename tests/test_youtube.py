"""Tests for YouTube URL parsing and video fetching."""

from unittest.mock import MagicMock, patch

from src.youtube import (
    get_channel_uploads,
    get_video_by_id,
    is_youtube_url,
    parse_iso8601_duration,
    parse_video_id,
)


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


class TestParseIso8601Duration:
    """Tests for parse_iso8601_duration() — converting ISO 8601 durations to seconds."""

    def test_minutes_and_seconds(self):
        assert parse_iso8601_duration("PT15M33S") == 933

    def test_hours_minutes_seconds(self):
        assert parse_iso8601_duration("PT1H2M30S") == 3750

    def test_seconds_only(self):
        assert parse_iso8601_duration("PT45S") == 45

    def test_minutes_only(self):
        assert parse_iso8601_duration("PT2M") == 120

    def test_hours_only(self):
        assert parse_iso8601_duration("PT1H") == 3600

    def test_zero_seconds(self):
        assert parse_iso8601_duration("PT0S") == 0

    def test_invalid_format(self):
        assert parse_iso8601_duration("not a duration") is None

    def test_empty_string(self):
        assert parse_iso8601_duration("") is None

    def test_case_insensitive(self):
        assert parse_iso8601_duration("pt15m33s") == 933


class TestShortsFiltering:
    """Tests for filtering shorts from channel uploads."""

    def _make_api_responses(self, video_durations):
        """Helper to build mock API responses for playlist + video details.

        video_durations: dict of video_id -> ISO 8601 duration string
        """
        playlist_items = []
        video_details = []
        for vid_id, duration in video_durations.items():
            playlist_items.append(
                {
                    "snippet": {
                        "resourceId": {"videoId": vid_id},
                        "publishedAt": "2026-03-01T12:00:00Z",
                        "title": f"Video {vid_id}",
                        "thumbnails": {
                            "high": {"url": "https://example.com/thumb.jpg"}
                        },
                    }
                }
            )
            video_details.append(
                {
                    "id": vid_id,
                    "snippet": {
                        "title": f"Video {vid_id}",
                        "description": "",
                    },
                    "contentDetails": {"duration": duration},
                    "statistics": {"viewCount": "100"},
                }
            )
        return playlist_items, video_details

    @patch("src.youtube.get_youtube_client")
    def test_shorts_filtered_when_enabled(self, mock_get_client):
        """Videos at or below shorts_max_duration are skipped."""
        mock_youtube = MagicMock()
        mock_get_client.return_value = mock_youtube

        playlist_items, video_details = self._make_api_responses(
            {"long1": "PT10M0S", "short1": "PT45S", "short2": "PT2M0S"}
        )

        # Mock channel -> uploads playlist
        mock_youtube.channels().list().execute.return_value = {
            "items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UU_test"}}}]
        }
        # Mock playlist items
        mock_youtube.playlistItems().list().execute.return_value = {
            "items": playlist_items
        }
        # Mock video details
        mock_youtube.videos().list().execute.return_value = {"items": video_details}

        videos = get_channel_uploads(
            channel_id="UC_test",
            channel_name="Test Channel",
            filter_shorts=True,
            shorts_max_duration=120,
        )

        video_ids = [v.id for v in videos]
        assert "long1" in video_ids
        assert "short1" not in video_ids  # 45s <= 120s, filtered
        assert "short2" not in video_ids  # 120s <= 120s, filtered

    @patch("src.youtube.get_youtube_client")
    def test_shorts_not_filtered_when_disabled(self, mock_get_client):
        """All videos should be returned when filter_shorts=False (default)."""
        mock_youtube = MagicMock()
        mock_get_client.return_value = mock_youtube

        playlist_items, video_details = self._make_api_responses(
            {"long1": "PT10M0S", "short1": "PT45S"}
        )

        mock_youtube.channels().list().execute.return_value = {
            "items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UU_test"}}}]
        }
        mock_youtube.playlistItems().list().execute.return_value = {
            "items": playlist_items
        }
        mock_youtube.videos().list().execute.return_value = {"items": video_details}

        videos = get_channel_uploads(
            channel_id="UC_test",
            channel_name="Test Channel",
            filter_shorts=False,
        )

        video_ids = [v.id for v in videos]
        assert "long1" in video_ids
        assert "short1" in video_ids  # not filtered
