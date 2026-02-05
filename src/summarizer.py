import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import anthropic

from .models import CATEGORIES, Summary

logger = logging.getLogger("ytdigest")

MAX_TRANSCRIPT_LENGTH = 100000


def get_anthropic_client() -> anthropic.Anthropic:
    """Create and return an Anthropic client."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")
    return anthropic.Anthropic(api_key=api_key)


def summarize_video(
    video_id: str,
    title: str,
    channel: str,
    transcript: str
) -> Optional[Summary]:
    """
    Generate a summary of a video using Claude.

    Returns a Summary object with the summary text and extracted topics.
    """
    if not transcript:
        return None

    if len(transcript) > MAX_TRANSCRIPT_LENGTH:
        transcript = transcript[:MAX_TRANSCRIPT_LENGTH] + "... [transcript truncated]"

    client = get_anthropic_client()

    categories_str = json.dumps(CATEGORIES)
    prompt = f"""You are analyzing a YouTube video to help someone decide if it's worth watching.

Video Title: {title}
Channel: {channel}

Transcript:
{transcript}

Please provide:
1. A concise summary (2-3 paragraphs) that captures the key points and main takeaways
2. A list of 3-5 topic tags that describe what the video covers
3. A single category from this predefined list that best fits the video: {categories_str}

Format your response as JSON with this structure:
{{
    "summary": "Your summary here...",
    "topics": ["topic1", "topic2", "topic3"],
    "category": "one of the predefined categories"
}}

Focus on:
- What the main topic/thesis is
- Key insights or information shared
- Who would benefit from watching this video
- Any notable conclusions or recommendations

Be concise but informative. Help the reader quickly understand if this video is relevant to their interests."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        response_text = response.content[0].text.strip()

        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]

        result = json.loads(response_text.strip())

        category = result.get("category")
        if category not in CATEGORIES:
            category = "Other"

        return Summary(
            video_id=video_id,
            summary=result["summary"],
            topics=result.get("topics", []),
            category=category,
            generated_at=datetime.now(timezone.utc)
        )

    except json.JSONDecodeError as e:
        logger.warning(f"Error parsing Claude response for {video_id}: {e}")
        logger.debug(f"Response was: {response_text[:500]}")
        return Summary(
            video_id=video_id,
            summary=response_text,
            topics=[],
            category=None,
            generated_at=datetime.now(timezone.utc)
        )
    except anthropic.APIError as e:
        logger.error(f"Anthropic API error for {video_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error summarizing video {video_id}: {e}")
        return None


def classify_existing_summary(
    summary_text: str, topics: list[str]
) -> Optional[str]:
    """Classify an existing summary into a category using a lightweight LLM call.

    Used for backfilling categories on summaries that were generated before
    the category field was added.
    """
    categories_str = json.dumps(CATEGORIES)
    topics_str = ", ".join(topics) if topics else "none"

    prompt = f"""Given this video summary and topics, pick the single best category from this list: {categories_str}

Summary: {summary_text[:500]}
Topics: {topics_str}

Reply with ONLY the category name, nothing else."""

    try:
        client = get_anthropic_client()
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=50,
            messages=[{"role": "user", "content": prompt}],
        )

        category = response.content[0].text.strip()
        if category in CATEGORIES:
            return category
        return "Other"

    except Exception as e:
        logger.error(f"Error classifying summary: {e}")
        return "Other"
