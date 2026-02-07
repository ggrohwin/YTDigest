"""Tests for embedding generation and search utilities."""

import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from types import SimpleNamespace

from src.embedder import (
    is_available,
    generate_embeddings,
    embedding_to_bytes,
    bytes_to_embedding,
    cosine_similarity,
)


class TestIsAvailable:
    """Tests for the is_available() check."""

    def test_available_when_key_set(self, monkeypatch):
        monkeypatch.setenv("VOYAGE_API_KEY", "test-key-123")
        assert is_available() is True

    def test_unavailable_when_key_missing(self, monkeypatch):
        monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
        assert is_available() is False

    def test_unavailable_when_key_empty(self, monkeypatch):
        monkeypatch.setenv("VOYAGE_API_KEY", "")
        assert is_available() is False


class TestGenerateEmbeddings:
    """Tests for generate_embeddings() with mocked Voyage AI."""

    @patch("src.embedder.voyageai")
    def test_generates_embeddings(self, mock_voyageai, monkeypatch):
        """Test that generate_embeddings calls Voyage AI correctly."""
        monkeypatch.setenv("VOYAGE_API_KEY", "test-key")

        # Mock the Voyage AI client and its response
        mock_client = MagicMock()
        mock_voyageai.Client.return_value = mock_client
        mock_client.embed.return_value = SimpleNamespace(
            embeddings=[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        )

        result = generate_embeddings(["hello", "world"], input_type="document")

        # Verify the client was created with our API key
        mock_voyageai.Client.assert_called_once_with(api_key="test-key")
        # Verify embed was called with correct params
        mock_client.embed.assert_called_once_with(
            ["hello", "world"],
            model="voyage-3-lite",
            input_type="document",
        )
        assert result == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]

    @patch("src.embedder.voyageai")
    def test_query_input_type(self, mock_voyageai, monkeypatch):
        """Test that query input_type is passed through."""
        monkeypatch.setenv("VOYAGE_API_KEY", "test-key")
        mock_client = MagicMock()
        mock_voyageai.Client.return_value = mock_client
        mock_client.embed.return_value = SimpleNamespace(embeddings=[[0.1]])

        generate_embeddings(["search query"], input_type="query")

        mock_client.embed.assert_called_once_with(
            ["search query"],
            model="voyage-3-lite",
            input_type="query",
        )

    def test_raises_without_api_key(self, monkeypatch):
        """Test that missing API key raises RuntimeError."""
        monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="VOYAGE_API_KEY"):
            generate_embeddings(["test"])


class TestBytesRoundTrip:
    """Tests for embedding_to_bytes / bytes_to_embedding serialization."""

    def test_round_trip(self):
        """Embedding -> bytes -> embedding preserves values."""
        original = [0.1, -0.2, 0.3, 0.0, 1.0]
        raw_bytes = embedding_to_bytes(original)
        recovered = bytes_to_embedding(raw_bytes)
        np.testing.assert_array_almost_equal(recovered, original)

    def test_bytes_are_float32(self):
        """Serialized bytes should be float32 (4 bytes per number)."""
        vector = [1.0, 2.0, 3.0]
        raw_bytes = embedding_to_bytes(vector)
        assert len(raw_bytes) == 3 * 4  # 3 floats * 4 bytes each

    def test_empty_vector(self):
        """Empty vector round-trips correctly."""
        raw_bytes = embedding_to_bytes([])
        recovered = bytes_to_embedding(raw_bytes)
        assert len(recovered) == 0


class TestCosineSimilarity:
    """Tests for cosine_similarity()."""

    def test_identical_vectors(self):
        """Identical vectors should have similarity 1.0."""
        a = np.array([1.0, 0.0, 0.0])
        b = np.array([1.0, 0.0, 0.0])
        assert cosine_similarity(a, b) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        """Perpendicular vectors should have similarity 0.0."""
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 1.0])
        assert cosine_similarity(a, b) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        """Opposite vectors should have similarity -1.0."""
        a = np.array([1.0, 0.0])
        b = np.array([-1.0, 0.0])
        assert cosine_similarity(a, b) == pytest.approx(-1.0)

    def test_similar_vectors(self):
        """Similar vectors should have high positive similarity."""
        a = np.array([1.0, 1.0, 0.0])
        b = np.array([1.0, 0.9, 0.1])
        score = cosine_similarity(a, b)
        assert score > 0.9

    def test_zero_vector_returns_zero(self):
        """A zero vector should return 0.0 (not NaN or error)."""
        a = np.array([0.0, 0.0, 0.0])
        b = np.array([1.0, 2.0, 3.0])
        assert cosine_similarity(a, b) == 0.0

    def test_magnitude_irrelevant(self):
        """Cosine similarity should be independent of vector magnitude."""
        a = np.array([1.0, 2.0, 3.0])
        b = np.array([2.0, 4.0, 6.0])  # same direction, 2x magnitude
        assert cosine_similarity(a, b) == pytest.approx(1.0)
