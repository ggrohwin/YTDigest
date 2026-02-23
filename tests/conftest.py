"""Shared test fixtures for all test modules."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from src import database
from src.models import AppConfig, Article, ChannelConfig, DigestConfig, Summary, Video


@pytest.fixture
async def test_db(tmp_path, monkeypatch):
    """Create a temporary database for testing.

    Points database.DATABASE_PATH at a temp file, runs init_db() to create
    all tables, and yields the path. Every test that uses this fixture gets
    a fresh, empty database.
    """
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)
    await database.init_db()
    yield db_path


@pytest.fixture
async def test_client(test_db):
    """Async HTTP client wired directly to the FastAPI app.

    Uses httpx.AsyncClient with ASGITransport — requests flow through FastAPI's
    full routing/serialization stack but never touch the network.

    The real app lifespan calls YouTube API and spawns background tasks. We
    swap it with a minimal version that just sets app_config to a safe default.
    test_db already ran init_db() so the database is ready.
    """
    from src import main

    original_lifespan = main.app.router.lifespan_context

    @asynccontextmanager
    async def _test_lifespan(app):
        main.app_config = AppConfig(
            channels=[ChannelConfig(id="UC_test", name="Test Channel")],
            digest=DigestConfig(),
        )
        yield
        main.app_config = None

    main.app.router.lifespan_context = _test_lifespan
    try:
        transport = ASGITransport(app=main.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        main.app.router.lifespan_context = original_lifespan


# ---------------------------------------------------------------------------
# Seed helpers — plain async functions (not fixtures) so tests can call them
# with custom overrides when needed.
# ---------------------------------------------------------------------------


async def seed_video(
    id="vid_001",
    channel_id="UC_test",
    channel_name="Test Channel",
    title="Test Video",
    published_at=None,
    thumbnail_url="https://i.ytimg.com/vi/vid_001/hq.jpg",
    video_url="https://www.youtube.com/watch?v=vid_001",
    duration="PT10M30S",
) -> Video:
    """Insert a video into the test database and return it."""
    video = Video(
        id=id,
        channel_id=channel_id,
        channel_name=channel_name,
        title=title,
        published_at=published_at or datetime.now(timezone.utc),
        thumbnail_url=thumbnail_url,
        video_url=video_url,
        duration=duration,
    )
    await database.save_video(video)
    return video


async def seed_article(
    id="art_001",
    url="https://example.com/test-article",
    domain="example.com",
    title="Test Article",
    author="Jane Doe",
    added_at=None,
    content="This is the full content of the test article.",
    word_count=9,
) -> Article:
    """Insert an article into the test database and return it."""
    article = Article(
        id=id,
        url=url,
        domain=domain,
        title=title,
        author=author,
        added_at=added_at or datetime.now(timezone.utc),
        content=content,
        word_count=word_count,
        extract_status="extracted",
    )
    await database.save_article(article)
    return article


async def seed_video_summary(
    video_id="vid_001",
    summary="A great summary of this test video.",
    topics=None,
    category="Programming & Development",
) -> Summary:
    """Insert a video summary and return it."""
    s = Summary(
        video_id=video_id,
        summary=summary,
        topics=topics or ["python", "testing"],
        category=category,
        generated_at=datetime.now(timezone.utc),
    )
    await database.save_summary(s)
    return s
