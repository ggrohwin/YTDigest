import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import requests
import trafilatura

from .models import Article

logger = logging.getLogger("ytdigest")

_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def generate_article_id(url: str) -> str:
    """Generate a deterministic 12-char ID from a URL using SHA-256."""
    return hashlib.sha256(url.encode()).hexdigest()[:12]


def extract_domain(url: str) -> str:
    """Extract the domain from a URL, stripping the www. prefix."""
    hostname = urlparse(url).hostname or ""
    if hostname.startswith("www."):
        hostname = hostname[4:]
    return hostname


def fetch_article(url: str) -> tuple[Optional[Article], Optional[str]]:
    """Download a page and extract its content via trafilatura.

    Returns (Article, None) on success, or (None, error_message) on failure.
    """
    try:
        # Use requests directly so REQUESTS_CA_BUNDLE env var is honoured
        # (trafilatura.fetch_url builds its own session and may bypass it).
        response = requests.get(url, headers=_FETCH_HEADERS, timeout=30)
        response.raise_for_status()
        downloaded = response.text
        if not downloaded:
            return None, "Failed to download page"

        metadata = trafilatura.extract(
            downloaded,
            output_format="txt",
            include_comments=False,
            include_tables=True,
            with_metadata=True,
            only_with_metadata=False,
        )

        if not metadata:
            return None, "Could not extract article content"

        # trafilatura returns plain text when output_format="txt" and with_metadata=True
        # We need to call bare_extraction for structured metadata
        result = trafilatura.bare_extraction(
            downloaded,
            include_comments=False,
            include_tables=True,
            with_metadata=True,
        )

        if not result or not getattr(result, "text", None):
            return None, "Could not extract article content"

        content = result.text
        title = getattr(result, "title", None) or "Untitled"
        author = getattr(result, "author", None)
        pub_date = None
        if getattr(result, "date", None):
            try:
                pub_date = datetime.fromisoformat(result.date)
                if pub_date.tzinfo is None:
                    pub_date = pub_date.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                pass

        image = getattr(result, "image", None)

        article = Article(
            id=generate_article_id(url),
            url=url,
            domain=extract_domain(url),
            title=title,
            author=author,
            published_at=pub_date,
            added_at=datetime.now(timezone.utc),
            content=content,
            word_count=len(content.split()),
            thumbnail_url=image,
            extract_status="extracted",
        )

        return article, None

    except Exception as e:
        logger.error(f"Error fetching article from {url}: {e}")
        return None, str(e)
