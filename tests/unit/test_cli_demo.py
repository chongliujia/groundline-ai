from pathlib import Path

from groundline.core.demo import run_demo_flow
from groundline.core.engine import Groundline


def test_demo_flow_returns_reusable_payload(tmp_path: Path) -> None:
    engine = Groundline.from_local(tmp_path / "data")

    report = run_demo_flow(
        engine=engine,
        collection="demo",
        docs_path=Path("examples/quickstart/docs"),
        evalset=Path("examples/quickstart/evalset.example.jsonl"),
        query_text="住宿标准",
        context_window=1,
        data_dir=tmp_path / "data",
    )

    step_names = [step.name for step in report.steps]
    run_operations = [run.operation for run in report.runs]

    assert step_names == [
        "clear",
        "ingest",
        "health",
        "query",
        "answer",
        "reindex",
        "health_after_reindex",
    ]
    assert report.ingest.documents
    assert report.health.status == "embedding_disabled"
    assert report.query_result.contexts
    assert report.eval.metrics.queries >= 1
    assert all(step.ok for step in report.steps)
    assert "query" in run_operations
    assert report.runs[0].operation == "health"
