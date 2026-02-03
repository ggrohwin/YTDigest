from datetime import datetime
from typing import Optional
from pydantic import BaseModel


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


class Transcript(BaseModel):
    video_id: str
    content: str
    fetched_at: datetime


class Summary(BaseModel):
    video_id: str
    summary: str
    topics: list[str]
    generated_at: datetime


class VideoWithDetails(BaseModel):
    video: Video
    transcript: Optional[Transcript] = None
    summary: Optional[Summary] = None
