import json
from pathlib import Path

from groundline.core.engine import Groundline
from groundline.evals.dataset import load_eval_dataset
from groundline.evals.metrics import mean_reciprocal_rank, recall_at_k
from groundline.evals.runner import run_eval


def test_eval_metrics() -> None:
    assert recall_at_k(["a", "b"], {"b"}, 2) == 1.0
    assert mean_reciprocal_rank(["a", "b"], {"b"}) == 0.5


def test_load_eval_dataset(tmp_path: Path) -> None:
    path = tmp_path / "eval.jsonl"
    path.write_text('{"query":"hello","gold_doc_ids":["doc_1"]}\n', encoding="utf-8")

    items = load_eval_dataset(path)

    assert len(items) == 1
    assert items[0].query == "hello"
    assert items[0].query_type == "default"


def test_run_eval_with_gold_doc_ids(tmp_path: Path) -> None:
    source = tmp_path / "policy.md"
    source.write_text("# Policy\n\n## Hotel\n\n住宿标准是一线城市 800 元。", encoding="utf-8")
    engine = Groundline.from_local(tmp_path / "data")
    ingest = engine.ingest_path(source, collection="demo")

    evalset = tmp_path / "eval.jsonl"
    evalset.write_text(
        json.dumps(
            {
                "query": "住宿标准",
                "gold_doc_ids": [ingest.documents[0].doc_id],
                "query_type": "exact",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = run_eval(engine, "demo", evalset, top_k=3)

    assert report.metrics.queries == 1
    assert report.metrics.recall_at_k == 1.0
    assert report.metrics.mrr == 1.0
    assert report.by_query_type["exact"].queries == 1
