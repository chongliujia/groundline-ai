from pathlib import Path

from groundline.core.config import Settings
from groundline.core.engine import Groundline


def test_engine_ingests_and_queries_markdown(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    source = docs / "travel.md"
    source.write_text(
        "# Finance Policy\n\n## Travel\n\n差旅住宿标准是一线城市 800 元每晚。",
        encoding="utf-8",
    )

    engine = Groundline.from_local(tmp_path / "data")
    ingest = engine.ingest_path(source, collection="demo")
    result = engine.query("demo", "住宿标准", include_trace=True)

    assert len(ingest.documents) == 1
    assert ingest.documents[0].chunk_count >= 1
    assert result.contexts
    assert result.contexts[0].citation.doc_id == ingest.documents[0].doc_id
    assert result.trace is not None
    assert result.trace["retrieval"]["bm25_hits"] >= 1


def test_engine_skips_reserved_pdf_parser(tmp_path: Path) -> None:
    source = tmp_path / "demo.pdf"
    source.write_bytes(b"%PDF placeholder")

    engine = Groundline.from_local(tmp_path / "data")
    ingest = engine.ingest_path(source, collection="demo")

    assert ingest.documents == []
    assert ingest.skipped
    assert "PDF parsing is reserved" in ingest.skipped[0].reason


def test_engine_keyword_rerank_adds_scores(tmp_path: Path) -> None:
    config_path = tmp_path / "groundline.toml"
    config_path.write_text(
        """
        [rerank]
        provider = "keyword"
        """,
        encoding="utf-8",
    )
    source = tmp_path / "policy.md"
    source.write_text(
        "# Policy\n\n## Travel\n\nTravel reimbursement.\n\n## Hotel\n\n住宿标准是一线城市 800 元。",
        encoding="utf-8",
    )

    engine = Groundline(Settings(data_dir=tmp_path / "data", provider_config_path=config_path))
    engine.ingest_path(source, collection="demo")
    result = engine.query("demo", "住宿标准", include_trace=True)

    assert result.contexts[0].section == "Policy > Hotel"
    assert "rerank_score" in result.contexts[0].scores
    assert result.trace is not None
    assert result.trace["rerank"]["enabled"] is True


def test_engine_lists_collections_documents_and_chunks(tmp_path: Path) -> None:
    source = tmp_path / "policy.md"
    source.write_text("# Policy\n\n## Hotel\n\n住宿标准是一线城市 800 元。", encoding="utf-8")
    engine = Groundline.from_local(tmp_path / "data")
    ingest = engine.ingest_path(source, collection="demo")

    assert engine.list_collections() == ["demo"]
    assert engine.list_documents("demo")[0].doc_id == ingest.documents[0].doc_id
    chunks = engine.list_chunks("demo", doc_id=ingest.documents[0].doc_id)
    assert chunks
    assert all(chunk.doc_id == ingest.documents[0].doc_id for chunk in chunks)


def test_engine_skips_unchanged_source(tmp_path: Path) -> None:
    source = tmp_path / "policy.md"
    source.write_text("# Policy\n\n## Hotel\n\n住宿标准是一线城市 800 元。", encoding="utf-8")
    engine = Groundline.from_local(tmp_path / "data")

    first = engine.ingest_path(source, collection="demo")
    second = engine.ingest_path(source, collection="demo")

    assert len(first.documents) == 1
    assert second.documents == []
    assert second.skipped[0].reason == "unchanged content hash"
    assert len(engine.list_documents("demo")) == 1


def test_engine_reuses_doc_id_for_changed_source(tmp_path: Path) -> None:
    source = tmp_path / "policy.md"
    source.write_text("# Policy\n\n## Hotel\n\n住宿标准是一线城市 800 元。", encoding="utf-8")
    engine = Groundline.from_local(tmp_path / "data")
    first = engine.ingest_path(source, collection="demo")

    source.write_text("# Policy\n\n## Meal\n\n餐补标准是每天 100 元。", encoding="utf-8")
    second = engine.ingest_path(source, collection="demo")
    result = engine.query("demo", "住宿")

    assert len(second.documents) == 1
    assert second.documents[0].doc_id == first.documents[0].doc_id
    assert second.documents[0].version_id != first.documents[0].version_id
    assert len(engine.list_documents("demo")) == 1
    assert len(engine.list_chunks("demo")) == 2
    assert len(engine.list_chunks("demo", include_inactive=True)) == 4
    assert not result.contexts


def test_engine_tombstones_document(tmp_path: Path) -> None:
    source = tmp_path / "policy.md"
    source.write_text("# Policy\n\n## Hotel\n\n住宿标准是一线城市 800 元。", encoding="utf-8")
    engine = Groundline.from_local(tmp_path / "data")
    ingest = engine.ingest_path(source, collection="demo")
    doc_id = ingest.documents[0].doc_id

    deleted = engine.delete_document("demo", doc_id)
    result = engine.query("demo", "住宿标准")

    assert deleted.deleted is True
    assert deleted.chunks_deactivated >= 1
    assert engine.list_documents("demo") == []
    assert engine.list_documents("demo", include_inactive=True)[0].is_active is False
    assert engine.list_chunks("demo") == []
    assert engine.list_chunks("demo", include_inactive=True)
    assert not result.contexts


def test_engine_delete_missing_document(tmp_path: Path) -> None:
    engine = Groundline.from_local(tmp_path / "data")

    deleted = engine.delete_document("demo", "missing")

    assert deleted.deleted is False
    assert deleted.reason == "document not found"
