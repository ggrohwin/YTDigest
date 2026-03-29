"""
One-off script to re-tag all existing summaries using refined tagging principles.

Backs up current tags before overwriting. Run from the project root:
    python scripts/retag_summaries.py
"""

import asyncio
import json
import os
import sqlite3
import sys
from datetime import datetime

import anthropic
from dotenv import load_dotenv

# Allow importing from src/ when run from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.tagging_rules import TAGGING_PRINCIPLES

load_dotenv()

DB_PATH = "data/ytdigest.db"
MODEL = "claude-haiku-4-5-20251001"
CONCURRENCY = 5
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

RETAG_PROMPT = f"""You are re-tagging an existing summary to improve navigation.

{TAGGING_PRINCIPLES}

Return 3-5 tags as a JSON array of strings. No explanation, just the array.
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def backup_tags(conn: sqlite3.Connection) -> None:
    """Save current tags to backup columns before overwriting."""
    (
        conn.execute(
            "ALTER TABLE summaries ADD COLUMN IF NOT EXISTS topics_backup TEXT"
        )
        if False
        else None
    )  # SQLite doesn't support IF NOT EXISTS on ALTER

    # Check if backup columns exist, add if not
    cols = {row[1] for row in conn.execute("PRAGMA table_info(summaries)")}
    if "topics_backup" not in cols:
        conn.execute("ALTER TABLE summaries ADD COLUMN topics_backup TEXT")

    cols = {row[1] for row in conn.execute("PRAGMA table_info(article_summaries)")}
    if "topics_backup" not in cols:
        conn.execute("ALTER TABLE article_summaries ADD COLUMN topics_backup TEXT")

    conn.execute(
        "UPDATE summaries SET topics_backup = topics WHERE topics_backup IS NULL"
    )
    conn.execute(
        "UPDATE article_summaries SET topics_backup = topics"
        " WHERE topics_backup IS NULL"
    )
    conn.commit()
    print("Tags backed up to topics_backup columns.")


def load_summaries(conn: sqlite3.Connection) -> list[dict]:
    rows = []
    for row in conn.execute(
        "SELECT video_id as id, summary, topics FROM summaries WHERE summary != ''"
    ):
        rows.append(
            {
                "id": row["id"],
                "table": "summaries",
                "summary": row["summary"],
                "current_topics": row["topics"],
            }
        )
    for row in conn.execute(
        "SELECT article_id as id, summary, topics"
        " FROM article_summaries WHERE summary != ''"
    ):
        rows.append(
            {
                "id": row["id"],
                "table": "article_summaries",
                "summary": row["summary"],
                "current_topics": row["topics"],
            }
        )
    return rows


async def retag_one(
    client: anthropic.AsyncAnthropic,
    sem: asyncio.Semaphore,
    item: dict,
) -> dict:
    prompt = f"""{RETAG_PROMPT}

Current tags (for reference): {item['current_topics']}

Summary:
{item['summary'][:1500]}
"""
    async with sem:
        for attempt in range(MAX_RETRIES):
            try:
                response = await client.messages.create(
                    model=MODEL,
                    max_tokens=200,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = response.content[0].text.strip()
                # Strip markdown fences if present
                if text.startswith("```"):
                    text = text.split("```")[1]
                    if text.startswith("json"):
                        text = text[4:]
                tags = json.loads(text.strip())
                if not isinstance(tags, list):
                    tags = []
                return {
                    "id": item["id"],
                    "table": item["table"],
                    "tags": tags,
                    "ok": True,
                }
            except anthropic.RateLimitError:
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                print(f"  RATE LIMIT (gave up): {item['id']}")
            except Exception as e:
                print(f"  ERROR {item['id']}: {e}")
                break
        return {"id": item["id"], "table": item["table"], "tags": [], "ok": False}


def write_results(conn: sqlite3.Connection, results: list[dict]) -> None:
    for r in results:
        if not r["ok"] or not r["tags"]:
            continue
        tags_str = ",".join(r["tags"])
        if r["table"] == "summaries":
            conn.execute(
                "UPDATE summaries SET topics = ? WHERE video_id = ?",
                (tags_str, r["id"]),
            )
        else:
            conn.execute(
                "UPDATE article_summaries SET topics = ? WHERE article_id = ?",
                (tags_str, r["id"]),
            )
    conn.commit()


def print_stats(conn: sqlite3.Connection) -> None:
    from collections import Counter

    all_topics = []
    for row in conn.execute("SELECT topics FROM summaries WHERE topics != ''"):
        all_topics.extend(t.strip() for t in row["topics"].split(",") if t.strip())
    for row in conn.execute("SELECT topics FROM article_summaries WHERE topics != ''"):
        all_topics.extend(t.strip() for t in row["topics"].split(",") if t.strip())

    counts = Counter(t.title() for t in all_topics)
    singles = sum(1 for c in counts.values() if c == 1)
    print("\nAfter re-tagging:")
    print(f"  Total tag occurrences : {len(all_topics)}")
    print(f"  Unique tags           : {len(counts)}")
    print(f"  Appear only once      : {singles}")
    print("\nTop 20 tags:")
    for tag, count in counts.most_common(20):
        print(f"  {count:4d}  {tag}")


async def main() -> None:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")

    conn = get_connection()
    backup_tags(conn)

    items = load_summaries(conn)
    print(
        f"Loaded {len(items)} summaries. Re-tagging with concurrency={CONCURRENCY}..."
    )

    client = anthropic.AsyncAnthropic(api_key=api_key)
    sem = asyncio.Semaphore(CONCURRENCY)

    start = datetime.now()
    results = await asyncio.gather(*[retag_one(client, sem, item) for item in items])
    elapsed = (datetime.now() - start).total_seconds()

    ok = sum(1 for r in results if r["ok"])
    print(f"\nCompleted {ok}/{len(results)} successfully in {elapsed:.1f}s")

    write_results(conn, results)
    print_stats(conn)
    conn.close()


if __name__ == "__main__":
    asyncio.run(main())
