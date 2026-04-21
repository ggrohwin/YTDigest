"""MCP server exposing YouTube API functions as tools.

Wraps the youtube.py functions so any MCP client (Claude desktop, Cursor, etc.)
can query YouTube channels and video metadata conversationally.

Run directly:
    python mcp_servers/youtube_server.py

Or register with Claude desktop via claude_desktop_config.json.
"""

import sys
from pathlib import Path
from typing import Optional

import yaml

# Make src/ importable when running this file directly
_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from src.transcripts import fetch_transcript, fetch_transcript_with_timestamps
from src.youtube import get_channel_uploads, get_video_by_id, get_video_details

load_dotenv()


def _resolve_channel(
    channel_name: Optional[str], channel_id: Optional[str]
) -> tuple[str, str]:
    """Return (channel_id, channel_name) from whichever identifier was supplied."""
    if not channel_name and not channel_id:
        raise ValueError("Provide either channel_name or channel_id.")

    if channel_id:
        return channel_id, channel_name or ""

    config = yaml.safe_load((_ROOT / "config.yaml").read_text())
    for ch in config.get("channels", []):
        if ch.get("name", "").lower() == channel_name.lower():
            return ch["id"], ch["name"]

    raise ValueError(
        f"Channel '{channel_name}' not found in config.yaml. "
        "Try providing channel_id directly."
    )


mcp = FastMCP(
    "youtube",
    dependencies=[
        "google-api-python-client",
        "youtube-transcript-api",
        "python-dotenv",
        "pyyaml",
        "requests",
    ],
)


@mcp.tool()
def fetch_channel_videos(
    channel_name: Optional[str] = None,
    channel_id: Optional[str] = None,
    max_results: int = 5,
) -> list[dict]:
    """Fetch recent videos from a YouTube channel.

    Use this when the user asks what a channel has posted recently,
    wants to browse a channel's latest content, or asks for recent
    uploads from a specific creator.

    Provide either channel_name (e.g. "Andrej Karpathy") or channel_id
    (e.g. "UCPk8m_r6fkUSYmvgCBwq-sw"). If only channel_name is given,
    it is looked up in config.yaml.

    Args:
        channel_name: Human-readable channel name.
        channel_id: YouTube channel ID (starts with UC...).
        max_results: Maximum number of videos to return (default 5, max 50).

    Returns:
        List of videos with id, title, channel, published_at, duration, and url.
    """
    resolved_id, resolved_name = _resolve_channel(channel_name, channel_id)
    videos = get_channel_uploads(
        channel_id=resolved_id,
        channel_name=resolved_name,
        max_results=max_results,
    )
    return [
        {
            "id": v.id,
            "title": v.title,
            "channel": v.channel_name,
            "published_at": v.published_at.isoformat(),
            "duration": v.duration,
            "url": v.video_url,
            "thumbnail": v.thumbnail_url,
        }
        for v in videos
    ]


@mcp.tool()
def get_video_metadata(video_id: str) -> dict | None:
    """Get metadata for a single YouTube video by its ID.

    Use this when the user provides a video ID or YouTube URL and wants
    to know the title, channel, duration, publish date, or other details
    about that specific video.

    Args:
        video_id: The YouTube video ID (the part after ?v= in the URL).

    Returns:
        Video metadata dict, or None if the video was not found.
    """
    video = get_video_by_id(video_id)
    if not video:
        return None
    return {
        "id": video.id,
        "title": video.title,
        "channel": video.channel_name,
        "channel_id": video.channel_id,
        "published_at": video.published_at.isoformat(),
        "duration": video.duration,
        "url": video.video_url,
        "thumbnail": video.thumbnail_url,
    }


@mcp.tool()
def get_videos_metadata(video_ids: list[str]) -> dict[str, dict]:
    """Get metadata for multiple YouTube videos in a single API call.

    Use this when you have several video IDs and need details about all
    of them efficiently — more efficient than calling get_video_metadata
    once per video.

    Args:
        video_ids: List of YouTube video IDs.

    Returns:
        Dict mapping each video ID to its metadata (title, description,
        duration, view_count).
    """
    return get_video_details(video_ids)


@mcp.tool()
def get_video_transcript(video_id: str) -> dict:
    """Get the full plain-text transcript for a YouTube video.

    Use this when the user wants to know what was said in a video,
    asks for a summary of a video's content, or wants to find or
    quote something from a specific video.

    Args:
        video_id: The YouTube video ID (the part after ?v= in the URL).

    Returns:
        Dict with 'transcript' (full text) on success, or 'error' with
        'unavailable' (no captions exist) or 'failed' (temporary error).
    """
    transcript, error = fetch_transcript(video_id)
    if error:
        return {"error": error}
    return {"transcript": transcript.content}


@mcp.tool()
def get_video_transcript_with_timestamps(video_id: str) -> dict:
    """Get the transcript for a YouTube video with timestamps per segment.

    Use this instead of get_video_transcript when the user wants to know
    at what point in the video something was said, or needs to reference
    specific moments (e.g. 'where does he discuss backpropagation?').

    Args:
        video_id: The YouTube video ID (the part after ?v= in the URL).

    Returns:
        Dict with 'segments' (list of {text, start, duration}) on success,
        or 'error' if the transcript could not be fetched.
    """
    snippets = fetch_transcript_with_timestamps(video_id)
    if snippets is None:
        return {"error": "failed"}
    return {
        "segments": [
            {
                "text": s.text,
                "start": round(s.start, 1),
                "duration": round(s.duration, 1),
            }
            for s in snippets
        ]
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
