import logging
from datetime import datetime, timezone
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from typing import Optional

import requests
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)

from .models import Transcript

logger = logging.getLogger("ytdigest")

# Path to cookies file for bypassing IP bans
COOKIES_PATH = Path(__file__).parent.parent / "cookies.txt"


def _create_api_client() -> YouTubeTranscriptApi:
    """Create YouTubeTranscriptApi with cookies if available."""
    if COOKIES_PATH.exists():
        logger.info(f"Using cookies from {COOKIES_PATH}")
        session = requests.Session()
        cookie_jar = MozillaCookieJar(str(COOKIES_PATH))
        cookie_jar.load(ignore_discard=True, ignore_expires=True)
        session.cookies = cookie_jar
        return YouTubeTranscriptApi(http_client=session)
    return YouTubeTranscriptApi()


_ytt_api = _create_api_client()


def fetch_transcript(video_id: str) -> Optional[Transcript]:
    """
    Fetch the transcript for a YouTube video.

    Returns None if transcript is not available.
    """
    try:
        transcript_list = _ytt_api.fetch(video_id)

        full_text = " ".join(
            snippet.text for snippet in transcript_list
        )

        full_text = " ".join(full_text.split())

        return Transcript(
            video_id=video_id,
            content=full_text,
            fetched_at=datetime.now(timezone.utc)
        )

    except NoTranscriptFound:
        logger.warning(f"No transcript found for video {video_id}")
        return None
    except TranscriptsDisabled:
        logger.warning(f"Transcripts disabled for video {video_id}")
        return None
    except VideoUnavailable:
        logger.warning(f"Video {video_id} is unavailable")
        return None
    except Exception as e:
        logger.error(f"Error fetching transcript for {video_id}: {e}")
        return None


def fetch_transcript_with_timestamps(video_id: str) -> Optional[list]:
    """
    Fetch the transcript with timestamps for a YouTube video.

    Returns list of FetchedTranscriptSnippet objects with text, start time, and duration.
    """
    try:
        return _ytt_api.fetch(video_id)
    except Exception as e:
        logger.error(f"Error fetching transcript for {video_id}: {e}")
        return None
