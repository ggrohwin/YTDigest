"""One-off backfill for items stuck in 'Summary pending...' (YTD-80 / YTD-81).

Does NOT import src.main (avoids sentry_sdk.init() / polluting Sentry with
one-off script noise, same convention as scripts/probe_channels.py).

Reuses the app's own functions so behavior matches the real pipeline exactly:
summarize_content() -> save_summary()/save_article_summary() -> embed_item().

For videos, queries for transcript-without-summary directly (unbounded by
age) rather than via get_videos_with_transcripts_without_summaries(days=...),
since that's the max_age_days windowing bug tracked as YTD-80 - a video that
aged out of that window is exactly what this script exists to catch. For
articles, get_articles_without_summaries() is already unbounded (YTD-81:
it's just never called from the running app).

Run from repo root with the project venv:
    .venv\\Scripts\\python scripts\\backfill_summaries.py
"""

import asyncio
import os

import aiosqlite
import yaml
from dotenv import load_dotenv

from src import embedder
from src.database import (
    DATABASE_PATH,
    get_all_tags_with_counts,
    get_articles_without_summaries,
    get_transcript,
    get_video,
    save_article_summary,
    save_summary,
)
from src.summarizer import initialize_tag_normalizer, summarize_content

load_dotenv(dotenv_path=os.path.join(os.getcwd(), ".env"))

with open("config.yaml") as f:
    MODEL = yaml.safe_load(f)["digest"]["summarization_model"]


async def get_video_ids_with_transcript_missing_summary() -> list[str]:
    """Any video with a saved transcript but no summary, regardless of age."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("""
            SELECT t.video_id FROM transcripts t
            LEFT JOIN summaries s ON s.video_id = t.video_id
            WHERE s.video_id IS NULL
            """) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


async def backfill_video(video_id: str) -> None:
    video = await get_video(video_id)
    transcript = await get_transcript(video_id)
    if not video or not transcript:
        print(f"[video {video_id}] missing video or transcript row, skipping")
        return

    print(f"[video] Generating summary for: {video.title}")
    summary = summarize_content(
        item_id=video.id,
        title=video.title,
        source_name=video.channel_name,
        content=transcript.content,
        content_type="video",
        model=MODEL,
    )
    if not summary:
        print(f"[video] FAILED (see log for reason): {video.title}")
        return

    await save_summary(summary)
    print(f"[video] Summary saved: {video.title}")

    if embedder.is_available():
        text = summary.summary
        if summary.topics:
            text += f"\n\nTopics: {','.join(summary.topics)}"
        await embedder.embed_item(video.id, "video", text)
        await embedder.embed_item_chunks(video.id, "video", transcript.content)
        print(f"[video] Embeddings saved: {video.title}")


async def backfill_articles() -> None:
    articles = await get_articles_without_summaries()
    print(f"[articles] {len(articles)} article(s) need a summary")

    for article in articles:
        print(f"[article] Generating summary for: {article.title}")
        summary = summarize_content(
            item_id=article.id,
            title=article.title,
            source_name=article.domain,
            content=article.content,
            content_type="article",
            author=article.author,
            model=MODEL,
        )
        if not summary:
            print(f"[article] FAILED (see log for reason): {article.title}")
            continue

        await save_article_summary(summary)
        print(f"[article] Summary saved: {article.title}")

        if embedder.is_available():
            text = summary.summary
            if summary.topics:
                text += f"\n\nTopics: {','.join(summary.topics)}"
            await embedder.embed_item(article.id, "article", text)
            await embedder.embed_item_chunks(article.id, "article", article.content)
            print(f"[article] Embeddings saved: {article.title}")


async def main() -> None:
    # Match production behavior: topics get normalized against existing
    # DB tags rather than passed through raw.
    tags_with_counts = await get_all_tags_with_counts()
    initialize_tag_normalizer(tags_with_counts)

    video_ids = await get_video_ids_with_transcript_missing_summary()
    print(f"[videos] {len(video_ids)} video(s) need a summary")
    for video_id in video_ids:
        await backfill_video(video_id)

    await backfill_articles()


if __name__ == "__main__":
    asyncio.run(main())
