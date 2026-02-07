import logging
import os
import re
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import parse_qs, urlparse

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .models import Video

logger = logging.getLogger("ytdigest")


def get_youtube_client():
    """Create and return a YouTube API client."""
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        raise ValueError("YOUTUBE_API_KEY environment variable not set")
    return build("youtube", "v3", developerKey=api_key, cache_discovery=False)


def get_channel_uploads_playlist_id(youtube, channel_id: str) -> Optional[str]:
    """Get the uploads playlist ID for a channel."""
    try:
        response = youtube.channels().list(
            part="contentDetails",
            id=channel_id
        ).execute()

        if response.get("items"):
            return response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    except HttpError as e:
        logger.error(f"Error fetching channel {channel_id}: {e}")
    return None


def get_channel_uploads(
    channel_id: str,
    channel_name: str,
    max_results: int = 5,
    published_after: Optional[datetime] = None
) -> list[Video]:
    """Fetch recent videos from a channel's uploads playlist."""
    youtube = get_youtube_client()

    uploads_playlist_id = get_channel_uploads_playlist_id(youtube, channel_id)
    if not uploads_playlist_id:
        logger.warning(f"Could not find uploads playlist for channel {channel_id}")
        return []

    try:
        response = youtube.playlistItems().list(
            part="snippet",
            playlistId=uploads_playlist_id,
            maxResults=max_results
        ).execute()

        # Collect video data first
        video_data = []
        for item in response.get("items", []):
            snippet = item["snippet"]
            video_id = snippet["resourceId"]["videoId"]
            published_at = datetime.fromisoformat(
                snippet["publishedAt"].replace("Z", "+00:00")
            )

            if published_after and published_at < published_after:
                continue

            thumbnail_url = snippet["thumbnails"].get(
                "high", snippet["thumbnails"].get("default", {})
            ).get("url", "")

            video_data.append({
                "id": video_id,
                "channel_id": channel_id,
                "channel_name": channel_name,
                "title": snippet["title"],
                "published_at": published_at,
                "thumbnail_url": thumbnail_url,
            })

        # Fetch durations for all videos in one API call
        video_ids = [v["id"] for v in video_data]
        details = get_video_details(video_ids) if video_ids else {}

        # Build Video objects with duration
        videos = []
        for v in video_data:
            duration = details.get(v["id"], {}).get("duration")
            videos.append(Video(
                id=v["id"],
                channel_id=v["channel_id"],
                channel_name=v["channel_name"],
                title=v["title"],
                published_at=v["published_at"],
                thumbnail_url=v["thumbnail_url"],
                video_url=f"https://www.youtube.com/watch?v={v['id']}",
                duration=duration,
            ))

        return videos

    except HttpError as e:
        logger.error(f"Error fetching uploads for channel {channel_id}: {e}")
        return []


def get_video_details(video_ids: list[str]) -> dict:
    """Get detailed metadata for multiple videos."""
    if not video_ids:
        return {}

    youtube = get_youtube_client()

    try:
        response = youtube.videos().list(
            part="snippet,contentDetails,statistics",
            id=",".join(video_ids)
        ).execute()

        return {
            item["id"]: {
                "title": item["snippet"]["title"],
                "description": item["snippet"]["description"],
                "duration": item["contentDetails"]["duration"],
                "view_count": item["statistics"].get("viewCount", 0),
            }
            for item in response.get("items", [])
        }

    except HttpError as e:
        logger.error(f"Error fetching video details: {e}")
        return {}


def parse_video_id(url: str) -> Optional[str]:
    """Extract a YouTube video ID from various URL formats.

    Supports:
        - https://www.youtube.com/watch?v=VIDEO_ID
        - https://youtu.be/VIDEO_ID
        - https://www.youtube.com/embed/VIDEO_ID
        - https://www.youtube.com/v/VIDEO_ID
        - https://youtube.com/shorts/VIDEO_ID

    Returns the video ID string, or None if the URL is not a recognized format.
    """
    if not url:
        return None

    parsed = urlparse(url)
    host = parsed.hostname or ""

    # Strip leading "www."
    if host.startswith("www."):
        host = host[4:]

    # youtu.be/VIDEO_ID
    if host == "youtu.be":
        video_id = parsed.path.lstrip("/").split("/")[0]
        return video_id if video_id else None

    # youtube.com variants
    if host in ("youtube.com", "m.youtube.com"):
        # /watch?v=VIDEO_ID
        if parsed.path == "/watch":
            qs = parse_qs(parsed.query)
            ids = qs.get("v", [])
            return ids[0] if ids else None

        # /embed/VIDEO_ID, /v/VIDEO_ID, /shorts/VIDEO_ID
        for prefix in ("/embed/", "/v/", "/shorts/"):
            if parsed.path.startswith(prefix):
                video_id = parsed.path[len(prefix):].split("/")[0]
                return video_id if video_id else None

    return None


def is_youtube_url(url: str) -> bool:
    """Check whether a URL is a recognized YouTube video URL."""
    return parse_video_id(url) is not None


def get_video_by_id(video_id: str) -> Optional[Video]:
    """Fetch metadata for a single video by its ID.

    Returns a Video object, or None if the video was not found.
    """
    youtube = get_youtube_client()

    try:
        response = youtube.videos().list(
            part="snippet,contentDetails",
            id=video_id,
        ).execute()

        items = response.get("items", [])
        if not items:
            return None

        item = items[0]
        snippet = item["snippet"]
        published_at = datetime.fromisoformat(
            snippet["publishedAt"].replace("Z", "+00:00")
        )
        thumbnail_url = snippet["thumbnails"].get(
            "high", snippet["thumbnails"].get("default", {})
        ).get("url", "")
        duration = item["contentDetails"].get("duration")

        return Video(
            id=video_id,
            channel_id=snippet["channelId"],
            channel_name=snippet["channelTitle"],
            title=snippet["title"],
            published_at=published_at,
            thumbnail_url=thumbnail_url,
            video_url=f"https://www.youtube.com/watch?v={video_id}",
            duration=duration,
        )

    except HttpError as e:
        logger.error(f"Error fetching video {video_id}: {e}")
        return None
