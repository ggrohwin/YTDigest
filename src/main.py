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
from fastapi.middleware.cors import CORSMiddleware
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
    save_article,
    get_article_by_url,
    get_articles_since,
    save_article_summary,
    get_article_summary,
    mark_article_completed,
    get_items_without_embeddings,
    get_summary_text_for_embedding,
)
from collections import defaultdict, Counter
from .models import AppConfig, CATEGORIES, DigestItem, VideoWithDetails
from .youtube import get_channel_uploads
from .transcripts import fetch_transcript
from .summarizer import summarize_video, summarize_article, classify_existing_summary
from .articles import fetch_article
from . import embedder

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
    grouped_items: list[tuple[str, list]],
    all_items: list[DigestItem],
) -> list[tuple[str, list[tuple[str, int]]]]:
    """Group topic entries by category for the sidebar hierarchy.

    Determines each topic's category by majority vote of the categories
    assigned to items in that topic group. Returns a list of
    (category_label, [(topic_label, item_count), ...]) tuples ordered
    by the CATEGORIES list, with "Uncategorized" last.
    """
    # Build a lookup: item_id -> category
    cat_lookup: dict[str, str] = {}
    for item in all_items:
        if item.category:
            cat_lookup[item.id] = item.category

    categories: dict[str, list[tuple[str, int]]] = {}
    for topic_label, items in grouped_items:
        # Determine category by majority vote
        cats = [cat_lookup.get(item.id, "Uncategorized") for item in items]
        most_common = Counter(cats).most_common(1)
        category = most_common[0][0] if most_common else "Uncategorized"
        if category not in categories:
            categories[category] = []
        categories[category].append((topic_label, len(items)))

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

# CORS middleware — needed for the bookmarklet which POSTs from arbitrary domains
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, group_by: str = "date", show_completed: bool = False):
    """Render the main digest page."""
    items = await get_digest_items(include_completed=show_completed)
    grouped = group_items(items, group_by)
    month_groups = build_month_hierarchy(grouped) if group_by == "date" else None
    category_groups = build_category_hierarchy(grouped, items) if group_by == "topic" else None

    # Compute live summary counts from already-loaded items
    total = len(items)
    with_summary = sum(1 for item in items if item.summary)
    pending = sum(1 for item in items if item.item_type == "video" and item.transcript_status in (None, "pending", "priority"))
    failed = sum(1 for item in items if item.item_type == "video" and item.transcript_status == "failed")

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
            "grouped_items": grouped,
            "group_by": group_by,
            "show_completed": show_completed,
            "page_summary": page_summary,
            "channels": app_config.channels if app_config else [],
            "month_groups": month_groups,
            "category_groups": category_groups,
            "bookmarklet_origin": f"{request.url.scheme}://{request.url.netloc}",
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


@app.post("/api/embed-all")
async def api_embed_all():
    """Generate embeddings for all items that have summaries but no embeddings."""
    if not embedder.is_available():
        return JSONResponse(
            content={"error": "VOYAGE_API_KEY is not set"},
            status_code=400,
        )

    try:
        items = await get_items_without_embeddings()
        embedded = 0
        errors = 0

        for item_id, item_type in items:
            text = await get_summary_text_for_embedding(item_id, item_type)
            if not text:
                errors += 1
                continue

            success = await embedder.embed_item(item_id, item_type, text)
            if success:
                embedded += 1
                logger.info(f"Embedded {item_type} {item_id}")
            else:
                errors += 1

        return JSONResponse(content={
            "success": True,
            "total": len(items),
            "embedded": embedded,
            "errors": errors,
        })
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error(f"Error during embedding backfill: {error_msg}")
        return JSONResponse(
            content={"error": error_msg},
            status_code=500,
        )


@app.post("/api/articles")
async def api_add_article(request: Request):
    """Add a web article by URL. Extracts content, saves, and generates summary."""
    try:
        body = await request.json()
        url = body.get("url")
        if not url:
            return JSONResponse(
                content={"error": "URL is required"},
                status_code=400,
            )

        # Check for duplicates
        existing = await get_article_by_url(url)
        if existing:
            summary = await get_article_summary(existing.id)
            return JSONResponse(content={
                "success": True,
                "duplicate": True,
                "article_id": existing.id,
                "title": existing.title,
                "summary": summary.summary if summary else None,
            })

        # Extract article content
        article, error = fetch_article(url)
        if not article:
            return JSONResponse(
                content={"error": f"Failed to extract article: {error}"},
                status_code=400,
            )

        # Save article
        await save_article(article)

        # Generate summary
        summary = summarize_article(
            article_id=article.id,
            title=article.title,
            domain=article.domain,
            content=article.content,
            author=article.author,
        )
        if summary:
            await save_article_summary(summary)

        return JSONResponse(content={
            "success": True,
            "duplicate": False,
            "article_id": article.id,
            "title": article.title,
            "domain": article.domain,
            "word_count": article.word_count,
            "summary": summary.summary if summary else None,
        })

    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error(f"Error adding article: {error_msg}")
        return JSONResponse(
            content={"error": error_msg},
            status_code=500,
        )


@app.post("/api/articles/{article_id}/complete")
async def api_complete_article(article_id: str, sentiment: str):
    """Mark an article as completed with the given sentiment."""
    if sentiment not in ("like", "neutral", "dislike"):
        return JSONResponse(
            content={"error": "Invalid sentiment. Must be: like, neutral, dislike"},
            status_code=400,
        )

    try:
        await mark_article_completed(article_id, sentiment)
        return JSONResponse(content={"success": True})
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error(f"Error marking article complete: {error_msg}")
        return JSONResponse(
            content={"error": error_msg},
            status_code=500,
        )


@app.get("/api/articles")
async def api_articles():
    """Get all articles with their summaries as JSON."""
    if not app_config:
        return JSONResponse(content=[])

    articles = await get_articles_since(app_config.digest.max_age_days, include_completed=True)
    result = []
    for article in articles:
        summary = await get_article_summary(article.id)
        result.append({
            "id": article.id,
            "title": article.title,
            "url": article.url,
            "domain": article.domain,
            "author": article.author,
            "word_count": article.word_count,
            "added_at": article.added_at.isoformat(),
            "summary": summary.summary if summary else None,
            "topics": summary.topics if summary else [],
        })
    return JSONResponse(content=result)


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


async def get_digest_items(include_completed: bool = False) -> list[DigestItem]:
    """Get all recent videos and articles as a unified list of DigestItems."""
    if not app_config:
        return []

    items: list[DigestItem] = []

    # Load videos
    videos = await get_videos_since(app_config.digest.max_age_days, include_completed=include_completed)
    for video in videos:
        transcript = await get_transcript(video.id)
        summary = await get_summary(video.id)
        items.append(DigestItem(
            item_type="video",
            id=video.id,
            title=video.title,
            url=video.video_url,
            source_name=video.channel_name,
            published_at=video.published_at,
            is_completed=video.is_completed,
            sentiment=video.sentiment,
            completed_at=video.completed_at,
            summary=summary.summary if summary else None,
            topics=summary.topics if summary else [],
            category=summary.category if summary else None,
            thumbnail_url=video.thumbnail_url,
            duration=video.duration,
            transcript_status=video.transcript_status,
        ))

    # Load articles
    articles = await get_articles_since(app_config.digest.max_age_days, include_completed=include_completed)
    for article in articles:
        summary = await get_article_summary(article.id)
        items.append(DigestItem(
            item_type="article",
            id=article.id,
            title=article.title,
            url=article.url,
            source_name=article.domain,
            published_at=article.added_at,
            added_at=article.added_at,
            is_completed=article.is_completed,
            sentiment=article.sentiment,
            completed_at=article.completed_at,
            summary=summary.summary if summary else None,
            topics=summary.topics if summary else [],
            category=summary.category if summary else None,
            thumbnail_url=article.thumbnail_url,
            author=article.author,
            domain=article.domain,
            word_count=article.word_count,
            original_published_at=article.published_at,
        ))

    # Sort by date, most recent first
    items.sort(key=lambda x: x.published_at, reverse=True)
    return items


def group_items(
    items: list[DigestItem], group_by: str
) -> list[tuple[str, list[DigestItem]]]:
    """Group digest items by the specified field.

    Returns list of (group_name, items) tuples, sorted appropriately.
    """
    if group_by == "channel":
        groups = defaultdict(list)
        for item in items:
            groups[item.source_name].append(item)
        # Sort groups alphabetically by source name
        return sorted(groups.items(), key=lambda x: x[0].lower())

    elif group_by == "topic":
        groups = defaultdict(list)
        for item in items:
            if item.topics:
                for topic in item.topics:
                    groups[topic].append(item)
            else:
                groups["No topics"].append(item)
        # Sort groups alphabetically, "No topics" last
        return sorted(groups.items(), key=lambda x: (x[0] == "No topics", x[0].lower()))

    else:  # Default: group by date
        groups = defaultdict(list)
        for item in items:
            date_str = item.published_at.strftime("%B %d, %Y")
            groups[date_str].append(item)
        # Sort groups by date (most recent first) using the max date in each group
        return sorted(
            groups.items(),
            key=lambda x: max(item.published_at for item in x[1]),
            reverse=True
        )
