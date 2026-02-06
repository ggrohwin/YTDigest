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
    mark_video_completed,
    get_summaries_without_category,
    update_summary_category,
    count_new_videos_since,
    get_setting,
    set_setting,
)
from collections import defaultdict, Counter
from .models import AppConfig, CATEGORIES, VideoWithDetails
from .youtube import get_channel_uploads
from .transcripts import fetch_transcript
from .summarizer import summarize_video, classify_existing_summary

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def slugify(value: str) -> str:
    """Convert a string to a valid HTML id (lowercase, hyphens, no special chars)."""
    value = value.lower().strip()
    value = re.sub(r"[^\w\s-]", "", value)
    value = re.sub(r"[\s_]+", "-", value)
    value = re.sub(r"-+", "-", value)
    return value.strip("-")


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
templates.env.filters["slugify"] = slugify

def build_month_hierarchy(
    grouped_videos: list[tuple[str, list]],
) -> list[tuple[str, list[tuple[str, int]]]]:
    """Group date entries by month+year for the sidebar hierarchy.

    Takes the output of group_videos when group_by == "date" and returns
    a list of (month_label, [(date_label, video_count), ...]) tuples.
    """
    months: dict[str, list[tuple[str, int]]] = {}
    for date_label, videos in grouped_videos:
        # Parse the date label (e.g. "February 04, 2026") to extract month+year
        try:
            parsed = datetime.strptime(date_label, "%B %d, %Y")
            month_label = parsed.strftime("%B %Y")
        except ValueError:
            month_label = "Other"
        if month_label not in months:
            months[month_label] = []
        months[month_label].append((date_label, len(videos)))
    return list(months.items())


def build_category_hierarchy(
    grouped_videos: list[tuple[str, list]],
    all_videos: list,
) -> list[tuple[str, list[tuple[str, int]]]]:
    """Group topic entries by category for the sidebar hierarchy.

    Determines each topic's category by majority vote of the categories
    assigned to videos in that topic group. Returns a list of
    (category_label, [(topic_label, video_count), ...]) tuples ordered
    by the CATEGORIES list, with "Uncategorized" last.
    """
    # Build a lookup: video_id -> category
    cat_lookup: dict[str, str] = {}
    for v in all_videos:
        if v.summary and v.summary.category:
            cat_lookup[v.video.id] = v.summary.category

    categories: dict[str, list[tuple[str, int]]] = {}
    for topic_label, videos in grouped_videos:
        # Determine category by majority vote
        cats = [cat_lookup.get(v.video.id, "Uncategorized") for v in videos]
        most_common = Counter(cats).most_common(1)
        category = most_common[0][0] if most_common else "Uncategorized"
        if category not in categories:
            categories[category] = []
        categories[category].append((topic_label, len(videos)))

    # Order by CATEGORIES list, then "Uncategorized" last
    ordered: list[tuple[str, list[tuple[str, int]]]] = []
    for cat in CATEGORIES:
        if cat in categories:
            ordered.append((cat, categories.pop(cat)))
    # Any remaining (e.g. "Uncategorized")
    for cat in sorted(categories.keys()):
        ordered.append((cat, categories[cat]))

    return ordered


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
                transcript, failure_reason = fetch_transcript(video.id)

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
                    # Mark with appropriate status based on failure reason
                    status = failure_reason or "failed"
                    await update_transcript_status(video.id, status)
                    logger.warning(f"[Background] Could not fetch transcript for: {video.title} - marked as {status}")

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
        logger.info(f"Querying videos from {channel.name}...")
        videos = get_channel_uploads(
            channel_id=channel.id,
            channel_name=channel.name,
            max_results=app_config.digest.max_videos_per_channel,
            published_after=published_after
        )
        new_count = 0
        for video in videos:
            is_new = await save_video(video)
            if is_new:
                total_videos += 1
                new_count += 1
                logger.info(f"    + {video.title}")
        logger.info(f"  {channel.name}: {new_count} new videos found and added to database")

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

    # Fetch latest videos on startup
    logger.info("Fetching videos on startup...")
    videos_fetched, summaries_generated = await refresh_video_metadata()
    logger.info(f"Startup: fetched {videos_fetched} new videos, generated {summaries_generated} summaries")

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
async def index(request: Request, group_by: str = "date", show_completed: bool = False):
    """Render the main digest page."""
    videos = await get_videos_with_details(include_completed=show_completed)
    grouped = group_videos(videos, group_by)
    month_groups = build_month_hierarchy(grouped) if group_by == "date" else None
    category_groups = build_category_hierarchy(grouped, videos) if group_by == "topic" else None

    # Compute live summary counts from already-loaded videos
    total = len(videos)
    with_summary = sum(1 for v in videos if v.summary)
    pending = sum(1 for v in videos if v.video.transcript_status in (None, "pending", "priority"))
    failed = sum(1 for v in videos if v.video.transcript_status == "failed")

    # Count new videos since last visit, then update the timestamp
    last_visited = await get_setting("last_visited_at")
    new_since_last_visit = await count_new_videos_since(last_visited) if last_visited else 0
    await set_setting("last_visited_at", datetime.now(timezone.utc).isoformat())

    page_summary = {
        "total": total,
        "with_summary": with_summary,
        "pending": pending,
        "failed": failed,
        "new_since_last_visit": new_since_last_visit,
    }

    return templates.TemplateResponse(
        "digest.html",
        {
            "request": request,
            "grouped_videos": grouped,
            "group_by": group_by,
            "show_completed": show_completed,
            "page_summary": page_summary,
            "channels": app_config.channels if app_config else [],
            "month_groups": month_groups,
            "category_groups": category_groups,
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


@app.post("/api/videos/{video_id}/complete")
async def api_complete_video(video_id: str, sentiment: str):
    """Mark a video as completed with the given sentiment (like, neutral, dislike)."""
    if sentiment not in ("like", "neutral", "dislike"):
        return JSONResponse(
            content={"error": "Invalid sentiment. Must be: like, neutral, dislike"},
            status_code=400
        )

    try:
        await mark_video_completed(video_id, sentiment)
        return JSONResponse(content={"success": True})
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error(f"Error marking video complete: {error_msg}")
        return JSONResponse(
            content={"error": error_msg},
            status_code=500
        )


@app.post("/api/videos/{video_id}/prioritize")
async def api_prioritize_video(video_id: str):
    """Mark a video as priority so the background fetcher processes it next."""
    try:
        await update_transcript_status(video_id, "priority")
        return JSONResponse(content={"success": True})
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error(f"Error prioritizing video: {error_msg}")
        return JSONResponse(
            content={"error": error_msg},
            status_code=500
        )


@app.post("/api/backfill-categories")
async def api_backfill_categories():
    """Classify existing summaries that don't have a category assigned."""
    try:
        video_ids = await get_summaries_without_category()
        updated = 0
        errors = 0

        for video_id in video_ids:
            summary = await get_summary(video_id)
            if not summary:
                errors += 1
                continue

            category = classify_existing_summary(summary.summary, summary.topics)
            if category:
                await update_summary_category(video_id, category)
                updated += 1
            else:
                errors += 1

        return JSONResponse(content={
            "success": True,
            "total": len(video_ids),
            "updated": updated,
            "errors": errors,
        })
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error(f"Error during category backfill: {error_msg}")
        return JSONResponse(
            content={"error": error_msg},
            status_code=500,
        )


async def get_videos_with_details(include_completed: bool = False) -> list[VideoWithDetails]:
    """Get all recent videos with their transcripts and summaries."""
    if not app_config:
        return []

    videos = await get_videos_since(app_config.digest.max_age_days, include_completed=include_completed)

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


def group_videos(
    videos: list[VideoWithDetails], group_by: str
) -> list[tuple[str, list[VideoWithDetails]]]:
    """Group videos by the specified field.

    Returns list of (group_name, videos) tuples, sorted appropriately.
    """
    if group_by == "channel":
        groups = defaultdict(list)
        for v in videos:
            groups[v.video.channel_name].append(v)
        # Sort groups alphabetically by channel name
        return sorted(groups.items(), key=lambda x: x[0].lower())

    elif group_by == "topic":
        groups = defaultdict(list)
        for v in videos:
            if v.summary and v.summary.topics:
                for topic in v.summary.topics:
                    groups[topic].append(v)
            else:
                groups["No topics"].append(v)
        # Sort groups alphabetically, "No topics" last
        return sorted(groups.items(), key=lambda x: (x[0] == "No topics", x[0].lower()))

    else:  # Default: group by date
        groups = defaultdict(list)
        for v in videos:
            date_str = v.video.published_at.strftime("%B %d, %Y")
            groups[date_str].append(v)
        # Sort groups by date (most recent first) using the max date in each group
        return sorted(
            groups.items(),
            key=lambda x: max(v.video.published_at for v in x[1]),
            reverse=True
        )
