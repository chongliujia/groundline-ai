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
    assert result.trace["retrieval"]["bm25_candidates"][0]["chunk_id"] == result.contexts[
        0
    ].chunk_id
    assert result.trace["fusion"]["candidates"][0]["source"] == "rrf"
    assert result.trace["context"]["contexts"][0]["chunk_id"] == result.contexts[0].chunk_id


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
    assert result.trace["rerank"]["candidates"][0]["score"] is not None


def test_engine_query_filters_by_metadata_and_document_fields(tmp_path: Path) -> None:
    policies = tmp_path / "policies"
    policies.mkdir()
    finance = policies / "finance.md"
    finance.write_text("# Finance\n\n住宿标准是一线城市 800 元。", encoding="utf-8")
    engineering = policies / "engineering.md"
    engineering.write_text("# Engineering\n\n住宿标准需要遵守研发出差规则。", encoding="utf-8")

    engine = Groundline.from_local(tmp_path / "data")
    engine.ingest_path(
        finance,
        collection="demo",
        doc_type="policy",
        domain="finance",
        language="zh",
        metadata={"department": "finance"},
    )
    engine.ingest_path(
        engineering,
        collection="demo",
        doc_type="handbook",
        domain="engineering",
        language="zh",
        metadata={"department": "engineering"},
    )

    domain_result = engine.query("demo", "住宿标准", filters={"domain": "finance"})
    metadata_result = engine.query(
        "demo",
        "住宿标准",
        filters={"metadata": {"department": "engineering"}},
        include_trace=True,
    )
    missing_result = engine.query("demo", "住宿标准", filters={"doc_type": "contract"})

    assert domain_result.contexts
    assert domain_result.contexts[0].title == "finance"
    assert all(context.metadata["department"] == "finance" for context in domain_result.contexts)
    assert metadata_result.contexts[0].metadata["department"] == "engineering"
    assert metadata_result.trace is not None
    assert metadata_result.trace["routing"]["filters"] == {
        "metadata": {"department": "engineering"}
    }
    assert missing_result.contexts == []


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
    detail = engine.get_document_detail("demo", first.documents[0].doc_id)

    assert len(second.documents) == 1
    assert second.documents[0].doc_id == first.documents[0].doc_id
    assert second.documents[0].version_id != first.documents[0].version_id
    assert detail is not None
    assert detail.document.current_version_id == second.documents[0].version_id
    assert len(detail.versions) == 2
    assert detail.versions[0].superseded_by == second.documents[0].version_id
    assert detail.versions[1].supersedes == first.documents[0].version_id
    assert detail.chunk_count == 4
    assert detail.active_chunk_count == 2
    assert detail.latest_chunk_count == 2
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
    hidden_detail = engine.get_document_detail("demo", doc_id)
    inactive_detail = engine.get_document_detail("demo", doc_id, include_inactive=True)

    assert deleted.deleted is True
    assert deleted.chunks_deactivated >= 1
    assert hidden_detail is None
    assert inactive_detail is not None
    assert inactive_detail.document.is_active is False
    assert inactive_detail.versions[0].is_active is False
    assert inactive_detail.active_chunk_count == 0
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


def test_engine_clears_and_deletes_collection(tmp_path: Path) -> None:
    source = tmp_path / "policy.md"
    source.write_text("# Policy\n\n## Hotel\n\n住宿标准是一线城市 800 元。", encoding="utf-8")
    engine = Groundline.from_local(tmp_path / "data")
    engine.ingest_path(source, collection="demo")

    cleared = engine.clear_collection("demo")

    assert cleared.ok is True
    assert cleared.operation == "clear"
    assert cleared.documents_removed == 1
    assert cleared.versions_removed == 1
    assert cleared.chunks_removed >= 1
    assert engine.list_collections() == ["demo"]
    assert engine.list_documents("demo") == []
    assert engine.list_chunks("demo") == []

    engine.ingest_path(source, collection="demo")
    deleted = engine.delete_collection("demo")

    assert deleted.ok is True
    assert deleted.operation == "delete"
    assert deleted.documents_removed == 1
    assert "demo" not in engine.list_collections()
    assert engine.list_documents("demo") == []
    assert engine.list_chunks("demo") == []


def test_engine_clear_missing_collection(tmp_path: Path) -> None:
    engine = Groundline.from_local(tmp_path / "data")

    cleared = engine.clear_collection("missing")
    deleted = engine.delete_collection("missing")

    assert cleared.ok is False
    assert cleared.reason == "collection not found"
    assert deleted.ok is False
    assert deleted.reason == "collection not found"
