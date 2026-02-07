from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict

CATEGORIES: list[str] = [
    "AI & Machine Learning",
    "Programming & Development",
    "Cloud & Infrastructure",
    "Security & Privacy",
    "Data & Analytics",
    "News & Industry",
    "Tools & Productivity",
    "Career & Education",
    "Other",
]


class ChannelConfig(BaseModel):
    id: str
    name: str


class DigestConfig(BaseModel):
    max_videos_per_channel: int = 5
    max_age_days: int = 7
    transcript_fetch_interval: int = 180  # seconds between background fetches
    transcript_batch_size: int = 1  # transcripts to fetch per cycle
    video_refresh_interval: int = 3600  # seconds between video metadata refreshes


class AppConfig(BaseModel):
    channels: list[ChannelConfig]
    digest: DigestConfig


class Video(BaseModel):
    id: str
    channel_id: str
    channel_name: str
    title: str
    published_at: datetime
    thumbnail_url: str
    video_url: str
    duration: Optional[str] = None  # ISO 8601 duration (e.g., "PT15M33S")
    transcript_status: Optional[str] = None  # pending, fetched, failed, unavailable, priority
    is_completed: bool = False
    sentiment: Optional[str] = None  # like, neutral, dislike
    completed_at: Optional[datetime] = None


class Transcript(BaseModel):
    video_id: str
    content: str
    fetched_at: datetime


class Summary(BaseModel):
    video_id: str
    summary: str
    topics: list[str]
    category: Optional[str] = None
    generated_at: datetime


class VideoWithDetails(BaseModel):
    video: Video
    transcript: Optional[Transcript] = None
    summary: Optional[Summary] = None


class Article(BaseModel):
    id: str  # SHA-256 hash of URL, 12 chars
    url: str
    domain: str
    title: str
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    added_at: datetime
    content: str
    word_count: int
    thumbnail_url: Optional[str] = None
    extract_status: Literal["pending", "extracted", "failed"] = "pending"
    is_completed: bool = False
    sentiment: Optional[str] = None
    completed_at: Optional[datetime] = None


class ArticleSummary(BaseModel):
    article_id: str
    summary: str
    topics: list[str]
    category: Optional[str] = None
    generated_at: datetime


class DigestItem(BaseModel):
    item_type: Literal["video", "article"]
    id: str
    title: str
    url: str
    source_name: str  # channel_name for videos, domain for articles
    published_at: datetime
    added_at: Optional[datetime] = None
    is_completed: bool = False
    sentiment: Optional[str] = None
    completed_at: Optional[datetime] = None
    # Summary fields (shared)
    summary: Optional[str] = None
    topics: list[str] = []
    category: Optional[str] = None
    # Video-specific
    thumbnail_url: Optional[str] = None
    duration: Optional[str] = None
    transcript_status: Optional[str] = None
    # Article-specific
    author: Optional[str] = None
    domain: Optional[str] = None
    word_count: Optional[int] = None
    original_published_at: Optional[datetime] = None


class Embedding(BaseModel):
    """A vector embedding for semantic search.

    Each embedding links a vector (list of floats) to a source item.
    content_type distinguishes summary-level vs chunk-level embeddings.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    item_id: str  # video ID or article ID
    item_type: Literal["video", "article"]
    content_type: Literal[
        "video_summary", "article_summary",
        "video_chunk", "article_chunk",
    ]
    vector: list[float]
    chunk_index: Optional[int] = None  # which chunk (None for summaries)


class SearchResult(BaseModel):
    """A digest item with a relevance score from semantic search."""
    item: DigestItem
    score: float  # cosine similarity, 0.0 to 1.0
