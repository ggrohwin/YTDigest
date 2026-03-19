"""Tag normalization using in-memory embedding similarity.

Maintains a cache of canonical tag → embedding vector. When new tags arrive
from the summarizer, each is compared against the cache. If a sufficiently
similar canonical tag already exists (cosine similarity >= threshold), the
new tag is snapped to the canonical one. Otherwise it becomes a new canonical
tag and is added to the cache.

Processing tags in frequency order (most common first) ensures that well-
established tags become canonical rather than rare one-offs.
"""

import logging

import numpy as np

from .embedder import generate_embeddings

logger = logging.getLogger("ytdigest")

DEFAULT_THRESHOLD = 0.87

# Words that don't count as "shared" for the word-overlap guard
_STOPWORDS = {"and", "or", "the", "of", "in", "for", "to", "a", "an", "vs", "with"}
# Generic words that alone don't constitute meaningful overlap
_GENERIC_WORDS = {
    "ai",
    "enterprise",
    "business",
    "corporate",
    "tech",
    "software",
    "digital",
}
# Qualifier suffixes that add no navigation value
_QUALIFIER_SUFFIXES = {
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
# Voyage can embed up to 128 texts per call; stay safely under that.
EMBED_BATCH_SIZE = 100


def _stem(word: str) -> str:
    """Minimal stemmer: strip trailing 's' for plural normalization."""
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _tag_root(tag: str) -> str:
    """Strip qualifier suffixes and stem words to get the root concept."""
    words = tag.lower().replace("-", " ").split()
    while words and words[-1] in _QUALIFIER_SUFFIXES:
        words.pop()
    return " ".join(_stem(w) for w in words)


def _is_prefix_of(shorter: str, longer: str) -> bool:
    """True if shorter tag is a word-boundary prefix of longer tag."""
    s = shorter.lower().replace("-", " ")
    longer_norm = longer.lower().replace("-", " ")
    return longer_norm.startswith(s + " ") or longer_norm == s


class TagNormalizer:
    def __init__(self, threshold: float = DEFAULT_THRESHOLD):
        self.threshold = threshold
        # canonical tag string -> numpy vector
        self._cache: dict[str, np.ndarray] = {}

    # ------------------------------------------------------------------
    # Building the cache
    # ------------------------------------------------------------------

    def build_from_tags(self, tags_with_counts: list[tuple[str, int]]) -> None:
        """Populate the cache from an existing tag inventory.

        tags_with_counts: list of (tag, count) sorted by count descending.
        Most-frequent tags are processed first so they become canonical.
        """
        if not tags_with_counts:
            return

        tags = [t for t, _ in tags_with_counts]
        logger.info(f"TagNormalizer: embedding {len(tags)} existing tags...")

        # Embed all tags in batches
        all_vectors = self._embed_batch(tags)

        # Process in frequency order: each tag either snaps to an existing
        # canonical tag or becomes a new canonical tag.
        for tag, vector in zip(tags, all_vectors):
            canonical = self._find_canonical(tag, vector)
            if canonical is None:
                self._cache[tag] = vector

        logger.info(f"TagNormalizer: {len(self._cache)} canonical tags in cache.")

    def _embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        """Embed a list of texts in batches, return numpy arrays."""
        vectors = []
        for i in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = texts[i : i + EMBED_BATCH_SIZE]
            raw = generate_embeddings(batch, input_type="document")
            vectors.extend(np.array(v, dtype=np.float32) for v in raw)
        return vectors

    # ------------------------------------------------------------------
    # Normalizing tags
    # ------------------------------------------------------------------

    def normalize(self, tags: list[str]) -> list[str]:
        """Normalize a list of tags, snapping to canonical tags where possible.

        New tags that don't match anything in the cache are added to the cache
        so future tags can snap to them.
        """
        if not tags or not self._cache:
            return tags

        # Embed all incoming tags in one call
        vectors = self._embed_batch(tags)
        result = []
        for tag, vector in zip(tags, vectors):
            canonical = self._find_canonical(tag, vector)
            if canonical is not None:
                if canonical != tag:
                    logger.debug(f"Tag snapped: '{tag}' → '{canonical}'")
                result.append(canonical)
            else:
                # Genuinely new — add to cache
                self._cache[tag] = vector
                result.append(tag)

        # Deduplicate while preserving order
        seen: set[str] = set()
        deduped = []
        for t in result:
            if t not in seen:
                seen.add(t)
                deduped.append(t)
        return deduped

    def _find_canonical(self, tag: str, vector: np.ndarray) -> str | None:
        """Return the best matching canonical tag, else None.

        Checks structural rules first (no embedding needed), then falls back
        to cosine similarity with a word-overlap guard.

        Structural rules (unconditional merge):
        1. Prefix match: canonical is a word-boundary prefix of tag
           e.g. "Ai Hype" matches "Ai Hype Vs Reality"
        2. Root match: same root after stripping qualifier suffixes + stemming
           e.g. "Anthropic" matches "Anthropic Updates"
           e.g. "Ai Hallucinations" matches "Ai Hallucination"

        Embedding rule (similarity >= threshold):
        3. Cosine similarity with meaningful word overlap guard
        """
        tag_root = _tag_root(tag)

        for canonical, canonical_vec in self._cache.items():
            # Root match — same root after stripping qualifier suffixes and stemming.
            # Named product variants (e.g. "Google Gemini") are preserved because
            # their suffix words are not in _QUALIFIER_SUFFIXES.
            if tag_root and _tag_root(canonical) == tag_root:
                return canonical

            # Embedding similarity disabled — structural rules only.
            # Re-enable once embedding strategy is evaluated (see backlog).

        return None

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def size(self) -> int:
        return len(self._cache)

    def canonical_tags(self) -> list[str]:
        return sorted(self._cache.keys())
