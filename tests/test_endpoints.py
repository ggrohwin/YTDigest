"""Tests for HTTP endpoints.

Uses httpx.AsyncClient + ASGITransport to send real HTTP requests through
FastAPI's routing stack — without starting a server or touching the network.
"""

import pytest

from src import database
from src.models import ArticleSummary, Summary
from datetime import datetime, timezone

from tests.conftest import seed_article, seed_video, seed_video_summary


# ── POST /api/videos/{video_id}/complete ───────────────────────────────

class TestCompleteVideo:

    async def test_like(self, test_client):
        await seed_video(id="v1")
        resp = await test_client.post("/api/videos/v1/complete?sentiment=like")

        assert resp.status_code == 200
        assert resp.json()["success"] is True

        video = await database.get_video("v1")
        assert video.is_completed is True
        assert video.sentiment == "like"

    async def test_neutral(self, test_client):
        await seed_video(id="v2")
        resp = await test_client.post("/api/videos/v2/complete?sentiment=neutral")

        assert resp.status_code == 200
        video = await database.get_video("v2")
        assert video.sentiment == "neutral"

    async def test_dislike(self, test_client):
        await seed_video(id="v3")
        resp = await test_client.post("/api/videos/v3/complete?sentiment=dislike")

        assert resp.status_code == 200
        video = await database.get_video("v3")
        assert video.sentiment == "dislike"

    async def test_invalid_sentiment(self, test_client):
        await seed_video(id="v4")
        resp = await test_client.post("/api/videos/v4/complete?sentiment=love")

        assert resp.status_code == 400
        assert "Invalid sentiment" in resp.json()["error"]

    async def test_missing_sentiment(self, test_client):
        """FastAPI rejects the request when the required query param is absent."""
        await seed_video(id="v5")
        resp = await test_client.post("/api/videos/v5/complete")

        assert resp.status_code == 422


# ── POST /api/videos/{video_id}/prioritize ─────────────────────────────

class TestPrioritizeVideo:

    async def test_prioritize(self, test_client):
        await seed_video(id="v1")
        resp = await test_client.post("/api/videos/v1/prioritize")

        assert resp.status_code == 200
        assert resp.json()["success"] is True

        video = await database.get_video("v1")
        assert video.transcript_status == "priority"


# ── POST /api/videos/{video_id}/favorite ───────────────────────────────

class TestFavoriteVideo:

    async def test_toggle_on(self, test_client):
        await seed_video(id="v1")
        resp = await test_client.post("/api/videos/v1/favorite")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["is_favorited"] is True

    async def test_toggle_off(self, test_client):
        await seed_video(id="v1")
        await test_client.post("/api/videos/v1/favorite")  # on
        resp = await test_client.post("/api/videos/v1/favorite")  # off

        assert resp.status_code == 200
        assert resp.json()["is_favorited"] is False


# ── POST /api/articles/{article_id}/complete ───────────────────────────

class TestCompleteArticle:

    async def test_like(self, test_client):
        await seed_article(id="a1")
        resp = await test_client.post("/api/articles/a1/complete?sentiment=like")

        assert resp.status_code == 200
        assert resp.json()["success"] is True

    async def test_invalid_sentiment(self, test_client):
        await seed_article(id="a2")
        resp = await test_client.post("/api/articles/a2/complete?sentiment=love")

        assert resp.status_code == 400
        assert "Invalid sentiment" in resp.json()["error"]


# ── POST /api/articles/{article_id}/favorite ───────────────────────────

class TestFavoriteArticle:

    async def test_toggle_on(self, test_client):
        await seed_article(id="a1")
        resp = await test_client.post("/api/articles/a1/favorite")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["is_favorited"] is True

    async def test_toggle_off(self, test_client):
        await seed_article(id="a1")
        await test_client.post("/api/articles/a1/favorite")  # on
        resp = await test_client.post("/api/articles/a1/favorite")  # off

        assert resp.status_code == 200
        assert resp.json()["is_favorited"] is False


# ── GET /api/videos ────────────────────────────────────────────────────

class TestGetVideos:

    async def test_empty(self, test_client):
        resp = await test_client.get("/api/videos")

        assert resp.status_code == 200
        assert resp.json() == []

    async def test_with_summary(self, test_client):
        await seed_video(id="v1", title="My Great Video")
        await seed_video_summary(video_id="v1", topics=["python", "testing"])

        resp = await test_client.get("/api/videos")
        assert resp.status_code == 200

        data = resp.json()
        assert len(data) == 1
        v = data[0]
        assert v["id"] == "v1"
        assert v["title"] == "My Great Video"
        assert v["summary"] is not None
        assert v["topics"] == ["python", "testing"]
        assert v["has_transcript"] is False

    async def test_without_summary(self, test_client):
        await seed_video(id="v1")

        resp = await test_client.get("/api/videos")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["summary"] is None
        assert data[0]["topics"] == []


# ── GET /api/articles ──────────────────────────────────────────────────

class TestGetArticles:

    async def test_empty(self, test_client):
        resp = await test_client.get("/api/articles")

        assert resp.status_code == 200
        assert resp.json() == []

    async def test_with_data(self, test_client):
        await seed_article(id="a1", title="Great Article", author="Jane Doe")

        resp = await test_client.get("/api/articles")
        assert resp.status_code == 200

        data = resp.json()
        assert len(data) == 1
        a = data[0]
        assert a["id"] == "a1"
        assert a["title"] == "Great Article"
        assert a["author"] == "Jane Doe"
        assert a["domain"] == "example.com"
        assert "added_at" in a

    async def test_includes_completed(self, test_client):
        """GET /api/articles passes include_completed=True, so completed
        articles should still appear in the list."""
        await seed_article(id="a1")
        await database.mark_article_completed("a1", "like")

        resp = await test_client.get("/api/articles")
        data = resp.json()
        assert len(data) == 1


# ── GET / (index page) ────────────────────────────────────────────────

class TestIndex:

    async def test_returns_html(self, test_client):
        resp = await test_client.get("/")

        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "YTDigest" in resp.text

    async def test_shows_video(self, test_client):
        await seed_video(id="v1", title="Visible Video Title")

        resp = await test_client.get("/")
        assert resp.status_code == 200
        assert "Visible Video Title" in resp.text

    async def test_favorites_view(self, test_client):
        await seed_video(id="v1", title="Fav Video")
        await database.toggle_video_favorite("v1")

        resp = await test_client.get("/?view=favorites")
        assert resp.status_code == 200
        assert "Fav Video" in resp.text

    async def test_favorites_empty(self, test_client):
        resp = await test_client.get("/?view=favorites")

        assert resp.status_code == 200
        assert "No favorites yet" in resp.text
