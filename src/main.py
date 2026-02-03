import asyncio
import logging
import os
import random
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

# Configure logging with timestamps
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("ytdigest")

from .database import (
    init_db,
    save_video,
    save_transcript,
    save_summary,
    get_transcript,
    get_summary,
    get_videos_since,
    get_videos_without_transcripts,
    get_videos_with_transcripts_without_summaries,
    update_transcript_status,
)
from .models import AppConfig, VideoWithDetails
from .youtube import get_channel_uploads
from .transcripts import fetch_transcript
from .summarizer import summarize_video

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def format_duration(iso_duration: str | None) -> str:
    """Convert ISO 8601 duration (e.g., PT15M33S) to human-readable format (15:33)."""
    if not iso_duration:
        return ""

    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso_duration)
    if not match:
        return ""

    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)

    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


templates.env.filters["format_duration"] = format_duration

app_config: AppConfig | None = None
background_tasks: list[asyncio.Task] = []


def load_config() -> AppConfig:
    """Load configuration from config.yaml."""
    config_path = BASE_DIR / "config.yaml"
    with open(config_path) as f:
        data = yaml.safe_load(f)
    return AppConfig(**data)


async def background_transcript_fetcher():
    """Background task that gradually fetches transcripts to avoid rate limiting."""
    logger.info("Background transcript fetcher started")

    while True:
        try:
            if not app_config:
                await asyncio.sleep(10)
                continue

            # Add jitter (-1 to +2 minutes) to appear less bot-like
            jitter = random.randint(-60, 120)
            wait_time = app_config.digest.transcript_fetch_interval + jitter
            logger.debug(f"[Background] Waiting {wait_time}s before next fetch")
            await asyncio.sleep(wait_time)

            # Find videos that need transcripts
            videos = await get_videos_without_transcripts(
                days=app_config.digest.max_age_days,
                limit=app_config.digest.transcript_batch_size
            )

            if not videos:
                logger.debug("No videos need transcripts")
                continue

            for video in videos:
                logger.info(f"[Background] Fetching transcript for: {video.title}")
                transcript = fetch_transcript(video.id)

                if transcript:
                    await save_transcript(transcript)
                    await update_transcript_status(video.id, "fetched")
                    logger.info(f"[Background] Transcript saved for: {video.title}")

                    # Also generate summary immediately if we got a transcript
                    logger.info(f"[Background] Generating summary for: {video.title}")
                    summary = summarize_video(
                        video_id=video.id,
                        title=video.title,
                        channel=video.channel_name,
                        transcript=transcript.content
                    )
                    if summary:
                        await save_summary(summary)
                        logger.info(f"[Background] Summary saved for: {video.title}")
                else:
                    # Mark as failed so we don't keep retrying the same video
                    await update_transcript_status(video.id, "failed")
                    logger.warning(f"[Background] Could not fetch transcript for: {video.title} - marked as failed")

        except asyncio.CancelledError:
            logger.info("Background transcript fetcher stopped")
            raise
        except Exception as e:
            logger.error(f"[Background] Error in transcript fetcher: {e}")
            # Continue running despite errors


async def refresh_video_metadata() -> tuple[int, int]:
    """Fetch video metadata from all channels and generate pending summaries.

    Returns tuple of (videos_fetched, summaries_generated).
    """
    if not app_config:
        return 0, 0

    published_after = datetime.now(timezone.utc) - timedelta(days=app_config.digest.max_age_days)
    total_videos = 0
    total_summaries = 0

    # Fetch video metadata from all channels
    for channel in app_config.channels:
        logger.info(f"Fetching videos from {channel.name}...")
        videos = get_channel_uploads(
            channel_id=channel.id,
            channel_name=channel.name,
            max_results=app_config.digest.max_videos_per_channel,
            published_after=published_after
        )
        for video in videos:
            await save_video(video)
            total_videos += 1

    # Generate summaries for videos that have transcripts but no summaries
    videos_needing_summaries = await get_videos_with_transcripts_without_summaries(
        days=app_config.digest.max_age_days
    )
    for video in videos_needing_summaries:
        transcript = await get_transcript(video.id)
        if transcript:
            logger.info(f"Generating summary for: {video.title}")
            summary = summarize_video(
                video_id=video.id,
                title=video.title,
                channel=video.channel_name,
                transcript=transcript.content
            )
            if summary:
                await save_summary(summary)
                total_summaries += 1

    return total_videos, total_summaries


async def background_video_fetcher():
    """Background task that periodically refreshes video metadata."""
    logger.info("Background video fetcher started")

    while True:
        try:
            if not app_config:
                await asyncio.sleep(10)
                continue

            await asyncio.sleep(app_config.digest.video_refresh_interval)

            logger.info("[Background] Refreshing video metadata...")
            videos_fetched, summaries_generated = await refresh_video_metadata()
            logger.info(f"[Background] Fetched {videos_fetched} videos, generated {summaries_generated} summaries")

        except asyncio.CancelledError:
            logger.info("Background video fetcher stopped")
            raise
        except Exception as e:
            logger.error(f"[Background] Error in video fetcher: {e}")
            # Continue running despite errors


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize app on startup."""
    global app_config, background_tasks
    await init_db()
    app_config = load_config()
    logger.info(f"Loaded {len(app_config.channels)} channels from config")

    # Start background tasks
    background_tasks = [
        asyncio.create_task(background_transcript_fetcher()),
        asyncio.create_task(background_video_fetcher()),
    ]

    yield

    # Stop all background tasks on shutdown
    for task in background_tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="YTDigest", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the main digest page."""
    videos = await get_videos_with_details()
    return templates.TemplateResponse(
        "digest.html",
        {
            "request": request,
            "videos": videos,
            "channels": app_config.channels if app_config else [],
        }
    )


@app.get("/api/videos")
async def api_videos():
    """Get all videos with their summaries as JSON."""
    videos = await get_videos_with_details()
    return JSONResponse(content=[
        {
            "id": v.video.id,
            "title": v.video.title,
            "channel_name": v.video.channel_name,
            "published_at": v.video.published_at.isoformat(),
            "thumbnail_url": v.video.thumbnail_url,
            "video_url": v.video.video_url,
            "summary": v.summary.summary if v.summary else None,
            "topics": v.summary.topics if v.summary else [],
            "has_transcript": v.transcript is not None,
        }
        for v in videos
    ])


@app.get("/api/refresh")
async def api_refresh():
    """Fetch new videos from all configured channels.

    This only fetches video metadata and generates summaries for videos
    that already have transcripts. Transcript fetching is handled by
    the background task to avoid YouTube rate limiting.
    """
    if not app_config:
        return JSONResponse(
            content={"error": "Config not loaded"},
            status_code=500
        )

    try:
        total_videos, total_summaries = await refresh_video_metadata()

        # Count pending transcripts for user feedback
        pending_transcripts = await get_videos_without_transcripts(
            days=app_config.digest.max_age_days,
            limit=100
        )

        return JSONResponse(content={
            "success": True,
            "videos_fetched": total_videos,
            "summaries_generated": total_summaries,
            "transcripts_pending": len(pending_transcripts),
        })
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error(f"Error during refresh: {error_msg}")
        logger.exception("Traceback:")
        return JSONResponse(
            content={"error": error_msg},
            status_code=500
        )


async def get_videos_with_details() -> list[VideoWithDetails]:
    """Get all recent videos with their transcripts and summaries."""
    if not app_config:
        return []

    videos = await get_videos_since(app_config.digest.max_age_days)

    result = []
    for video in videos:
        transcript = await get_transcript(video.id)
        summary = await get_summary(video.id)
        result.append(VideoWithDetails(
            video=video,
            transcript=transcript,
            summary=summary
        ))

    return result
