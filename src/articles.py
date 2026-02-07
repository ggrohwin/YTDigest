import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import trafilatura

from .models import Article

logger = logging.getLogger("ytdigest")


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
        downloaded = trafilatura.fetch_url(url)
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
        )

        if not result or not result.get("text"):
            return None, "Could not extract article content"

        content = result["text"]
        title = result.get("title") or "Untitled"
        author = result.get("author")
        pub_date = None
        if result.get("date"):
            try:
                pub_date = datetime.fromisoformat(result["date"])
                if pub_date.tzinfo is None:
                    pub_date = pub_date.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                pass

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
            extract_status="extracted",
        )

        return article, None

    except Exception as e:
        logger.error(f"Error fetching article from {url}: {e}")
        return None, str(e)
