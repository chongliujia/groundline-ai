import os
from pathlib import Path

import pytest
from qdrant_client import QdrantClient

from groundline.core.config import Settings
from groundline.core.engine import Groundline

pytestmark = pytest.mark.skipif(
    os.getenv("GROUNDLINE_TEST_QDRANT") != "1",
    reason="Set GROUNDLINE_TEST_QDRANT=1 and run Qdrant to enable this test.",
)


def test_qdrant_vector_path_with_hash_embedder(tmp_path: Path) -> None:
    qdrant_url = os.getenv("GROUNDLINE_QDRANT_URL", "http://localhost:6333")
    client = QdrantClient(url=qdrant_url)
    try:
        client.get_collections()
    except Exception as error:
        pytest.skip(f"Qdrant is not reachable at {qdrant_url}: {error}")

    config = tmp_path / "groundline.toml"
    config.write_text(
        """
        [embedding]
        provider = "hash"
        dimension = 64
        """,
        encoding="utf-8",
    )
    source = tmp_path / "policy.md"
    source.write_text(
        "# Policy\n\n## Hotel\n\nhotel standard reimbursement approval",
        encoding="utf-8",
    )
    collection = f"test_groundline_{os.getpid()}"
    engine = Groundline(
        Settings(
            data_dir=tmp_path / "data",
            provider_config_path=config,
            qdrant_url=qdrant_url,
        )
    )

    try:
        ingest = engine.ingest_path(source, collection=collection)
        result = engine.query(
            collection,
            "hotel standard",
            include_trace=True,
            top_k=3,
        )

        assert ingest.documents[0].chunk_count >= 1
        assert result.trace is not None
        assert result.trace["retrieval"]["vector_hits_raw"] > 0
        assert result.trace["retrieval"]["vector_hits"] > 0
        assert result.trace["retrieval"]["vector_candidates"]
        assert any(
            "vector" in context.scores or "rrf_score" in context.scores
            for context in result.contexts
        )
    finally:
        try:
            client.delete_collection(collection)
        except Exception:
            pass
