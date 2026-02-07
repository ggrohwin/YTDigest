import aiosqlite
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from .models import Article, ArticleSummary, Video, Transcript, Summary

DATABASE_PATH = Path(__file__).parent.parent / "data" / "ytdigest.db"


async def init_db() -> None:
    """Create database tables if they don't exist."""
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(DATABASE_PATH) as db:
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
            await db.execute("ALTER TABLE videos ADD COLUMN is_completed INTEGER DEFAULT 0")
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE videos ADD COLUMN sentiment TEXT")  # like, neutral, dislike
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE videos ADD COLUMN completed_at TEXT")
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
            await db.execute(
                "ALTER TABLE videos ADD COLUMN first_seen_at TEXT"
            )
        except Exception:
            pass

        await db.commit()


async def save_video(video: Video) -> bool:
    """Save a video to the database. Returns True if the video was new."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Check if video already exists
        cursor = await db.execute("SELECT id FROM videos WHERE id = ?", (video.id,))
        exists = await cursor.fetchone()

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
                (id, channel_id, channel_name, title, published_at, thumbnail_url, video_url, duration, first_seen_at)
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
        is_completed=bool(row["is_completed"]),
        sentiment=row["sentiment"],
        completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
    )


async def get_video(video_id: str) -> Optional[Video]:
    """Get a video by ID."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM videos WHERE id = ?", (video_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return _video_from_row(row)
    return None


async def get_videos_since(days: int, include_completed: bool = False) -> list[Video]:
    """Get all videos published within the specified number of days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        if include_completed:
            query = "SELECT * FROM videos WHERE published_at >= ? ORDER BY published_at DESC"
            params = (cutoff.isoformat(),)
        else:
            query = "SELECT * FROM videos WHERE published_at >= ? AND (is_completed = 0 OR is_completed IS NULL) ORDER BY published_at DESC"
            params = (cutoff.isoformat(),)
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [_video_from_row(row) for row in rows]


async def mark_video_completed(video_id: str, sentiment: str) -> None:
    """Mark a video as completed with the given sentiment (like, neutral, dislike)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            UPDATE videos
            SET is_completed = 1, sentiment = ?, completed_at = ?
            WHERE id = ?
            """,
            (sentiment, datetime.now(timezone.utc).isoformat(), video_id),
        )
        await db.commit()


async def save_transcript(transcript: Transcript) -> None:
    """Save a transcript to the database."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO summaries (video_id, summary, topics, category, generated_at)
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE videos SET transcript_status = ? WHERE id = ?",
            (status, video_id),
        )
        await db.commit()


async def get_videos_without_transcripts(days: int, limit: int = 1) -> list[Video]:
    """Get videos that are pending transcript fetch."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT v.* FROM videos v
            WHERE v.published_at >= ?
            AND (v.is_completed = 0 OR v.is_completed IS NULL)
            AND (v.transcript_status IS NULL OR v.transcript_status = 'pending' OR v.transcript_status = 'priority')
            ORDER BY CASE WHEN v.transcript_status = 'priority' THEN 0 ELSE 1 END,
                     v.published_at DESC
            LIMIT ?
            """,
            (cutoff.isoformat(), limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [_video_from_row(row) for row in rows]


async def get_videos_with_transcripts_without_summaries(days: int) -> list[Video]:
    """Get videos that have transcripts but no summaries yet."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    async with aiosqlite.connect(DATABASE_PATH) as db:
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def set_setting(key: str, value: str) -> None:
    """Set a setting value."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        await db.commit()


async def get_summaries_without_category() -> list[str]:
    """Get video IDs of summaries that don't have a category assigned."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT video_id FROM summaries WHERE category IS NULL"
        ) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


async def update_summary_category(video_id: str, category: str) -> None:
    """Update the category for an existing summary."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "UPDATE summaries SET category = ? WHERE video_id = ?",
            (category, video_id),
        )
        await db.commit()


async def count_new_videos_since(since: str) -> int:
    """Count videos first seen after the given ISO timestamp."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
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
        published_at=datetime.fromisoformat(row["published_at"]) if row["published_at"] else None,
        added_at=datetime.fromisoformat(row["added_at"]),
        content=row["content"],
        word_count=row["word_count"],
        extract_status=row["extract_status"],
        is_completed=bool(row["is_completed"]),
        sentiment=row["sentiment"],
        completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
    )


async def save_article(article: Article) -> bool:
    """Save an article to the database. Returns True if it was new."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("SELECT id FROM articles WHERE id = ?", (article.id,))
        exists = await cursor.fetchone()

        if exists:
            await db.execute(
                """
                UPDATE articles SET title = ?, content = ?, word_count = ?, extract_status = ?
                WHERE id = ?
                """,
                (article.title, article.content, article.word_count, article.extract_status, article.id),
            )
        else:
            await db.execute(
                """
                INSERT INTO articles
                (id, url, domain, title, author, published_at, added_at, content, word_count, extract_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    article.extract_status,
                ),
            )

        await db.commit()
        return not exists


async def get_article(article_id: str) -> Optional[Article]:
    """Get an article by ID."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM articles WHERE url = ?", (url,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return _article_from_row(row)
    return None


async def get_articles_since(days: int, include_completed: bool = False) -> list[Article]:
    """Get all articles added within the specified number of days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        if include_completed:
            query = "SELECT * FROM articles WHERE added_at >= ? ORDER BY added_at DESC"
            params = (cutoff.isoformat(),)
        else:
            query = "SELECT * FROM articles WHERE added_at >= ? AND (is_completed = 0 OR is_completed IS NULL) ORDER BY added_at DESC"
            params = (cutoff.isoformat(),)
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [_article_from_row(row) for row in rows]


async def save_article_summary(summary: ArticleSummary) -> None:
    """Save an article summary to the database."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO article_summaries (article_id, summary, topics, category, generated_at)
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
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
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            UPDATE articles
            SET is_completed = 1, sentiment = ?, completed_at = ?
            WHERE id = ?
            """,
            (sentiment, datetime.now(timezone.utc).isoformat(), article_id),
        )
        await db.commit()


async def get_articles_without_summaries() -> list[Article]:
    """Get articles that have content but no summaries yet."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT a.* FROM articles a
            LEFT JOIN article_summaries s ON a.id = s.article_id
            WHERE s.article_id IS NULL AND a.extract_status = 'extracted'
            ORDER BY a.added_at DESC
            """
        ) as cursor:
            rows = await cursor.fetchall()
            return [_article_from_row(row) for row in rows]
