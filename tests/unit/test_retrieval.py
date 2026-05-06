from groundline.core.schemas import RetrievalHit
from groundline.retrieval.fusion import reciprocal_rank_fusion


def test_rrf_merges_ranked_lists() -> None:
    results = reciprocal_rank_fusion(
        [
            [
                RetrievalHit(chunk_id="a", score=1.0, source="bm25"),
                RetrievalHit(chunk_id="b", score=0.5, source="bm25"),
            ],
            [
                RetrievalHit(chunk_id="b", score=1.0, source="vector"),
                RetrievalHit(chunk_id="c", score=0.5, source="vector"),
            ],
        ],
        top_n=3,
    )

    assert [hit.chunk_id for hit in results] == ["b", "a", "c"]
    assert all(hit.source == "rrf" for hit in results)

