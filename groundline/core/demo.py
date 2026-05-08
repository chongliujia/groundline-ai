from __future__ import annotations

from pathlib import Path

from groundline.core.engine import Groundline
from groundline.core.schemas import DemoReport, DemoStepReport, PipelineRun
from groundline.evals.runner import run_eval


def run_demo_flow(
    engine: Groundline,
    collection: str,
    docs_path: Path,
    evalset: Path,
    query_text: str,
    context_window: int,
    data_dir: Path,
) -> DemoReport:
    cleared = engine.clear_collection(collection)
    providers_result = engine.provider_status()
    ingest_result = engine.ingest_path(docs_path, collection=collection)
    health_result = engine.collection_health(collection)
    query_result = engine.query(
        collection=collection,
        query=query_text,
        context_window=context_window,
        include_trace=True,
    )
    answer_result = engine.answer(
        collection=collection,
        query=query_text,
        context_window=context_window,
        include_trace=True,
    )
    eval_report = run_eval(
        engine=engine,
        collection=collection,
        dataset_path=evalset,
    )
    reindex_result = engine.reindex_collection(collection)
    health_after_reindex = engine.collection_health(collection)
    runs = engine.list_pipeline_runs(collection=collection, limit=20)
    return DemoReport(
        collection=collection,
        data_dir=str(data_dir),
        docs_path=str(docs_path),
        evalset=str(evalset),
        query=query_text,
        steps=[
            demo_step(
                "clear",
                cleared.pipeline,
                ok=cleared.ok or cleared.reason == "collection not found",
            ),
            demo_step("ingest", ingest_result.pipeline, ok=bool(ingest_result.documents)),
            demo_step("health", health_result.pipeline, ok=health_result.ok),
            demo_step("query", query_result.pipeline, ok=bool(query_result.contexts)),
            demo_step(
                "answer",
                answer_result.pipeline,
                ok=answer_result.error in {None, "llm disabled"},
            ),
            demo_step(
                "reindex",
                reindex_result.pipeline,
                ok=reindex_result.ok or reindex_result.reason == "embedding disabled",
            ),
            demo_step(
                "health_after_reindex",
                health_after_reindex.pipeline,
                ok=health_after_reindex.ok,
            ),
        ],
        providers=providers_result,
        cleared=cleared,
        ingest=ingest_result,
        health=health_result,
        query_result=query_result,
        answer=answer_result,
        eval=eval_report,
        reindex=reindex_result,
        health_after_reindex=health_after_reindex,
        runs=runs,
    )


def demo_step(
    name: str,
    run: PipelineRun | None,
    ok: bool,
) -> DemoStepReport:
    return DemoStepReport(
        name=name,
        ok=ok,
        run_id=run.run_id if run else None,
        status=run.status if run else None,
        events=len(run.events) if run else 0,
    )
