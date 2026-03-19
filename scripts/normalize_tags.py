"""
One-off script to retroactively normalize all existing tags using embedding
similarity. Run from the project root:

    python scripts/normalize_tags.py

Algorithm:
  1. Load all distinct tags sorted most-frequent-first.
  2. Embed all tags in one batch Voyage call.
  3. Process in frequency order — each tag either becomes canonical (added to
     the cache) or gets mapped to an existing canonical tag if:
       a. cosine similarity >= threshold, AND
       b. the two tags share at least one significant word (guards against
          merging distinct named entities like 'Claude' and 'OpenAI' that
          sit near each other in embedding space).
  4. Apply the mapping to every row in the database.
"""

import sqlite3
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

DB_PATH = "data/ytdigest.db"
STOPWORDS = {"and", "or", "the", "of", "in", "for", "to", "a", "an", "vs", "with"}
# Generic prefix words that alone don't constitute meaningful overlap.
# e.g. "Enterprise Software" and "Enterprise Ai" share only "enterprise" — not enough.
GENERIC_WORDS = {
    "ai",
    "enterprise",
    "business",
    "corporate",
    "tech",
    "software",
    "digital",
}
# Qualifier suffixes that add no navigation value — strip before comparing.
QUALIFIER_SUFFIXES = {
    "challenges",
    "updates",
    "news",
    "analysis",
    "overview",
    "recap",
    "issues",
    "risks",
    "concerns",
    "trends",
    "insights",
    "implications",
    "criticism",
    "critique",
    "tutorial",
    "guide",
    "discussion",
    "examples",
}


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def load_tag_counts(conn: sqlite3.Connection) -> Counter:
    counts: Counter = Counter()
    for row in conn.execute("SELECT topics FROM summaries WHERE topics != ''"):
        for t in row["topics"].split(","):
            t = t.strip().title()
            if t:
                counts[t] += 1
    for row in conn.execute("SELECT topics FROM article_summaries WHERE topics != ''"):
        for t in row["topics"].split(","):
            t = t.strip().title()
            if t:
                counts[t] += 1
    return counts


def stem(word: str) -> str:
    """Minimal stemmer: strip trailing 's' for plural normalization."""
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def tag_words(tag: str) -> set[str]:
    words = {w.lower() for w in tag.replace("-", " ").split()} - STOPWORDS
    return {stem(w) for w in words}


def tag_root(tag: str) -> str:
    """Strip trailing qualifier suffixes and stem words to get the root concept.

    Stemming handles singular/plural variants:
      "Ai Hallucination" and "Ai Hallucinations" both -> "ai hallucination"
    Suffix stripping handles qualifier variants:
      "Anthropic Updates" -> "anthropic"
      "Ai Implementation Challenges" -> "ai implementation"
    """
    words = tag.lower().replace("-", " ").split()
    while words and words[-1] in QUALIFIER_SUFFIXES:
        words.pop()
    return " ".join(stem(w) for w in words)


def is_prefix_of(shorter: str, longer: str) -> bool:
    """True if shorter tag is a prefix of longer tag (word-boundary match)."""
    s = shorter.lower().replace("-", " ")
    longer_norm = longer.lower().replace("-", " ")
    return longer_norm.startswith(s + " ") or longer_norm == s


def build_canonical_mapping(
    tags_by_freq: list[tuple[str, int]],
) -> dict[str, str]:
    """Single-pass: process tags most-frequent-first.

    Each tag either becomes canonical or maps to an existing canonical
    via structural rules only. Embedding similarity is disabled pending
    embedding strategy evaluation (see backlog).

    Returns only the non-identity mappings: {original -> canonical}.
    """
    canonical_cache: set[str] = set()
    mapping: dict[str, str] = {}

    for tag, _ in tags_by_freq:
        best_canonical: str | None = None

        for canonical in canonical_cache:
            # Root match — same root after stripping qualifier suffixes and stemming.
            # Handles plural/singular and noise qualifiers:
            #   "Ai Hallucination" == "Ai Hallucinations"
            #   "Anthropic Updates" == "Anthropic"
            #   "Ai Implementation Challenges" == "Ai Implementation"
            #   "Openclaw Criticism" == "Openclaw"
            # Named product variants (e.g. "Google Gemini", "Claude Opus") are
            # preserved because their suffix words are not in QUALIFIER_SUFFIXES.
            if tag_root(tag) == tag_root(canonical) and tag_root(tag):
                best_canonical = canonical
                break

        if best_canonical is not None:
            mapping[tag] = best_canonical
        else:
            canonical_cache.add(tag)

    return mapping


def apply_mapping(
    conn: sqlite3.Connection, mapping: dict[str, str], table: str, id_col: str
) -> int:
    changed = 0
    rows = list(
        conn.execute(f"SELECT {id_col}, topics FROM {table} WHERE topics != ''")
    )
    for row in rows:
        original_topics = [
            t.strip().title() for t in row["topics"].split(",") if t.strip()
        ]
        new_topics: list[str] = []
        seen: set[str] = set()
        for t in original_topics:
            canonical = mapping.get(t, t)
            if canonical not in seen:
                seen.add(canonical)
                new_topics.append(canonical)
        new_str = ",".join(new_topics)
        if new_str != row["topics"]:
            conn.execute(
                f"UPDATE {table} SET topics = ? WHERE {id_col} = ?",
                (new_str, row[id_col]),
            )
            changed += 1
    return changed


def print_stats(before: Counter, after: Counter) -> None:
    print(f"\n{'':>4}{'Before':>10}{'After':>10}")
    print(f"  {'Unique tags':<28}{len(before):>6}{len(after):>10}")
    print(
        f"  {'Single-occurrence tags':<28}"
        f"{sum(1 for c in before.values() if c == 1):>6}"
        f"{sum(1 for c in after.values() if c == 1):>10}"
    )
    print("\nTop 20 tags after normalization:")
    for tag, count in after.most_common(20):
        print(f"  {count:4d}  {tag}")


def main() -> None:
    conn = get_connection()
    counts = load_tag_counts(conn)
    tags_by_freq = counts.most_common()
    tags = [t for t, _ in tags_by_freq]

    print(f"Loaded {len(tags)} unique tags.")
    print("Building canonical mapping (structural rules only)...")
    mapping = build_canonical_mapping(tags_by_freq)

    remapped = len(mapping)
    canonical_count = len(tags) - remapped
    print(f"  {remapped} tags will be remapped -> {canonical_count} canonical tags")

    print("\nSample remappings (up to 20):")
    for original, canonical in list(mapping.items())[:20]:
        freq = f"(freq: {counts[original]} -> {counts[canonical]})"
        print(f"  '{original}' -> '{canonical}'  {freq}")

    changed_v = apply_mapping(conn, mapping, "summaries", "video_id")
    changed_a = apply_mapping(conn, mapping, "article_summaries", "article_id")
    conn.commit()
    print(f"\nUpdated {changed_v} video rows, {changed_a} article rows.")

    after = load_tag_counts(conn)
    print_stats(counts, after)
    conn.close()


if __name__ == "__main__":
    main()
