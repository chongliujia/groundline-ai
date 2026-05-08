import os
from pathlib import Path

import pytest
from qdrant_client import QdrantClient
from qdrant_client.http import models

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
        doc_id = ingest.documents[0].doc_id

        assert ingest.documents[0].chunk_count >= 1
        assert _count_doc_points(client, collection, doc_id) == ingest.documents[0].chunk_count
        health = engine.collection_health(collection)
        assert health.status == "ready"
        assert health.vector_index.actual_points == ingest.documents[0].chunk_count
        client.delete_collection(collection)
        assert _count_collection_points(client, collection) == 0
        missing_vectors = engine.collection_health(collection)
        assert missing_vectors.status == "needs_reindex"
        assert missing_vectors.vector_index.missing_points == ingest.documents[0].chunk_count

        reindexed = engine.reindex_collection(collection)

        assert reindexed.ok is True
        assert reindexed.chunks_indexed == ingest.documents[0].chunk_count
        assert _count_doc_points(client, collection, doc_id) == ingest.documents[0].chunk_count
        assert engine.collection_health(collection).status == "ready"

        assert result.trace is not None
        assert result.trace["retrieval"]["vector_hits_raw"] > 0
        assert result.trace["retrieval"]["vector_hits"] > 0
        assert result.trace["retrieval"]["vector_candidates"]
        assert any(
            "vector" in context.scores or "rrf_score" in context.scores
            for context in result.contexts
        )

        source.write_text(
            "# Policy\n\n## Meal\n\nmeal reimbursement approval",
            encoding="utf-8",
        )
        updated = engine.ingest_path(source, collection=collection)

        assert updated.documents[0].doc_id == doc_id
        assert _count_doc_points(client, collection, doc_id) == updated.documents[0].chunk_count

        deleted = engine.delete_document(collection, doc_id)

        assert deleted.deleted is True
        assert deleted.vector_points_deleted == updated.documents[0].chunk_count
        assert _count_doc_points(client, collection, doc_id) == 0
    finally:
        try:
            client.delete_collection(collection)
        except Exception:
            pass


def _count_doc_points(client: QdrantClient, collection: str, doc_id: str) -> int:
    if not client.collection_exists(collection):
        return 0
    return int(
        client.count(
            collection_name=collection,
            count_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="doc_id",
                        match=models.MatchValue(value=doc_id),
                    )
                ]
            ),
            exact=True,
        ).count
    )


def _count_collection_points(client: QdrantClient, collection: str) -> int:
    if not client.collection_exists(collection):
        return 0
    return int(client.count(collection_name=collection, exact=True).count)
