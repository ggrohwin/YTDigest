"""
Spike evaluation harness: compare full-transcript vs chunked RAG retrieval.

Runs the same questions through both approaches and reports:
- Answer text (for qualitative comparison)
- Token usage (input/output)
- Sources used

Usage:
    python scripts/eval_rag.py                  # run evaluation
    python scripts/eval_rag.py --backfill       # backfill chunk_text first
    python scripts/eval_rag.py --backfill-only  # backfill only, no evaluation
"""

import argparse
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import anthropic
import numpy as np
from dotenv import load_dotenv

from src.database import get_all_embeddings
from src.embedder import (
    bytes_to_embedding,
    chunk_text,
    cosine_similarity,
    generate_embeddings,
)

load_dotenv()

# -- Configuration --------------------------------------------------------

# Default model matches app config
MODEL = "claude-sonnet-4-20250514"
MAX_CONTENT_LENGTH = 100_000

# Test questions — mix of broad and specific
TEST_QUESTIONS = [
    (
        "I don't understand what context engineering is. Please give me a"
        " high-level explanation, and then suggest some digest entries"
        " that would be useful to me in understanding this topic. In"
        " particular, I'd like to see entries that provide practical"
        " examples of applying/implementing this concept."
    ),
    (
        "I don't understand what agent orchestration is. Please give me"
        " a high-level explanation, and then suggest some digest entries"
        " that would be useful to me in understanding this topic. In"
        " particular, I'd like to see entries that provide practical"
        " examples of applying/implementing this concept."
    ),
    (
        "Which creators are running freelance businesses developing"
        " AI solutions, and what are they focused on?"
    ),
    (
        "Based on the digest entries available, can someone like"
        " myself be successful as a freelance AI application"
        " developer at the present moment?"
    ),
    (
        "Attempts to develop enterprise-wide AI solutions to"
        " synthesize information sources from across the enterprise"
        " have run into data quality issues. Is this correct? This"
        " seems to create new opportunities in data engineering and"
        " data normalization."
    ),
]

# -- Backfill chunk_text --------------------------------------------------


def backfill_chunk_text():
    """Populate chunk_text for existing chunk embeddings by re-chunking source content.

    This avoids re-calling the Voyage API — we just re-derive the text from
    the full content using the same chunking parameters and match by chunk_index.

    Uses synchronous sqlite3 to avoid conflicts with the running
    app's async connections.
    """
    import sqlite3

    from src.database import DATABASE_PATH

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row

    # Find all items with chunk embeddings but no chunk_text
    items = conn.execute("""
        SELECT DISTINCT item_id, item_type
        FROM embeddings
        WHERE content_type LIKE '%_chunk'
        AND chunk_text IS NULL
    """).fetchall()

    if not items:
        print("All chunk embeddings already have text. Nothing to backfill.")
        conn.close()
        return

    print(f"Backfilling chunk_text for {len(items)} items...")
    updated = 0
    skipped = 0

    for item in items:
        item_id = item["item_id"]
        item_type = item["item_type"]

        # Get the full source text
        if item_type == "video":
            row = conn.execute(
                "SELECT content FROM transcripts WHERE video_id = ?", (item_id,)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT content FROM articles WHERE id = ?", (item_id,)
            ).fetchone()

        if not row:
            skipped += 1
            continue

        full_text = row[0]
        chunks = chunk_text(full_text)

        for i, text in enumerate(chunks):
            conn.execute(
                """
                UPDATE embeddings
                SET chunk_text = ?
                WHERE item_id = ? AND content_type = ? AND chunk_index = ?
                """,
                (text, item_id, f"{item_type}_chunk", i),
            )

        updated += 1

    conn.commit()
    print(f"Done. Updated {updated} items, skipped {skipped} (no source text).")

    row = conn.execute(
        "SELECT COUNT(*) FROM embeddings WHERE chunk_text IS NOT NULL"
    ).fetchone()
    print(f"Chunks with text: {row[0]}")
    conn.close()


# -- Search strategies ----------------------------------------------------


async def search_items(query: str, limit: int = 5) -> list[tuple[str, str, float]]:
    """Current approach: search embeddings, deduplicate by item, return top items."""
    query_vectors = generate_embeddings([query], input_type="query")
    query_vec = np.array(query_vectors[0], dtype=np.float32)

    all_embeddings = await get_all_embeddings()
    if not all_embeddings:
        return []

    best_scores: dict[tuple[str, str], float] = {}
    for emb, raw_bytes in all_embeddings:
        stored_vec = bytes_to_embedding(raw_bytes)
        score = cosine_similarity(query_vec, stored_vec)
        key = (emb.item_id, emb.item_type)
        if key not in best_scores or score > best_scores[key]:
            best_scores[key] = score

    ranked = sorted(best_scores.items(), key=lambda x: x[1], reverse=True)
    return [
        (item_id, item_type, score)
        for (item_id, item_type), score in ranked[:limit]
        if score >= 0.3
    ]


async def search_chunks(
    query: str, limit: int = 15
) -> list[tuple[str, str, str, float]]:
    """Chunked approach: search embeddings, return top chunks with their text.

    Returns (item_id, item_type, chunk_text, score) tuples.
    Only includes chunk-level embeddings (not summary embeddings).
    """
    query_vectors = generate_embeddings([query], input_type="query")
    query_vec = np.array(query_vectors[0], dtype=np.float32)

    all_embeddings = await get_all_embeddings()
    if not all_embeddings:
        return []

    scored_chunks = []
    for emb, raw_bytes in all_embeddings:
        # Only use chunk embeddings, skip summary-level
        if not emb.content_type.endswith("_chunk"):
            continue
        if not emb.chunk_text:
            continue

        stored_vec = bytes_to_embedding(raw_bytes)
        score = cosine_similarity(query_vec, stored_vec)
        if score >= 0.3:
            scored_chunks.append((emb.item_id, emb.item_type, emb.chunk_text, score))

    scored_chunks.sort(key=lambda x: x[3], reverse=True)
    return scored_chunks[:limit]


# -- Answer generation ----------------------------------------------------


def call_claude(system_prompt: str, question: str, max_retries: int = 3) -> dict:
    """Call Claude and return answer text + usage stats. Retries on rate limit."""
    client = anthropic.Anthropic()
    for attempt in range(max_retries):
        try:
            start = time.time()
            response = client.messages.create(
                model=MODEL,
                max_tokens=2048,
                system=system_prompt,
                messages=[{"role": "user", "content": question}],
            )
            elapsed = time.time() - start
            return {
                "answer": response.content[0].text,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "latency_s": round(elapsed, 2),
            }
        except anthropic.RateLimitError:
            wait = 60 * (attempt + 1)
            print(f"    Rate limited. Waiting {wait}s...")
            time.sleep(wait)
    return {
        "answer": "ERROR: rate limit exceeded",
        "input_tokens": 0,
        "output_tokens": 0,
        "latency_s": 0,
    }


async def answer_full_transcript(question: str) -> dict:
    """Current approach: retrieve items, load full transcripts, send to Claude."""
    from src.database import get_article, get_transcript, get_video

    results = await search_items(question, limit=5)
    if not results:
        return {"answer": "No results found.", "input_tokens": 0, "output_tokens": 0}

    context_blocks = []
    source_titles = []
    for i, (item_id, item_type, score) in enumerate(results, 1):
        if item_type == "video":
            video = await get_video(item_id)
            transcript = await get_transcript(item_id)
            if not video or not transcript:
                continue
            title = video.title
            content = transcript.content
            source_name = video.channel_name
            kind = "Video Transcript"
        else:
            article = await get_article(item_id)
            if not article:
                continue
            title = article.title
            content = article.content
            source_name = article.domain
            kind = "Article"

        if len(content) > MAX_CONTENT_LENGTH:
            content = content[:MAX_CONTENT_LENGTH] + "... [truncated]"

        block = (
            f"[Source {i}] {kind}: {title}\n"
            f"By: {source_name} (score: {score:.4f})\n"
            f"Full Content:\n{content}\n"
        )
        context_blocks.append(block)
        source_titles.append(f"{title} ({score:.4f})")

    context = "\n---\n\n".join(context_blocks)
    system_prompt = (
        "You are a helpful assistant answering questions about the user's "
        "video and article library. You have been given the most relevant "
        "sources from their collection.\n\n"
        f"--- SOURCES ---\n{context}\n--- END SOURCES ---\n\n"
        "Instructions:\n"
        "- Answer the question based on the sources provided.\n"
        "- Cite sources by referencing the title in your answer.\n"
        "- If the sources don't contain enough information, say so honestly.\n"
        "- Be concise but thorough."
    )

    result = call_claude(system_prompt, question)
    result["sources"] = source_titles
    result["num_sources"] = len(source_titles)
    return result


async def answer_chunked(question: str) -> dict:
    """Chunked approach: retrieve top chunks, send only those to Claude."""
    chunks = await search_chunks(question, limit=15)
    if not chunks:
        return {"answer": "No results found.", "input_tokens": 0, "output_tokens": 0}

    # Group chunks by item for source attribution
    seen_items = set()
    context_blocks = []
    for i, (item_id, item_type, text, score) in enumerate(chunks, 1):
        seen_items.add((item_id, item_type))
        block = (
            f"[Chunk {i}] (item: {item_id[:8]}, type: {item_type}, "
            f"score: {score:.4f})\n{text}\n"
        )
        context_blocks.append(block)

    context = "\n---\n\n".join(context_blocks)
    system_prompt = (
        "You are a helpful assistant answering questions about the user's "
        "video and article library. You have been given the most relevant "
        "excerpts from their collection.\n\n"
        f"--- EXCERPTS ---\n{context}\n--- END EXCERPTS ---\n\n"
        "Instructions:\n"
        "- Answer the question based on the excerpts provided.\n"
        "- Excerpts are ranked by relevance — earlier ones are more relevant.\n"
        "- If the excerpts don't contain enough information, say so honestly.\n"
        "- Be concise but thorough."
    )

    result = call_claude(system_prompt, question)
    result["num_sources"] = len(seen_items)
    result["num_chunks"] = len(chunks)
    return result


async def answer_question_focused_summaries(question: str) -> dict:
    """Question-focused summaries: retrieve, summarize, synthesize."""
    from src.database import get_article, get_transcript, get_video
    from src.summarizer import summarize_for_question

    results = await search_items(question, limit=8)
    if not results:
        return {"answer": "No results found.", "input_tokens": 0, "output_tokens": 0}

    # Generate question-focused summary for each entry
    focused_summaries = []
    source_titles = []
    summary_details = []  # Per-entry summary stats
    for i, (item_id, item_type, score) in enumerate(results, 1):
        if item_type == "video":
            video = await get_video(item_id)
            transcript = await get_transcript(item_id)
            if not video or not transcript:
                continue
            title = video.title
            content = transcript.content
            source_name = video.channel_name
            kind = "Video Transcript"
        else:
            article = await get_article(item_id)
            if not article:
                continue
            title = article.title
            content = article.content
            source_name = article.domain
            kind = "Article"

        if len(content) > MAX_CONTENT_LENGTH:
            content = content[:MAX_CONTENT_LENGTH] + "... [truncated]"

        # Generate focused summary for this entry
        focused_summary = summarize_for_question(
            content=content,
            question=question,
            title=title,
            source_name=source_name,
            content_type=item_type,
        )

        if focused_summary:
            word_count = len(focused_summary.split())
            block = (
                f"[Source {i}] {kind}: {title}\n"
                f"By: {source_name} (relevance score: {score:.4f})\n"
                f"Focused Summary:\n{focused_summary}\n"
            )
            focused_summaries.append(block)
            source_titles.append(f"{title} ({score:.4f})")
            summary_details.append(
                {
                    "title": title,
                    "score": round(score, 4),
                    "word_count": word_count,
                }
            )

    if not focused_summaries:
        return {
            "answer": "Could not generate summaries.",
            "input_tokens": 0,
            "output_tokens": 0,
        }

    context = "\n---\n\n".join(focused_summaries)
    system_prompt = (
        "You are a helpful assistant answering questions about the user's "
        "video and article library. You have been given question-focused summaries "
        "from the most relevant sources in their collection.\n\n"
        f"--- FOCUSED SUMMARIES ---\n{context}\n--- END SUMMARIES ---\n\n"
        "Instructions:\n"
        "- Answer the question based on the summaries provided.\n"
        "- Cite sources by referencing the title in your answer.\n"
        "- Synthesize across multiple sources where relevant.\n"
        "- If the summaries don't contain enough information, say so honestly.\n"
        "- Be concise but thorough."
    )

    result = call_claude(system_prompt, question)
    result["sources"] = source_titles
    result["num_sources"] = len(source_titles)
    result["summary_details"] = summary_details
    return result


# -- Main evaluation ------------------------------------------------------


async def run_evaluation():
    """Run all test questions through all three approaches and print comparison."""
    print("=" * 80)
    print("RAG EVALUATION: Full Transcript vs Chunks vs Question-Focused Summaries")
    print("=" * 80)

    totals = {
        "full": {"input_tokens": 0, "output_tokens": 0, "latency": 0},
        "chunked": {"input_tokens": 0, "output_tokens": 0, "latency": 0},
        "focused_summaries": {"input_tokens": 0, "output_tokens": 0, "latency": 0},
    }

    results = []

    for i, question in enumerate(TEST_QUESTIONS, 1):
        print(f"\n{'-' * 80}")
        print(f"Question {i}/{len(TEST_QUESTIONS)}: {question}")
        print(f"{'-' * 80}")

        # Run all three approaches
        print("\n  Running full-transcript approach...")
        full = await answer_full_transcript(question)

        print("  Running chunked approach...")
        chunked = await answer_chunked(question)

        print("  Running question-focused summaries approach...")
        focused_summaries = await answer_question_focused_summaries(question)

        # Display results
        print("\n  +- FULL TRANSCRIPT -----------------------------")
        print(f"  | Sources: {full.get('num_sources', 0)}")
        print(f"  | Input tokens:  {full['input_tokens']:,}")
        print(f"  | Output tokens: {full['output_tokens']:,}")
        print(f"  | Latency: {full.get('latency_s', 0)}s")
        print("  |")
        # Indent answer
        for line in full["answer"][:500].split("\n"):
            print(f"  | {line}")
        if len(full["answer"]) > 500:
            print("  | ... [truncated at 500 chars]")
        print("  +-------------------------------------------------")

        print("\n  +- CHUNKED RETRIEVAL ------------------------------")
        print(
            f"  | Entries: {chunked.get('num_sources', 0)}, "
            f"Chunks: {chunked.get('num_chunks', 0)}"
        )
        print(f"  | Input tokens:  {chunked['input_tokens']:,}")
        print(f"  | Output tokens: {chunked['output_tokens']:,}")
        print(f"  | Latency: {chunked.get('latency_s', 0)}s")
        print("  |")
        for line in chunked["answer"][:500].split("\n"):
            print(f"  | {line}")
        if len(chunked["answer"]) > 500:
            print("  | ... [truncated at 500 chars]")
        print("  +-------------------------------------------------")

        print("\n  +- QUESTION-FOCUSED SUMMARIES ------------------")
        print(f"  | Sources: {focused_summaries.get('num_sources', 0)}")
        print(f"  | Input tokens:  {focused_summaries['input_tokens']:,}")
        print(f"  | Output tokens: {focused_summaries['output_tokens']:,}")
        print(f"  | Latency: {focused_summaries.get('latency_s', 0)}s")
        if focused_summaries.get("summary_details"):
            print("  |")
            print("  | Per-entry summary sizes:")
            for detail in focused_summaries["summary_details"]:
                wc = detail["word_count"]
                sc = detail["score"]
                t = detail["title"][:60]
                print(f"  |   {wc:>4} words  (score: {sc:.4f})  {t}")
        print("  |")
        for line in focused_summaries["answer"][:500].split("\n"):
            print(f"  | {line}")
        if len(focused_summaries["answer"]) > 500:
            print("  | ... [truncated at 500 chars]")
        print("  +-------------------------------------------------")

        # Token savings comparison
        if full["input_tokens"] > 0:
            chunked_savings = (
                (full["input_tokens"] - chunked["input_tokens"])
                / full["input_tokens"]
                * 100
            )
            focused_savings = (
                (full["input_tokens"] - focused_summaries["input_tokens"])
                / full["input_tokens"]
                * 100
            )
            print("\n  Token savings (vs full):")
            print(f"    Chunked:            {chunked_savings:+.1f}%")
            print(f"    Focused summaries:  {focused_savings:+.1f}%")

        totals["full"]["input_tokens"] += full["input_tokens"]
        totals["full"]["output_tokens"] += full["output_tokens"]
        totals["full"]["latency"] += full.get("latency_s", 0)
        totals["chunked"]["input_tokens"] += chunked["input_tokens"]
        totals["chunked"]["output_tokens"] += chunked["output_tokens"]
        totals["chunked"]["latency"] += chunked.get("latency_s", 0)
        totals["focused_summaries"]["input_tokens"] += focused_summaries["input_tokens"]
        totals["focused_summaries"]["output_tokens"] += focused_summaries[
            "output_tokens"
        ]
        totals["focused_summaries"]["latency"] += focused_summaries.get("latency_s", 0)

        results.append(
            {
                "question": question,
                "full": full,
                "chunked": chunked,
                "focused_summaries": focused_summaries,
            }
        )

    # Summary
    print(f"\n{'=' * 80}")
    print("SUMMARY")
    print(f"{'=' * 80}")
    print(f"  Questions evaluated: {len(TEST_QUESTIONS)}")
    print(f"\n  {'':30s} {'Full':>14s} {'Chunked':>14s} {'Focused':>14s}")
    print(f"  {'-' * 76}")

    f_in = totals["full"]["input_tokens"]
    c_in = totals["chunked"]["input_tokens"]
    foc_in = totals["focused_summaries"]["input_tokens"]
    print(f"  {'Total input tokens':30s} {f_in:>14,} {c_in:>14,} {foc_in:>14,}")

    f_out = totals["full"]["output_tokens"]
    c_out = totals["chunked"]["output_tokens"]
    foc_out = totals["focused_summaries"]["output_tokens"]
    print(f"  {'Total output tokens':30s} {f_out:>14,} {c_out:>14,} {foc_out:>14,}")

    f_lat = totals["full"]["latency"]
    c_lat = totals["chunked"]["latency"]
    foc_lat = totals["focused_summaries"]["latency"]
    print(f"  {'Total latency':30s} {f_lat:>13.1f}s {c_lat:>13.1f}s {foc_lat:>13.1f}s")

    avg_f = f_in / len(TEST_QUESTIONS) if TEST_QUESTIONS else 0
    avg_c = c_in / len(TEST_QUESTIONS) if TEST_QUESTIONS else 0
    avg_foc = foc_in / len(TEST_QUESTIONS) if TEST_QUESTIONS else 0
    label = "Avg input tokens/question"
    print(f"  {label:30s} {avg_f:>14,.0f} {avg_c:>14,.0f} {avg_foc:>14,.0f}")

    # Token savings comparison
    if f_in > 0:
        c_savings = (f_in - c_in) / f_in * 100
        foc_savings = (f_in - foc_in) / f_in * 100
        label = "Token savings vs Full"
        print(
            f"\n  {label:30s} {'':>14s}" f" {c_savings:>13.1f}% {foc_savings:>13.1f}%"
        )

    # Save raw results
    output_path = "data/rag_eval_results.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Raw results saved to {output_path}")


# -- Entry point ----------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate RAG strategies")
    parser.add_argument(
        "--backfill", action="store_true", help="Backfill chunk_text before evaluation"
    )
    parser.add_argument(
        "--backfill-only",
        action="store_true",
        help="Only backfill chunk_text, skip evaluation",
    )
    args = parser.parse_args()

    if args.backfill or args.backfill_only:
        backfill_chunk_text()
        if args.backfill_only:
            sys.exit(0)

    asyncio.run(run_evaluation())
