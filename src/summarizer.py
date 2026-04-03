import json
import logging
import os
from datetime import datetime, timezone
from typing import Literal, Optional

import anthropic

from .models import CATEGORIES, ArticleSummary, Summary
from .tag_normalizer import TagNormalizer
from .tagging_rules import TAGGING_PRINCIPLES

# Default chat model — cheaper/faster than summarization model
CHAT_MODEL = "claude-sonnet-4-20250514"

logger = logging.getLogger("ytdigest")

# Module-level singleton — initialized at app startup via initialize_tag_normalizer()
_tag_normalizer: TagNormalizer | None = None


def initialize_tag_normalizer(tags_with_counts: list[tuple[str, int]]) -> None:
    """Populate the tag normalizer cache from existing DB tags.

    Call once at app startup after the database is ready.
    tags_with_counts: list of (tag, count) sorted by count descending.
    """
    global _tag_normalizer
    _tag_normalizer = TagNormalizer()
    _tag_normalizer.build_from_tags(tags_with_counts)
    logger.info(f"TagNormalizer ready: {_tag_normalizer.size()} canonical tags.")


def _normalize_tags(tags: list[str]) -> list[str]:
    """Normalize tags if the normalizer is initialized, otherwise pass through."""
    if _tag_normalizer is None:
        return tags
    return _tag_normalizer.normalize(tags)


MAX_TRANSCRIPT_LENGTH = 100000
MAX_ARTICLE_LENGTH = 100000


def get_anthropic_client() -> anthropic.Anthropic:
    """Create and return an Anthropic client."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")
    return anthropic.Anthropic(api_key=api_key)


def summarize_content(
    item_id: str,
    title: str,
    source_name: str,
    content: str,
    content_type: Literal["video", "article"] = "video",
    author: Optional[str] = None,
    model: str = "claude-sonnet-4-20250514",
) -> Optional[Summary | ArticleSummary]:
    """Generate a summary of a video or article using Claude.

    Returns a Summary (for videos) or ArticleSummary (for articles).
    """
    if not content:
        return None

    max_length = (
        MAX_TRANSCRIPT_LENGTH if content_type == "video" else MAX_ARTICLE_LENGTH
    )
    if len(content) > max_length:
        content = content[:max_length] + "... [content truncated]"

    if content_type == "video":
        kind = "YouTube video"
        verb = "watching"
        source_label = "Channel"
        content_label = "Transcript"
    else:
        kind = "web article"
        verb = "reading"
        source_label = "Source"
        content_label = "Article Content"

    author_line = f"\nAuthor: {author}" if author else ""
    categories_str = json.dumps(CATEGORIES)

    prompt = f"""You are analyzing a {kind} to help someone
decide if it's worth {verb}.

{content_type.title()} Title: {title}
{source_label}: {source_name}{author_line}

{content_label}:
{content}

Please provide:
1. A concise summary (2-3 paragraphs) that captures the key points and main takeaways
2. A list of 3-5 topic tags for navigation, following these rules:
{TAGGING_PRINCIPLES}
3. A single category from this predefined list that best
fits the {content_type}: {categories_str}

Format your response as JSON with this structure:
{{
    "summary": "Your summary here...",
    "topics": ["topic1", "topic2", "topic3"],
    "category": "one of the predefined categories"
}}

Focus on:
- What the main topic/thesis is
- Key insights or information shared
- Who would benefit from {verb} this {content_type}
- Any notable conclusions or recommendations

Be concise but informative. Help the reader quickly understand
if this {content_type} is relevant to their interests."""

    client = get_anthropic_client()

    try:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
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

        topics = _normalize_tags(result.get("topics", []))
        generated_at = datetime.now(timezone.utc)

        if content_type == "video":
            return Summary(
                video_id=item_id,
                summary=result["summary"],
                topics=topics,
                category=category,
                generated_at=generated_at,
            )
        return ArticleSummary(
            article_id=item_id,
            summary=result["summary"],
            topics=topics,
            category=category,
            generated_at=generated_at,
        )

    except json.JSONDecodeError as e:
        logger.warning(
            f"Error parsing Claude response for {content_type} {item_id}: {e}"
        )
        logger.debug(f"Response was: {response_text[:500]}")
        if content_type == "video":
            return Summary(
                video_id=item_id,
                summary=response_text,
                topics=[],
                category=None,
                generated_at=datetime.now(timezone.utc),
            )
        return ArticleSummary(
            article_id=item_id,
            summary=response_text,
            topics=[],
            category=None,
            generated_at=datetime.now(timezone.utc),
        )
    except anthropic.APIError as e:
        logger.error(f"Anthropic API error for {content_type} {item_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error summarizing {content_type} {item_id}: {e}")
        return None


def classify_existing_summary(
    summary_text: str,
    topics: list[str],
    model: str = "claude-sonnet-4-20250514",
) -> Optional[str]:
    """Classify an existing summary into a category using a lightweight LLM call.

    Used for backfilling categories on summaries that were generated before
    the category field was added.
    """
    categories_str = json.dumps(CATEGORIES)
    topics_str = ", ".join(topics) if topics else "none"

    prompt = f"""Given this video summary and topics, pick the
single best category from this list: {categories_str}

Summary: {summary_text[:500]}
Topics: {topics_str}

Reply with ONLY the category name, nothing else."""

    try:
        client = get_anthropic_client()
        response = client.messages.create(
            model=model,
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


def summarize_for_question(
    content: str,
    question: str,
    title: str,
    source_name: str,
    content_type: str = "video",
    model: str = CHAT_MODEL,
) -> Optional[str]:
    """Generate a focused summary of content in response to a specific question.

    Used in multi-entry RAG synthesis: retrieve relevant entries, then generate
    question-focused summaries for each to avoid sending full transcripts to Claude.

    Args:
        content: Full transcript or article text
        question: User's question to answer
        title: Entry title
        source_name: Channel/domain name
        content_type: "video" or "article"
        model: Claude model to use

    Returns:
        A focused summary (300-500 words), or None on error.
    """
    if not content or not question:
        return None

    max_len = MAX_TRANSCRIPT_LENGTH if content_type == "video" else MAX_ARTICLE_LENGTH
    if len(content) > max_len:
        content = content[:max_len] + "... [content truncated]"

    kind = "video transcript" if content_type == "video" else "article"

    prompt = f"""You are extracting relevant information from a {kind} to answer a specific question.

Question: {question}

{kind.title()} Title: {title}
Source: {source_name}

{kind.title()} Content:
{content}

Please provide a focused summary that:
1. Extracts ONLY the parts of this {kind} that answer or relate to the question above
2. Maintains coherence and narrative flow (don't just list fragments)
3. Includes relevant details, examples, and context
4. Omits unrelated material entirely
5. Is self-contained (assume the reader sees only this summary, not the full {kind})
6. Is as brief or detailed as the relevance warrants — a few sentences if only tangentially related, up to 500 words if deeply relevant

Write the summary directly without preamble or metadata."""  # noqa: E501

    client = get_anthropic_client()

    try:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except anthropic.APIError as e:
        logger.error(f"Anthropic API error during summarize_for_question: {e}")
        return None
    except Exception as e:
        logger.error(f"Error during summarize_for_question: {e}")
        return None


def chat_with_content(
    content: str,
    title: str,
    source_name: str,
    content_type: str,
    messages: list[dict],
    model: str = CHAT_MODEL,
) -> Optional[str]:
    """Have a multi-turn conversation about a video transcript or article.

    The content (transcript/article text) is passed as a system message so it
    stays constant across turns, while the conversation grows in the messages
    array.

    Returns the assistant's response text, or None on error.
    """
    max_len = MAX_TRANSCRIPT_LENGTH if content_type == "video" else MAX_ARTICLE_LENGTH
    if len(content) > max_len:
        content = content[:max_len] + "... [content truncated]"

    kind = "video transcript" if content_type == "video" else "article"
    system_prompt = (
        f"You are a helpful assistant answering questions about a {kind}.\n\n"
        f"Title: {title}\n"
        f"Source: {source_name}\n\n"
        f"--- {kind.upper()} CONTENT ---\n"
        f"{content}\n"
        f"--- END CONTENT ---\n\n"
        "Be concise. When relevant, quote the source material directly. "
        "If the content doesn't answer the user's question, say so honestly."
    )

    client = get_anthropic_client()

    try:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=system_prompt,
            messages=messages,
        )
        return response.content[0].text
    except anthropic.APIError as e:
        logger.error(f"Anthropic API error during chat: {e}")
        return None
    except Exception as e:
        logger.error(f"Error during chat: {e}")
        return None


def answer_question(
    question: str,
    sources: list[dict],
    model: str = CHAT_MODEL,
) -> Optional[str]:
    """Answer a question using retrieved content from multiple sources (RAG).

    sources: list of dicts with keys: title, source_name, item_type, content, summary
    Returns the assistant's response text, or None on error.
    """
    # Build context blocks from retrieved sources
    context_blocks = []
    for i, src in enumerate(sources, 1):
        kind = "Video Transcript" if src["item_type"] == "video" else "Article"
        block = f"[Source {i}] {kind}: {src['title']}\n" f"By: {src['source_name']}\n"
        if src.get("summary"):
            block += f"Summary: {src['summary']}\n"
        if src.get("content"):
            # Include full content, truncated if very long
            content = src["content"]
            max_len = MAX_TRANSCRIPT_LENGTH
            if len(content) > max_len:
                content = content[:max_len] + "... [truncated]"
            block += f"Full Content:\n{content}\n"
        context_blocks.append(block)

    context = "\n---\n\n".join(context_blocks)

    system_prompt = (
        "You are a helpful assistant answering questions about the user's "
        "video and article library. You have been given the most relevant "
        "sources from their collection.\n\n"
        f"--- SOURCES ---\n{context}\n--- END SOURCES ---\n\n"
        "Instructions:\n"
        "- Answer the question based on the sources provided.\n"
        "- Cite sources by referencing the title in your answer "
        '(e.g. "According to [Title]...").\n'
        "- If the sources don't contain enough information to answer, "
        "say so honestly.\n"
        "- Be concise but thorough."
    )

    client = get_anthropic_client()

    try:
        response = client.messages.create(
            model=model,
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": question}],
        )
        return response.content[0].text
    except anthropic.APIError as e:
        logger.error(f"Anthropic API error during answer_question: {e}")
        return None
    except Exception as e:
        logger.error(f"Error during answer_question: {e}")
        return None
