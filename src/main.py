import asyncio
import logging
import os
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


def load_config() -> AppConfig:
    """Load configuration from config.yaml."""
    config_path = BASE_DIR / "config.yaml"
    with open(config_path) as f:
        data = yaml.safe_load(f)
    return AppConfig(**data)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize app on startup."""
    global app_config
    await init_db()
    app_config = load_config()
    logger.info(f"Loaded {len(app_config.channels)} channels from config")
    yield


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
    """Fetch new videos from all configured channels."""
    if not app_config:
        return JSONResponse(
            content={"error": "Config not loaded"},
            status_code=500
        )

    try:
        published_after = datetime.now(timezone.utc) - timedelta(days=app_config.digest.max_age_days)
        total_videos = 0
        total_transcripts = 0
        total_summaries = 0

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

                existing_transcript = await get_transcript(video.id)
                if existing_transcript:
                    transcript = existing_transcript
                else:
                    logger.info(f"  Fetching transcript for: {video.title}")
                    transcript = fetch_transcript(video.id)
                    if transcript:
                        await save_transcript(transcript)
                        total_transcripts += 1
                    # Rate limit: wait between transcript requests to avoid YouTube blocking
                    await asyncio.sleep(3)

                if transcript:
                    existing_summary = await get_summary(video.id)
                    if not existing_summary:
                        logger.info(f"  Generating summary for: {video.title}")
                        summary = summarize_video(
                            video_id=video.id,
                            title=video.title,
                            channel=video.channel_name,
                            transcript=transcript.content
                        )
                        if summary:
                            await save_summary(summary)
                            total_summaries += 1

        return JSONResponse(content={
            "success": True,
            "videos_fetched": total_videos,
            "transcripts_fetched": total_transcripts,
            "summaries_generated": total_summaries,
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
