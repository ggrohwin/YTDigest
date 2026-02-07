"""Embedding generation and semantic search using Voyage AI.

Generates vector embeddings for summaries and text chunks, stores them
in SQLite, and provides cosine-similarity-based search.
"""

import logging
import os
from typing import Optional

import numpy as np
import voyageai

from .models import Embedding

logger = logging.getLogger("ytdigest")

# Voyage AI configuration
VOYAGE_MODEL = "voyage-3-lite"
VOYAGE_DIMENSIONS = 512


def is_available() -> bool:
    """Check whether embedding generation is available (API key is set)."""
    return bool(os.environ.get("VOYAGE_API_KEY"))


def generate_embeddings(
    texts: list[str], input_type: str = "document"
) -> list[list[float]]:
    """Generate embeddings for a list of texts using Voyage AI.

    Args:
        texts: List of text strings to embed.
        input_type: "document" when embedding stored content,
                     "query" when embedding a search query.

    Returns:
        List of embedding vectors (each a list of floats).
    """
    api_key = os.environ.get("VOYAGE_API_KEY")
    if not api_key:
        raise RuntimeError("VOYAGE_API_KEY environment variable is not set")

    client = voyageai.Client(api_key=api_key)
    result = client.embed(texts, model=VOYAGE_MODEL, input_type=input_type)
    return result.embeddings


def embedding_to_bytes(vector: list[float]) -> bytes:
    """Serialize an embedding vector to bytes for SQLite storage."""
    return np.array(vector, dtype=np.float32).tobytes()


def bytes_to_embedding(data: bytes) -> np.ndarray:
    """Deserialize bytes from SQLite back to a numpy array."""
    return np.frombuffer(data, dtype=np.float32)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors.

    Both vectors are normalized to unit length, then their dot product
    gives the cosine of the angle between them: 1.0 = identical meaning,
    0.0 = unrelated.
    """
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


async def embed_item(item_id: str, item_type: str, text: str) -> bool:
    """Generate and store a summary embedding for one item.

    Returns True if successful, False otherwise.
    """
    from .database import save_embedding

    try:
        content_type = f"{item_type}_summary"
        vectors = generate_embeddings([text], input_type="document")
        vector = vectors[0]

        emb = Embedding(
            item_id=item_id,
            item_type=item_type,
            content_type=content_type,
            vector=vector,
        )
        await save_embedding(emb, embedding_to_bytes(vector))
        return True
    except Exception as e:
        logger.error(f"Failed to embed {item_type} {item_id}: {e}")
        return False


async def search(query: str, limit: int = 10) -> list[tuple[str, str, float]]:
    """Search for items by semantic similarity to the query.

    Embeds the query, compares against all stored embeddings, and returns
    the top matches sorted by similarity score.

    Returns list of (item_id, item_type, score) tuples, deduplicated by
    item — if multiple embeddings for the same item match (e.g. summary
    and chunks), only the highest-scoring one is kept.
    """
    from .database import get_all_embeddings

    # Embed the query using "query" input_type for better search quality
    query_vectors = generate_embeddings([query], input_type="query")
    query_vec = np.array(query_vectors[0], dtype=np.float32)

    # Load all stored embeddings and compute similarity
    all_embeddings = await get_all_embeddings()
    if not all_embeddings:
        return []

    # Score each embedding, keeping only the best score per item
    best_scores: dict[tuple[str, str], float] = {}  # (item_id, item_type) -> score
    for emb, raw_bytes in all_embeddings:
        stored_vec = bytes_to_embedding(raw_bytes)
        score = cosine_similarity(query_vec, stored_vec)

        key = (emb.item_id, emb.item_type)
        if key not in best_scores or score > best_scores[key]:
            best_scores[key] = score

    # Sort by score descending, take top N
    ranked = sorted(best_scores.items(), key=lambda x: x[1], reverse=True)
    return [
        (item_id, item_type, score)
        for (item_id, item_type), score in ranked[:limit]
    ]
