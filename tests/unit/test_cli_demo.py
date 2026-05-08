from pathlib import Path

from groundline.cli.main import _run_demo_flow
from groundline.core.engine import Groundline


def test_demo_flow_returns_reusable_payload(tmp_path: Path) -> None:
    engine = Groundline.from_local(tmp_path / "data")

    payload = _run_demo_flow(
        engine=engine,
        collection="demo",
        docs_path=Path("examples/quickstart/docs"),
        evalset=Path("examples/quickstart/evalset.example.jsonl"),
        query_text="住宿标准",
        context_window=1,
        data_dir=tmp_path / "data",
    )

    step_names = [step["name"] for step in payload["steps"]]
    run_operations = [run["operation"] for run in payload["runs"]]

    assert step_names == [
        "clear",
        "ingest",
        "health",
        "query",
        "answer",
        "reindex",
        "health_after_reindex",
    ]
    assert payload["ingest"]["documents"]
    assert payload["health"]["status"] == "embedding_disabled"
    assert payload["query_result"]["contexts"]
    assert payload["eval"]["metrics"]["queries"] >= 1
    assert all(step["ok"] for step in payload["steps"])
    assert "query" in run_operations
    assert payload["runs"][0]["operation"] == "health"
