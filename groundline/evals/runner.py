from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from groundline.core.engine import Groundline
from groundline.core.schemas import (
    EvalItem,
    EvalMetrics,
    EvalQueryResult,
    EvalReport,
    EvalRetrievedContext,
)
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
    query_results = [
        _score_item(engine, collection, item, tenant_id=tenant_id, top_k=top_k)
        for item in items
    ]
    by_type: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for result in query_results:
        by_type[result.query_type].append((result.recall_at_k, result.mrr))

    return EvalReport(
        collection=collection,
        top_k=top_k,
        metrics=_aggregate([(result.recall_at_k, result.mrr) for result in query_results]),
        by_query_type={
            query_type: _aggregate(scores) for query_type, scores in sorted(by_type.items())
        },
        queries=query_results,
    )


def _score_item(
    engine: Groundline,
    collection: str,
    item: EvalItem,
    tenant_id: str,
    top_k: int,
) -> EvalQueryResult:
    result = engine.query(
        collection=collection,
        query=item.query,
        tenant_id=tenant_id,
        top_k=top_k,
        include_trace=True,
    )
    result_chunk_ids = [context.chunk_id for context in result.contexts]
    result_doc_ids = [context.doc_id for context in result.contexts]
    resolved_gold_doc_ids = _resolve_gold_doc_ids(engine, collection, item)

    if item.gold_chunk_ids:
        gold = set(item.gold_chunk_ids)
        results = result_chunk_ids
    else:
        gold = set(resolved_gold_doc_ids)
        results = result_doc_ids

    matched_chunk_ids = _ordered_matches(result_chunk_ids[:top_k], set(item.gold_chunk_ids))
    matched_doc_ids = _ordered_matches(result_doc_ids[:top_k], set(resolved_gold_doc_ids))
    recall = recall_at_k(results, gold, top_k)
    mrr = mean_reciprocal_rank(results, gold)
    return EvalQueryResult(
        query=item.query,
        query_type=item.query_type,
        gold_chunk_ids=item.gold_chunk_ids,
        gold_doc_ids=item.gold_doc_ids,
        gold_source_uris=item.gold_source_uris,
        resolved_gold_doc_ids=resolved_gold_doc_ids,
        retrieved=[
            EvalRetrievedContext(
                rank=rank,
                chunk_id=context.chunk_id,
                doc_id=context.doc_id,
                title=context.title,
                section=context.section,
                scores=context.scores,
            )
            for rank, context in enumerate(result.contexts, start=1)
        ],
        recall_at_k=recall,
        mrr=mrr,
        hit=recall > 0,
        first_hit_rank=_first_hit_rank(results, gold),
        matched_doc_ids=matched_doc_ids,
        matched_chunk_ids=matched_chunk_ids,
        trace=_eval_trace_summary(result.trace),
    )


def _aggregate(scores: list[tuple[float, float]]) -> EvalMetrics:
    if not scores:
        return EvalMetrics(recall_at_k=0.0, mrr=0.0, queries=0)
    return EvalMetrics(
        recall_at_k=sum(score[0] for score in scores) / len(scores),
        mrr=sum(score[1] for score in scores) / len(scores),
        queries=len(scores),
    )


def _resolve_gold_doc_ids(
    engine: Groundline,
    collection: str,
    item: EvalItem,
) -> list[str]:
    doc_ids = list(item.gold_doc_ids)
    if not item.gold_source_uris:
        return doc_ids

    source_uri_to_doc_id = {
        document.source_uri: document.doc_id
        for document in engine.list_documents(collection, include_inactive=True)
    }
    for source_uri in item.gold_source_uris:
        doc_id = source_uri_to_doc_id.get(source_uri)
        if doc_id is not None and doc_id not in doc_ids:
            doc_ids.append(doc_id)
    return doc_ids


def _first_hit_rank(results: list[str], gold: set[str]) -> int | None:
    for rank, result in enumerate(results, start=1):
        if result in gold:
            return rank
    return None


def _ordered_matches(results: list[str], gold: set[str]) -> list[str]:
    matches: list[str] = []
    seen: set[str] = set()
    for result in results:
        if result in gold and result not in seen:
            matches.append(result)
            seen.add(result)
    return matches


def _eval_trace_summary(trace: dict | None) -> dict | None:
    if trace is None:
        return None
    return {
        "routing": trace.get("routing", {}),
        "retrieval": trace.get("retrieval", {}),
        "fusion": trace.get("fusion", {}),
        "rerank": trace.get("rerank", {}),
        "context": trace.get("context", {}),
    }
