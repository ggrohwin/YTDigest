"""Tests for embedding generation and search utilities."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src import database
from src.embedder import (
    bytes_to_embedding,
    chunk_text,
    cosine_similarity,
    embed_item,
    embed_item_chunks,
    embedding_to_bytes,
    generate_embeddings,
    is_available,
    search,
)
from src.models import Embedding


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


class TestEmbedItem:
    """Tests for embed_item() — generates and stores an embedding for one item."""

    @pytest.fixture
    async def test_db(self, tmp_path, monkeypatch):
        """Create a temporary database for testing."""
        db_path = tmp_path / "test.db"
        monkeypatch.setattr(database, "DATABASE_PATH", db_path)
        await database.init_db()
        yield db_path

    @patch("src.embedder.generate_embeddings")
    async def test_embed_item_success(self, mock_gen, test_db):
        """embed_item should generate a vector and store it in the database."""
        mock_gen.return_value = [[0.1, 0.2, 0.3]]

        result = await embed_item("vid1", "video", "Some summary text")

        assert result is True
        mock_gen.assert_called_once_with(["Some summary text"], input_type="document")

        # Verify it was stored in the database
        stored = await database.get_embedding("vid1", "video_summary")
        assert stored is not None

    @patch("src.embedder.generate_embeddings")
    async def test_embed_item_failure(self, mock_gen, test_db):
        """embed_item should return False if embedding generation fails."""
        mock_gen.side_effect = RuntimeError("API error")

        result = await embed_item("vid1", "video", "Some text")

        assert result is False
        # Nothing stored
        stored = await database.get_embedding("vid1", "video_summary")
        assert stored is None


class TestSearch:
    """Tests for the search() function with known vectors."""

    @pytest.fixture
    async def test_db(self, tmp_path, monkeypatch):
        """Create a temporary database for testing."""
        db_path = tmp_path / "test.db"
        monkeypatch.setattr(database, "DATABASE_PATH", db_path)
        await database.init_db()
        yield db_path

    async def _store_embedding(self, item_id, item_type, content_type, vector):
        """Helper to store an embedding directly in the database."""
        emb = Embedding(
            item_id=item_id,
            item_type=item_type,
            content_type=content_type,
            vector=vector,
        )
        await database.save_embedding(emb, embedding_to_bytes(vector))

    @patch("src.embedder.generate_embeddings")
    async def test_search_returns_ranked_results(self, mock_gen, test_db):
        """Search should return items ranked by similarity to the query."""
        # Store two embeddings: both with decent similarity to the query
        await self._store_embedding("vid1", "video", "video_summary", [1.0, 0.0, 0.0])
        await self._store_embedding("vid2", "video", "video_summary", [0.8, 0.6, 0.0])

        # Mock the query embedding to be close to vid1
        mock_gen.return_value = [[0.9, 0.1, 0.0]]

        results = await search("machine learning", limit=10)

        assert len(results) == 2
        # vid1 should rank first (closer to query)
        assert results[0][0] == "vid1"
        assert results[0][2] > results[1][2]  # higher score
        # Verify generate_embeddings was called with query input_type
        mock_gen.assert_called_once_with(["machine learning"], input_type="query")

    @patch("src.embedder.generate_embeddings")
    async def test_search_filters_low_similarity(self, mock_gen, test_db):
        """Search should exclude results below the MIN_SIMILARITY threshold."""
        # vid1 is close to query, vid2 is orthogonal (low similarity)
        await self._store_embedding("vid1", "video", "video_summary", [1.0, 0.0, 0.0])
        await self._store_embedding("vid2", "video", "video_summary", [0.0, 1.0, 0.0])

        # Query is close to vid1, orthogonal to vid2 (similarity ~0.11)
        mock_gen.return_value = [[0.9, 0.1, 0.0]]

        results = await search("test", limit=10)

        # vid2 should be filtered out (cosine sim ~0.11 < 0.3)
        assert len(results) == 1
        assert results[0][0] == "vid1"

    @patch("src.embedder.generate_embeddings")
    async def test_search_respects_limit(self, mock_gen, test_db):
        """Search should return at most 'limit' results."""
        for i in range(5):
            await self._store_embedding(
                f"vid{i}", "video", "video_summary", [float(i), 1.0, 0.0]
            )

        mock_gen.return_value = [[3.0, 1.0, 0.0]]
        results = await search("test", limit=2)

        assert len(results) == 2

    @patch("src.embedder.generate_embeddings")
    async def test_search_empty_database(self, mock_gen, test_db):
        """Search with no stored embeddings should return empty list."""
        mock_gen.return_value = [[1.0, 0.0, 0.0]]
        results = await search("anything")
        assert results == []

    @patch("src.embedder.generate_embeddings")
    async def test_search_deduplicates_by_item(self, mock_gen, test_db):
        """Multiple embeddings for the same item should be deduplicated."""
        # Same item, two embeddings (summary and chunk)
        await self._store_embedding("vid1", "video", "video_summary", [1.0, 0.0, 0.0])
        await self._store_embedding("vid1", "video", "video_chunk", [0.9, 0.1, 0.0])

        mock_gen.return_value = [[1.0, 0.0, 0.0]]
        results = await search("test")

        # Should appear only once, with the best score
        assert len(results) == 1
        assert results[0][0] == "vid1"
        assert results[0][2] == pytest.approx(1.0)  # the exact match


class TestChunkText:
    """Tests for chunk_text() — splitting text into overlapping word chunks."""

    def test_short_text_returns_single_chunk(self):
        """Text shorter than chunk_size should return as one chunk."""
        text = "This is a short piece of text."
        chunks = chunk_text(text, chunk_size=500, overlap=100)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_empty_text_returns_empty(self):
        """Empty text should return no chunks."""
        assert chunk_text("") == []
        assert chunk_text("   ") == []

    def test_exact_chunk_size(self):
        """Text with exactly chunk_size words should return one chunk."""
        words = ["word"] * 500
        text = " ".join(words)
        chunks = chunk_text(text, chunk_size=500, overlap=100)
        assert len(chunks) == 1

    def test_overlap_between_chunks(self):
        """Adjacent chunks should share 'overlap' words."""
        # Create text with 1000 unique words so we can verify overlap
        words = [f"w{i}" for i in range(1000)]
        text = " ".join(words)

        chunks = chunk_text(text, chunk_size=500, overlap=100)
        assert len(chunks) >= 2

        # Check that chunks overlap: last 100 words of chunk 0 == first 100 of chunk 1
        chunk0_words = chunks[0].split()
        chunk1_words = chunks[1].split()
        assert chunk0_words[-100:] == chunk1_words[:100]

    def test_chunk_count(self):
        """Verify approximate number of chunks for known input size."""
        # 1000 words, chunk_size=500, overlap=100, step=400
        # chunks: 0-500, 400-900, 800-1000 = 3 chunks
        words = [f"w{i}" for i in range(1000)]
        text = " ".join(words)
        chunks = chunk_text(text, chunk_size=500, overlap=100)
        assert len(chunks) == 3

    def test_all_words_covered(self):
        """Every word in the original text should appear in at least one chunk."""
        words = [f"w{i}" for i in range(1234)]
        text = " ".join(words)
        chunks = chunk_text(text, chunk_size=500, overlap=100)

        all_chunk_words = set()
        for chunk in chunks:
            all_chunk_words.update(chunk.split())
        assert all_chunk_words == set(words)


class TestEmbedItemChunks:
    """Tests for embed_item_chunks() — chunking and embedding full text."""

    @pytest.fixture
    async def test_db(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.db"
        monkeypatch.setattr(database, "DATABASE_PATH", db_path)
        await database.init_db()
        yield db_path

    @patch("src.embedder.generate_embeddings")
    async def test_embed_chunks_success(self, mock_gen, test_db):
        """embed_item_chunks should store one embedding per chunk."""
        # Short text = 1 chunk
        mock_gen.return_value = [[0.1, 0.2, 0.3]]

        count = await embed_item_chunks("vid1", "video", "A short transcript.")
        assert count == 1

        # Verify stored as a chunk embedding
        stored = await database.get_embedding("vid1", "video_chunk", chunk_index=0)
        assert stored is not None

    @patch("src.embedder.generate_embeddings")
    async def test_embed_multiple_chunks(self, mock_gen, test_db):
        """Longer text should produce multiple chunk embeddings."""
        # Create text that will produce 3 chunks
        words = [f"word{i}" for i in range(1000)]
        text = " ".join(words)

        # Mock: return a vector for each chunk (3 chunks expected)
        mock_gen.return_value = [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]

        count = await embed_item_chunks("vid1", "video", text)
        assert count == 3

        # Verify each chunk is stored
        for i in range(3):
            stored = await database.get_embedding("vid1", "video_chunk", chunk_index=i)
            assert stored is not None

    @patch("src.embedder.generate_embeddings")
    async def test_embed_chunks_api_failure(self, mock_gen, test_db):
        """API failure should return 0 and not store anything."""
        mock_gen.side_effect = RuntimeError("API error")

        count = await embed_item_chunks("vid1", "video", "Some text")
        assert count == 0

    @patch("src.embedder.generate_embeddings")
    async def test_empty_text_returns_zero(self, mock_gen, test_db):
        """Empty text should return 0 without calling the API."""
        count = await embed_item_chunks("vid1", "video", "")
        assert count == 0
        mock_gen.assert_not_called()
