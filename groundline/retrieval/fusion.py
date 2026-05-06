from __future__ import annotations

from groundline.core.schemas import RetrievalHit


def reciprocal_rank_fusion(
    ranked_lists: list[list[RetrievalHit]],
    k: int = 60,
    top_n: int = 100,
) -> list[RetrievalHit]:
    scores: dict[str, float] = {}
    best_hit: dict[str, RetrievalHit] = {}

    for results in ranked_lists:
        for rank, hit in enumerate(results, start=1):
            scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + 1.0 / (k + rank)
            best_hit.setdefault(chunk_id := hit.chunk_id, hit)

    fused: list[RetrievalHit] = []
    for chunk_id, score in scores.items():
        hit = best_hit[chunk_id].model_copy(update={"score": score, "source": "rrf"})
        fused.append(hit)

    return sorted(fused, key=lambda hit: hit.score, reverse=True)[:top_n]

