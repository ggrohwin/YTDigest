import aiosqlite
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from .models import Video, Transcript, Summary

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

        await db.commit()


async def save_video(video: Video) -> None:
    """Save a video to the database."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO videos
            (id, channel_id, channel_name, title, published_at, thumbnail_url, video_url, duration)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
            ),
        )
        await db.commit()


async def get_video(video_id: str) -> Optional[Video]:
    """Get a video by ID."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM videos WHERE id = ?", (video_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return Video(
                    id=row["id"],
                    channel_id=row["channel_id"],
                    channel_name=row["channel_name"],
                    title=row["title"],
                    published_at=datetime.fromisoformat(row["published_at"]),
                    thumbnail_url=row["thumbnail_url"],
                    video_url=row["video_url"],
                    duration=row["duration"],
                )
    return None


async def get_videos_since(days: int) -> list[Video]:
    """Get all videos published within the specified number of days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM videos WHERE published_at >= ? ORDER BY published_at DESC",
            (cutoff.isoformat(),),
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                Video(
                    id=row["id"],
                    channel_id=row["channel_id"],
                    channel_name=row["channel_name"],
                    title=row["title"],
                    published_at=datetime.fromisoformat(row["published_at"]),
                    thumbnail_url=row["thumbnail_url"],
                    video_url=row["video_url"],
                    duration=row["duration"],
                )
                for row in rows
            ]


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
            INSERT OR REPLACE INTO summaries (video_id, summary, topics, generated_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                summary.video_id,
                summary.summary,
                ",".join(summary.topics),
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
                    generated_at=datetime.fromisoformat(row["generated_at"]),
                )
    return None
