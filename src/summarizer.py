import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import anthropic

from .models import Summary

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

    prompt = f"""You are analyzing a YouTube video to help someone decide if it's worth watching.

Video Title: {title}
Channel: {channel}

Transcript:
{transcript}

Please provide:
1. A concise summary (2-3 paragraphs) that captures the key points and main takeaways
2. A list of 3-5 topic tags that describe what the video covers

Format your response as JSON with this structure:
{{
    "summary": "Your summary here...",
    "topics": ["topic1", "topic2", "topic3"]
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

        return Summary(
            video_id=video_id,
            summary=result["summary"],
            topics=result.get("topics", []),
            generated_at=datetime.now(timezone.utc)
        )

    except json.JSONDecodeError as e:
        logger.warning(f"Error parsing Claude response for {video_id}: {e}")
        logger.debug(f"Response was: {response_text[:500]}")
        return Summary(
            video_id=video_id,
            summary=response_text,
            topics=[],
            generated_at=datetime.now(timezone.utc)
        )
    except anthropic.APIError as e:
        logger.error(f"Anthropic API error for {video_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error summarizing video {video_id}: {e}")
        return None
