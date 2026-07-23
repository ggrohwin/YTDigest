import asyncio
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import aiosqlite
import sentry_sdk

from .models import (
    Article,
    ArticleSummary,
    DigestItem,
    Embedding,
    Summary,
    Transcript,
    Video,
)

DATABASE_PATH = Path(__file__).parent.parent / "data" / "ytdigest.db"


@asynccontextmanager
async def traced_connect(op_name: str):
    """Open a DB connection wrapped in a Sentry span covering the whole operation."""
    with sentry_sdk.start_span(op="db", name=op_name) as span:
        span.set_data("db.system", "sqlite")
        async with aiosqlite.connect(DATABASE_PATH) as db:
            yield db


async def init_db() -> None:
    """Create database tables if they don't exist."""
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    async with traced_connect("init_db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id TEXT PRIMARY KEY,
                channel_id TEXT NOT NULL,
                channel_name TEXT NOT NULL,
                title TEXT NOT NULL,
                published_at TEXT NOT NULL,
                thumbnail_url TEXT NOT NULL,
                video_url TEXT NOT NULL,
                duration TEXT
            )
        """)

        # Migration: add duration column if it doesn't exist
        try:
            await db.execute("ALTER TABLE videos ADD COLUMN duration TEXT")
        except Exception:
            pass  # Column already exists

        # Migration: add transcript_status column if it doesn't exist
        # Values: 'pending', 'fetched', 'failed', 'unavailable'
        try:
            await db.execute(
                "ALTER TABLE videos ADD COLUMN transcript_status TEXT DEFAULT 'pending'"
            )
        except Exception:
            pass  # Column already exists

        # Migration: add completion tracking columns
        try:
            await db.execute(
                "ALTER TABLE videos ADD COLUMN is_completed INTEGER DEFAULT 0"
            )
        except Exception:
            pass
        try:
            await db.execute(
                "ALTER TABLE videos ADD COLUMN sentiment TEXT"
            )  # like, neutral, dislike
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE videos ADD COLUMN completed_at TEXT")
        except Exception:
            pass

        # Migration: add favorites tracking columns to videos
        try:
            await db.execute(
                "ALTER TABLE videos ADD COLUMN is_favorited INTEGER DEFAULT 0"
            )
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE videos ADD COLUMN favorited_at TEXT")
        except Exception:
            pass

        # Migration: add notes column to videos
        try:
            await db.execute("ALTER TABLE videos ADD COLUMN notes TEXT")
        except Exception:
            pass

        await db.execute("""
            CREATE TABLE IF NOT EXISTS transcripts (
                video_id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                FOREIGN KEY (video_id) REFERENCES videos(id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS summaries (
                video_id TEXT PRIMARY KEY,
                summary TEXT NOT NULL,
                topics TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                FOREIGN KEY (video_id) REFERENCES videos(id)
            )
        """)

        # Migration: add category column to summaries
        try:
            await db.execute("ALTER TABLE summaries ADD COLUMN category TEXT")
        except Exception:
            pass

        await db.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id TEXT PRIMARY KEY,
                url TEXT NOT NULL UNIQUE,
                domain TEXT NOT NULL,
                title TEXT NOT NULL,
                author TEXT,
                published_at TEXT,
                added_at TEXT NOT NULL,
                content TEXT NOT NULL,
                word_count INTEGER NOT NULL,
                extract_status TEXT DEFAULT 'pending',
                is_completed INTEGER DEFAULT 0,
                sentiment TEXT,
                completed_at TEXT
            )
        """)

        # Migration: add thumbnail_url column to articles
        try:
            await db.execute("ALTER TABLE articles ADD COLUMN thumbnail_url TEXT")
        except Exception:
            pass  # Column already exists

        # Migration: add favorites tracking columns to articles
        try:
            await db.execute(
                "ALTER TABLE articles ADD COLUMN is_favorited INTEGER DEFAULT 0"
            )
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE articles ADD COLUMN favorited_at TEXT")
        except Exception:
            pass

        # Migration: add notes column to articles
        try:
            await db.execute("ALTER TABLE articles ADD COLUMN notes TEXT")
        except Exception:
            pass

        await db.execute("""
            CREATE TABLE IF NOT EXISTS article_summaries (
                article_id TEXT PRIMARY KEY,
                summary TEXT NOT NULL,
                topics TEXT NOT NULL,
                category TEXT,
                generated_at TEXT NOT NULL,
                FOREIGN KEY (article_id) REFERENCES articles(id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        # Migration: add first_seen_at column
        try:
            await db.execute("ALTER TABLE videos ADD COLUMN first_seen_at TEXT")
        except Exception:
            pass

        await db.execute("""
            CREATE TABLE IF NOT EXISTS embeddings (
                item_id TEXT NOT NULL,
                item_type TEXT NOT NULL,
                content_type TEXT NOT NULL,
                vector BLOB NOT NULL,
                chunk_index INTEGER,
                UNIQUE(item_id, content_type, chunk_index)
            )
        """)

        await db.commit()


async def save_video(video: Video) -> bool:
    """Save a video to the database. Returns True if the video was new."""
    async with traced_connect("save_video") as db:
        # Check if video already exists
        cursor = await db.execute("SELECT id FROM videos WHERE id = ?", (video.id,))
        exists = await cursor.fetchone()

        # Widen the check-then-act window to make the TOCTOU race with
        # concurrent submissions of the same video reliably reproducible.
        await asyncio.sleep(3)

        if exists:
            # Update metadata only, preserve status fields
            await db.execute(
                """
                UPDATE videos SET title = ?, thumbnail_url = ?, duration = ?
                WHERE id = ?
                """,
                (video.title, video.thumbnail_url, video.duration, video.id),
            )
        else:
            await db.execute(
                """
                INSERT INTO videos
                (id, channel_id, channel_name, title,
                published_at, thumbnail_url, video_url,
                duration, first_seen_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    video.id,
                    video.channel_id,
                    video.channel_name,
                    video.title,
                    video.published_at.isoformat(),
                    video.thumbnail_url,
                    video.video_url,
                    video.duration,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

        await db.commit()
        return not exists


def _video_from_row(row) -> Video:
    """Helper to create a Video from a database row."""
    return Video(
        id=row["id"],
        channel_id=row["channel_id"],
        channel_name=row["channel_name"],
        title=row["title"],
        published_at=datetime.fromisoformat(row["published_at"]),
        thumbnail_url=row["thumbnail_url"],
        video_url=row["video_url"],
        duration=row["duration"],
        transcript_status=row["transcript_status"],
        first_seen_at=(
            datetime.fromisoformat(row["first_seen_at"])
            if row["first_seen_at"]
            else None
        ),
        is_completed=bool(row["is_completed"]),
        sentiment=row["sentiment"],
        completed_at=(
            datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None
        ),
        is_favorited=bool(row["is_favorited"]),
        favorited_at=(
            datetime.fromisoformat(row["favorited_at"]) if row["favorited_at"] else None
        ),
        notes=row["notes"],
    )


async def get_video(video_id: str) -> Optional[Video]:
    """Get a video by ID."""
    async with traced_connect("get_video") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM videos WHERE id = ?", (video_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return _video_from_row(row)
    return None


async def get_all_videos(include_completed: bool = False) -> list[Video]:
    """Get all videos in the database."""
    async with traced_connect("get_all_videos") as db:
        db.row_factory = aiosqlite.Row
        if include_completed:
            query = (
                "SELECT * FROM videos "
                "ORDER BY COALESCE(first_seen_at, published_at) DESC"
            )
        else:
            query = (
                "SELECT * FROM videos "
                "WHERE (is_completed = 0 "
                "OR is_completed IS NULL) "
                "ORDER BY COALESCE(first_seen_at, published_at) DESC"
            )
        async with db.execute(query) as cursor:
            rows = await cursor.fetchall()
            return [_video_from_row(row) for row in rows]


async def mark_video_completed(video_id: str, sentiment: str) -> None:
    """Mark a video as completed with the given sentiment (like, neutral, dislike)."""
    async with traced_connect("mark_video_completed") as db:
        await db.execute(
            """
            UPDATE videos
            SET is_completed = 1, sentiment = ?, completed_at = ?
            WHERE id = ?
            """,
            (sentiment, datetime.now(timezone.utc).isoformat(), video_id),
        )
        await db.commit()


async def uncomplete_video(video_id: str) -> None:
    """Un-complete a video, restoring it to active status."""
    async with traced_connect("uncomplete_video") as db:
        await db.execute(
            """
            UPDATE videos
            SET is_completed = 0, sentiment = NULL, completed_at = NULL
            WHERE id = ?
            """,
            (video_id,),
        )
        await db.commit()


def _parse_duration_minutes(iso_duration: str | None) -> float:
    """Parse ISO 8601 duration (e.g. 'PT5M30S') into total minutes as a float."""
    if not iso_duration:
        return 0.0
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso_duration)
    if not match:
        return 0.0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 60 + minutes + seconds / 60


async def get_engagement_stats(date_str: str | None = None) -> dict:
    """Get engagement stats, optionally filtered to a specific date.

    Returns counts of engaged vs skipped items and totals for
    minutes watched (videos) and words read (articles).
    """
    stats = {
        "videos_engaged": 0,
        "videos_skipped": 0,
        "articles_engaged": 0,
        "articles_skipped": 0,
        "total_minutes_watched": 0.0,
        "total_words_read": 0,
    }

    async with traced_connect("get_engagement_stats") as db:
        db.row_factory = aiosqlite.Row

        # --- Videos ---
        # Use DATE(completed_at, 'localtime') so UTC timestamps match the local date
        if date_str:
            video_query = (
                "SELECT sentiment, duration FROM videos "
                "WHERE is_completed = 1 "
                "AND DATE(completed_at, 'localtime') = ?"
            )
            video_params = (date_str,)
        else:
            video_query = (
                "SELECT sentiment, duration FROM videos WHERE is_completed = 1"
            )
            video_params = ()

        async with db.execute(video_query, video_params) as cursor:
            async for row in cursor:
                if row["sentiment"] == "skip":
                    stats["videos_skipped"] += 1
                else:
                    stats["videos_engaged"] += 1
                    stats["total_minutes_watched"] += _parse_duration_minutes(
                        row["duration"]
                    )

        # --- Articles ---
        if date_str:
            article_query = (
                "SELECT sentiment, word_count FROM articles "
                "WHERE is_completed = 1 "
                "AND DATE(completed_at, 'localtime') = ?"
            )
            article_params = (date_str,)
        else:
            article_query = (
                "SELECT sentiment, word_count FROM articles WHERE is_completed = 1"
            )
            article_params = ()

        async with db.execute(article_query, article_params) as cursor:
            async for row in cursor:
                if row["sentiment"] == "skip":
                    stats["articles_skipped"] += 1
                else:
                    stats["articles_engaged"] += 1
                    stats["total_words_read"] += row["word_count"] or 0

    return stats


async def save_transcript(transcript: Transcript) -> None:
    """Save a transcript to the database."""
    async with traced_connect("save_transcript") as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO transcripts (video_id, content, fetched_at)
            VALUES (?, ?, ?)
            """,
            (
                transcript.video_id,
                transcript.content,
                transcript.fetched_at.isoformat(),
            ),
        )
        await db.commit()


async def get_transcript(video_id: str) -> Optional[Transcript]:
    """Get a transcript by video ID."""
    async with traced_connect("get_transcript") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM transcripts WHERE video_id = ?", (video_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return Transcript(
                    video_id=row["video_id"],
                    content=row["content"],
                    fetched_at=datetime.fromisoformat(row["fetched_at"]),
                )
    return None


async def save_summary(summary: Summary) -> None:
    """Save a summary to the database."""
    async with traced_connect("save_summary") as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO summaries
            (video_id, summary, topics,
            category, generated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                summary.video_id,
                summary.summary,
                ",".join(summary.topics),
                summary.category,
                summary.generated_at.isoformat(),
            ),
        )
        await db.commit()


async def get_summary(video_id: str) -> Optional[Summary]:
    """Get a summary by video ID."""
    async with traced_connect("get_summary") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM summaries WHERE video_id = ?", (video_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return Summary(
                    video_id=row["video_id"],
                    summary=row["summary"],
                    topics=row["topics"].split(",") if row["topics"] else [],
                    category=row["category"],
                    generated_at=datetime.fromisoformat(row["generated_at"]),
                )
    return None


async def update_transcript_status(video_id: str, status: str) -> None:
    """Update the transcript fetch status for a video.

    Status values: 'pending', 'fetched', 'failed', 'unavailable', 'priority'
    """
    async with traced_connect("update_transcript_status") as db:
        await db.execute(
            "UPDATE videos SET transcript_status = ? WHERE id = ?",
            (status, video_id),
        )
        await db.commit()


async def get_videos_without_transcripts(limit: int = 1) -> list[Video]:
    """Get videos that are pending transcript fetch."""
    async with traced_connect("get_videos_without_transcripts") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT v.* FROM videos v
            WHERE (v.is_completed = 0 OR v.is_completed IS NULL)
            AND (v.transcript_status IS NULL
                 OR v.transcript_status = 'pending'
                 OR v.transcript_status = 'priority')
            ORDER BY CASE WHEN v.transcript_status = 'priority' THEN 0 ELSE 1 END,
                     v.published_at DESC
            LIMIT ?
            """,
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [_video_from_row(row) for row in rows]


async def get_videos_with_transcripts_without_summaries(days: int) -> list[Video]:
    """Get videos that have transcripts but no summaries yet."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    async with traced_connect("get_videos_with_transcripts_without_summaries") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT v.* FROM videos v
            INNER JOIN transcripts t ON v.id = t.video_id
            LEFT JOIN summaries s ON v.id = s.video_id
            WHERE v.published_at >= ? AND s.video_id IS NULL
            ORDER BY v.published_at DESC
            """,
            (cutoff.isoformat(),),
        ) as cursor:
            rows = await cursor.fetchall()
            return [_video_from_row(row) for row in rows]


async def get_setting(key: str) -> Optional[str]:
    """Get a setting value by key."""
    async with traced_connect("get_setting") as db:
        async with db.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def set_setting(key: str, value: str) -> None:
    """Set a setting value."""
    async with traced_connect("set_setting") as db:
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        await db.commit()


async def get_summaries_without_category() -> list[str]:
    """Get video IDs of summaries that don't have a category assigned."""
    async with traced_connect("get_summaries_without_category") as db:
        async with db.execute(
            "SELECT video_id FROM summaries WHERE category IS NULL"
        ) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


async def update_summary_category(video_id: str, category: str) -> None:
    """Update the category for an existing summary."""
    async with traced_connect("update_summary_category") as db:
        await db.execute(
            "UPDATE summaries SET category = ? WHERE video_id = ?",
            (category, video_id),
        )
        await db.commit()


async def count_new_videos_since(since: str) -> int:
    """Count videos first seen after the given ISO timestamp."""
    async with traced_connect("count_new_videos_since") as db:
        async with db.execute(
            "SELECT COUNT(*) FROM videos WHERE first_seen_at > ?",
            (since,),
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


# --- Article operations ---


def _article_from_row(row) -> Article:
    """Helper to create an Article from a database row."""
    return Article(
        id=row["id"],
        url=row["url"],
        domain=row["domain"],
        title=row["title"],
        author=row["author"],
        published_at=(
            datetime.fromisoformat(row["published_at"]) if row["published_at"] else None
        ),
        added_at=datetime.fromisoformat(row["added_at"]),
        content=row["content"],
        word_count=row["word_count"],
        thumbnail_url=row["thumbnail_url"],
        extract_status=row["extract_status"],
        is_completed=bool(row["is_completed"]),
        sentiment=row["sentiment"],
        completed_at=(
            datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None
        ),
        is_favorited=bool(row["is_favorited"]),
        favorited_at=(
            datetime.fromisoformat(row["favorited_at"]) if row["favorited_at"] else None
        ),
        notes=row["notes"],
    )


async def save_article(article: Article) -> bool:
    """Save an article to the database. Returns True if it was new."""
    async with traced_connect("save_article") as db:
        cursor = await db.execute("SELECT id FROM articles WHERE id = ?", (article.id,))
        exists = await cursor.fetchone()

        if exists:
            await db.execute(
                """
                UPDATE articles
                SET title = ?, content = ?,
                word_count = ?, extract_status = ?,
                thumbnail_url = ?
                WHERE id = ?
                """,
                (
                    article.title,
                    article.content,
                    article.word_count,
                    article.extract_status,
                    article.thumbnail_url,
                    article.id,
                ),
            )
        else:
            await db.execute(
                """
                INSERT INTO articles
                (id, url, domain, title, author,
                published_at, added_at, content,
                word_count, thumbnail_url,
                extract_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    article.id,
                    article.url,
                    article.domain,
                    article.title,
                    article.author,
                    article.published_at.isoformat() if article.published_at else None,
                    article.added_at.isoformat(),
                    article.content,
                    article.word_count,
                    article.thumbnail_url,
                    article.extract_status,
                ),
            )

        await db.commit()
        return not exists


async def get_article(article_id: str) -> Optional[Article]:
    """Get an article by ID."""
    async with traced_connect("get_article") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM articles WHERE id = ?", (article_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return _article_from_row(row)
    return None


async def get_article_by_url(url: str) -> Optional[Article]:
    """Get an article by its URL."""
    async with traced_connect("get_article_by_url") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM articles WHERE url = ?", (url,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return _article_from_row(row)
    return None


async def get_all_articles(include_completed: bool = False) -> list[Article]:
    """Get all articles in the database."""
    async with traced_connect("get_all_articles") as db:
        db.row_factory = aiosqlite.Row
        if include_completed:
            query = "SELECT * FROM articles ORDER BY added_at DESC"
        else:
            query = (
                "SELECT * FROM articles "
                "WHERE (is_completed = 0 "
                "OR is_completed IS NULL) "
                "ORDER BY added_at DESC"
            )
        async with db.execute(query) as cursor:
            rows = await cursor.fetchall()
            return [_article_from_row(row) for row in rows]


async def save_article_summary(summary: ArticleSummary) -> None:
    """Save an article summary to the database."""
    async with traced_connect("save_article_summary") as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO article_summaries
            (article_id, summary, topics,
            category, generated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                summary.article_id,
                summary.summary,
                ",".join(summary.topics),
                summary.category,
                summary.generated_at.isoformat(),
            ),
        )
        await db.commit()


async def get_article_summary(article_id: str) -> Optional[ArticleSummary]:
    """Get an article summary by article ID."""
    async with traced_connect("get_article_summary") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM article_summaries WHERE article_id = ?", (article_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return ArticleSummary(
                    article_id=row["article_id"],
                    summary=row["summary"],
                    topics=row["topics"].split(",") if row["topics"] else [],
                    category=row["category"],
                    generated_at=datetime.fromisoformat(row["generated_at"]),
                )
    return None


async def mark_article_completed(article_id: str, sentiment: str) -> None:
    """Mark an article as completed with the given sentiment."""
    async with traced_connect("mark_article_completed") as db:
        await db.execute(
            """
            UPDATE articles
            SET is_completed = 1, sentiment = ?, completed_at = ?
            WHERE id = ?
            """,
            (sentiment, datetime.now(timezone.utc).isoformat(), article_id),
        )
        await db.commit()


async def uncomplete_article(article_id: str) -> None:
    """Un-complete an article, restoring it to active status."""
    async with traced_connect("uncomplete_article") as db:
        await db.execute(
            """
            UPDATE articles
            SET is_completed = 0, sentiment = NULL, completed_at = NULL
            WHERE id = ?
            """,
            (article_id,),
        )
        await db.commit()


async def toggle_video_favorite(video_id: str) -> bool:
    """Toggle the favorite status of a video. Returns the new is_favorited state."""
    async with traced_connect("toggle_video_favorite") as db:
        async with db.execute(
            "SELECT is_favorited FROM videos WHERE id = ?", (video_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return False
            currently_favorited = bool(row[0])

        new_state = not currently_favorited
        if new_state:
            await db.execute(
                "UPDATE videos SET is_favorited = 1, favorited_at = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), video_id),
            )
        else:
            await db.execute(
                "UPDATE videos SET is_favorited = 0, favorited_at = NULL WHERE id = ?",
                (video_id,),
            )
        await db.commit()
        return new_state


async def toggle_article_favorite(article_id: str) -> bool:
    """Toggle the favorite status of an article. Returns the new is_favorited state."""
    async with traced_connect("toggle_article_favorite") as db:
        async with db.execute(
            "SELECT is_favorited FROM articles WHERE id = ?", (article_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return False
            currently_favorited = bool(row[0])

        new_state = not currently_favorited
        if new_state:
            await db.execute(
                "UPDATE articles SET is_favorited = 1, favorited_at = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), article_id),
            )
        else:
            await db.execute(
                "UPDATE articles SET is_favorited = 0, "
                "favorited_at = NULL WHERE id = ?",
                (article_id,),
            )
        await db.commit()
        return new_state


async def save_video_notes(video_id: str, notes: str) -> None:
    """Save notes for a video. Empty string clears the notes."""
    async with traced_connect("save_video_notes") as db:
        await db.execute(
            "UPDATE videos SET notes = ? WHERE id = ?",
            (notes or None, video_id),
        )
        await db.commit()


async def save_article_notes(article_id: str, notes: str) -> None:
    """Save notes for an article. Empty string clears the notes."""
    async with traced_connect("save_article_notes") as db:
        await db.execute(
            "UPDATE articles SET notes = ? WHERE id = ?",
            (notes or None, article_id),
        )
        await db.commit()


async def get_favorite_videos() -> list[Video]:
    """Get all favorited videos, ordered by most recently favorited."""
    async with traced_connect("get_favorite_videos") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM videos WHERE is_favorited = 1 ORDER BY favorited_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [_video_from_row(row) for row in rows]


async def get_favorite_articles() -> list[Article]:
    """Get all favorited articles, ordered by most recently favorited."""
    async with traced_connect("get_favorite_articles") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM articles WHERE is_favorited = 1 ORDER BY favorited_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [_article_from_row(row) for row in rows]


async def get_articles_without_summaries() -> list[Article]:
    """Get articles that have content but no summaries yet."""
    async with traced_connect("get_articles_without_summaries") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT a.* FROM articles a
            LEFT JOIN article_summaries s ON a.id = s.article_id
            WHERE s.article_id IS NULL AND a.extract_status = 'extracted'
            ORDER BY a.added_at DESC
            """) as cursor:
            rows = await cursor.fetchall()
            return [_article_from_row(row) for row in rows]


async def get_digest_item(item_id: str, item_type: str) -> Optional[DigestItem]:
    """Load a single video or article as a DigestItem (with summary data)."""
    if item_type == "video":
        video = await get_video(item_id)
        if not video:
            return None
        summary = await get_summary(item_id)
        return DigestItem(
            item_type="video",
            id=video.id,
            title=video.title,
            url=video.video_url,
            source_name=video.channel_name,
            published_at=video.published_at,
            added_at=video.first_seen_at,
            is_completed=video.is_completed,
            sentiment=video.sentiment,
            completed_at=video.completed_at,
            is_favorited=video.is_favorited,
            favorited_at=video.favorited_at,
            summary=summary.summary if summary else None,
            topics=summary.topics if summary else [],
            category=summary.category if summary else None,
            notes=video.notes,
            thumbnail_url=video.thumbnail_url,
            duration=video.duration,
            transcript_status=video.transcript_status,
        )
    else:
        article = await get_article(item_id)
        if not article:
            return None
        summary = await get_article_summary(item_id)
        return DigestItem(
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
            is_favorited=article.is_favorited,
            favorited_at=article.favorited_at,
            summary=summary.summary if summary else None,
            topics=summary.topics if summary else [],
            category=summary.category if summary else None,
            notes=article.notes,
            thumbnail_url=article.thumbnail_url,
            author=article.author,
            domain=article.domain,
            word_count=article.word_count,
            original_published_at=article.published_at,
        )


# --- Embedding operations ---


async def save_embedding(embedding: Embedding, vector_bytes: bytes) -> None:
    """Save an embedding to the database.

    vector_bytes is the pre-serialized numpy array (via embedding_to_bytes).
    We take bytes rather than doing the conversion here so that database.py
    stays free of numpy dependency.
    """
    async with traced_connect("save_embedding") as db:
        # SQLite treats NULL != NULL for UNIQUE constraints, so
        # INSERT OR REPLACE won't match rows with chunk_index IS NULL.
        # Delete first, then insert to handle both cases.
        if embedding.chunk_index is not None:
            await db.execute(
                "DELETE FROM embeddings "
                "WHERE item_id = ? "
                "AND content_type = ? "
                "AND chunk_index = ?",
                (embedding.item_id, embedding.content_type, embedding.chunk_index),
            )
        else:
            await db.execute(
                "DELETE FROM embeddings "
                "WHERE item_id = ? "
                "AND content_type = ? "
                "AND chunk_index IS NULL",
                (embedding.item_id, embedding.content_type),
            )
        await db.execute(
            """
            INSERT INTO embeddings
            (item_id, item_type, content_type, vector, chunk_index)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                embedding.item_id,
                embedding.item_type,
                embedding.content_type,
                vector_bytes,
                embedding.chunk_index,
            ),
        )
        await db.commit()


async def get_embedding(
    item_id: str, content_type: str, chunk_index: Optional[int] = None
) -> Optional[tuple[Embedding, bytes]]:
    """Get an embedding by item ID and content type.

    Returns (Embedding, raw_vector_bytes) or None.
    """
    async with traced_connect("get_embedding") as db:
        db.row_factory = aiosqlite.Row
        if chunk_index is not None:
            query = (
                "SELECT * FROM embeddings "
                "WHERE item_id = ? "
                "AND content_type = ? "
                "AND chunk_index = ?"
            )
            params = (item_id, content_type, chunk_index)
        else:
            query = (
                "SELECT * FROM embeddings "
                "WHERE item_id = ? "
                "AND content_type = ? "
                "AND chunk_index IS NULL"
            )
            params = (item_id, content_type)
        async with db.execute(query, params) as cursor:
            row = await cursor.fetchone()
            if row:
                emb = Embedding(
                    item_id=row["item_id"],
                    item_type=row["item_type"],
                    content_type=row["content_type"],
                    vector=[],  # caller will deserialize from bytes
                    chunk_index=row["chunk_index"],
                )
                return emb, bytes(row["vector"])
    return None


async def get_all_embeddings() -> list[tuple[Embedding, bytes]]:
    """Get all embeddings from the database.

    Returns list of (Embedding, raw_vector_bytes) tuples.
    """
    results = []
    async with traced_connect("get_all_embeddings") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM embeddings") as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                emb = Embedding(
                    item_id=row["item_id"],
                    item_type=row["item_type"],
                    content_type=row["content_type"],
                    vector=[],
                    chunk_index=row["chunk_index"],
                )
                results.append((emb, bytes(row["vector"])))
    return results


async def get_all_tags_with_counts() -> list[tuple[str, int]]:
    """Return all distinct tags sorted most-frequent first.

    Used to initialize the TagNormalizer cache at app startup.
    """
    from collections import Counter

    counts: Counter = Counter()
    async with traced_connect("get_all_tags_with_counts") as db:
        async with db.execute(
            "SELECT topics FROM summaries WHERE topics != ''"
        ) as cursor:
            async for row in cursor:
                for t in row[0].split(","):
                    t = t.strip().title()
                    if t:
                        counts[t] += 1
        async with db.execute(
            "SELECT topics FROM article_summaries WHERE topics != ''"
        ) as cursor:
            async for row in cursor:
                for t in row[0].split(","):
                    t = t.strip().title()
                    if t:
                        counts[t] += 1
    return counts.most_common()


async def has_embeddings() -> bool:
    """Check whether any embeddings exist in the database."""
    async with traced_connect("has_embeddings") as db:
        async with db.execute("SELECT COUNT(*) FROM embeddings") as cursor:
            row = await cursor.fetchone()
            return row[0] > 0


async def count_embeddings() -> int:
    """Count total embeddings in the database."""
    async with traced_connect("count_embeddings") as db:
        async with db.execute("SELECT COUNT(*) FROM embeddings") as cursor:
            row = await cursor.fetchone()
            return row[0]


async def get_items_without_embeddings() -> list[tuple[str, str]]:
    """Get (item_id, item_type) pairs for items with summaries but no embeddings.

    This finds videos with summaries and articles with
    article_summaries that don't yet have a corresponding
    row in the embeddings table.
    """
    results = []
    async with traced_connect("get_items_without_embeddings") as db:
        # Videos with summaries but no summary embedding
        async with db.execute("""
            SELECT s.video_id FROM summaries s
            LEFT JOIN embeddings e
                ON s.video_id = e.item_id AND e.content_type = 'video_summary'
            WHERE e.item_id IS NULL
            """) as cursor:
            for row in await cursor.fetchall():
                results.append((row[0], "video"))

        # Articles with summaries but no summary embedding
        async with db.execute("""
            SELECT s.article_id FROM article_summaries s
            LEFT JOIN embeddings e
                ON s.article_id = e.item_id AND e.content_type = 'article_summary'
            WHERE e.item_id IS NULL
            """) as cursor:
            for row in await cursor.fetchall():
                results.append((row[0], "article"))

    return results


async def get_summary_text_for_embedding(item_id: str, item_type: str) -> Optional[str]:
    """Get the summary text to embed for a given item.

    Combines the summary text with topics to create a richer embedding.
    Returns None if no summary exists.
    """
    async with traced_connect("get_summary_text_for_embedding") as db:
        db.row_factory = aiosqlite.Row
        if item_type == "video":
            async with db.execute(
                "SELECT summary, topics FROM summaries WHERE video_id = ?",
                (item_id,),
            ) as cursor:
                row = await cursor.fetchone()
        else:
            async with db.execute(
                "SELECT summary, topics FROM article_summaries WHERE article_id = ?",
                (item_id,),
            ) as cursor:
                row = await cursor.fetchone()

        if not row:
            return None

        summary = row["summary"]
        topics = row["topics"]
        if topics:
            summary += f"\n\nTopics: {topics}"
        return summary


async def save_embeddings_batch(
    embeddings: list[tuple[Embedding, bytes]],
) -> None:
    """Save multiple embeddings in a single transaction.

    Used for chunk embeddings where one item produces many vectors.
    Replaces any existing chunks for the same item and content_type.
    """
    if not embeddings:
        return

    async with traced_connect("save_embeddings_batch") as db:
        # Delete old chunks for this item+content_type first
        first_emb = embeddings[0][0]
        await db.execute(
            "DELETE FROM embeddings WHERE item_id = ? AND content_type = ?",
            (first_emb.item_id, first_emb.content_type),
        )

        for emb, vector_bytes in embeddings:
            await db.execute(
                """
                INSERT INTO embeddings
                (item_id, item_type, content_type, vector, chunk_index)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    emb.item_id,
                    emb.item_type,
                    emb.content_type,
                    vector_bytes,
                    emb.chunk_index,
                ),
            )
        await db.commit()


async def get_items_without_chunk_embeddings() -> list[tuple[str, str]]:
    """Get (item_id, item_type) pairs for items without chunk embeddings.

    Videos must have a transcript; articles must have content.
    """
    results = []
    async with traced_connect("get_items_without_chunk_embeddings") as db:
        # Videos with transcripts but no chunk embeddings
        async with db.execute("""
            SELECT t.video_id FROM transcripts t
            LEFT JOIN embeddings e
                ON t.video_id = e.item_id AND e.content_type = 'video_chunk'
            WHERE e.item_id IS NULL
            """) as cursor:
            for row in await cursor.fetchall():
                results.append((row[0], "video"))

        # Articles with content but no chunk embeddings
        async with db.execute("""
            SELECT a.id FROM articles a
            LEFT JOIN embeddings e
                ON a.id = e.item_id AND e.content_type = 'article_chunk'
            WHERE e.item_id IS NULL AND a.extract_status = 'extracted'
            """) as cursor:
            for row in await cursor.fetchall():
                results.append((row[0], "article"))

    return results


async def get_full_text_for_embedding(item_id: str, item_type: str) -> Optional[str]:
    """Get the full text (transcript or article content) for chunk embedding."""
    async with traced_connect("get_full_text_for_embedding") as db:
        if item_type == "video":
            async with db.execute(
                "SELECT content FROM transcripts WHERE video_id = ?",
                (item_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None
        else:
            async with db.execute(
                "SELECT content FROM articles WHERE id = ?",
                (item_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None
