from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from groundline.core.engine import Groundline
from groundline.core.schemas import EvalItem, EvalMetrics, EvalReport
from groundline.evals.dataset import load_eval_dataset
from groundline.evals.metrics import mean_reciprocal_rank, recall_at_k


def run_eval(
    engine: Groundline,
    collection: str,
    dataset_path: Path,
    tenant_id: str = "default",
    top_k: int = 8,
) -> EvalReport:
    items = load_eval_dataset(dataset_path)
    scored_items = [
        _score_item(engine, collection, item, tenant_id=tenant_id, top_k=top_k)
        for item in items
    ]
    by_type: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for item, recall, mrr in scored_items:
        by_type[item.query_type].append((recall, mrr))

    return EvalReport(
        collection=collection,
        top_k=top_k,
        metrics=_aggregate([(recall, mrr) for _, recall, mrr in scored_items]),
        by_query_type={
            query_type: _aggregate(scores) for query_type, scores in sorted(by_type.items())
        },
    )


def _score_item(
    engine: Groundline,
    collection: str,
    item: EvalItem,
    tenant_id: str,
    top_k: int,
) -> tuple[EvalItem, float, float]:
    result = engine.query(
        collection=collection,
        query=item.query,
        tenant_id=tenant_id,
        top_k=top_k,
    )
    result_chunk_ids = [context.chunk_id for context in result.contexts]
    result_doc_ids = [context.doc_id for context in result.contexts]

    if item.gold_chunk_ids:
        gold = set(item.gold_chunk_ids)
        results = result_chunk_ids
    else:
        gold = set(item.gold_doc_ids)
        results = result_doc_ids

    return item, recall_at_k(results, gold, top_k), mean_reciprocal_rank(results, gold)


def _aggregate(scores: list[tuple[float, float]]) -> EvalMetrics:
    if not scores:
        return EvalMetrics(recall_at_k=0.0, mrr=0.0, queries=0)
    return EvalMetrics(
        recall_at_k=sum(score[0] for score in scores) / len(scores),
        mrr=sum(score[1] for score in scores) / len(scores),
        queries=len(scores),
    )

