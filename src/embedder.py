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
