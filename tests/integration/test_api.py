import json
from pathlib import Path

from fastapi.testclient import TestClient

from groundline.app.main import create_app


def test_api_smoke_flow(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GROUNDLINE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("GROUNDLINE_PROVIDER_CONFIG_PATH", str(tmp_path / "missing.toml"))
    monkeypatch.setenv("GROUNDLINE_EMBEDDING_API_KEY", "secret")
    source = tmp_path / "policy.md"
    source.write_text(
        "# Policy\n\n## Hotel\n\n差旅住宿标准是一线城市 800 元。",
        encoding="utf-8",
    )
    client = TestClient(create_app())

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}

    providers = client.get("/providers")
    assert providers.status_code == 200
    assert providers.json()["providers"][0]["name"] == "llm"
    assert "secret" not in providers.text

    created = client.post("/collections", params={"name": "demo"})
    assert created.status_code == 200
    assert created.json()["status"] == "created"

    collections = client.get("/collections")
    assert collections.status_code == 200
    assert collections.json()["collections"] == ["demo"]

    ingest = client.post(
        "/collections/demo/ingest",
        json={"source_uri": str(source), "tenant_id": "default"},
    )
    assert ingest.status_code == 200
    ingest_payload = ingest.json()
    assert ingest_payload["collection"] == "demo"
    assert len(ingest_payload["documents"]) == 1
    assert ingest_payload["pipeline"]["operation"] == "ingest"
    assert ingest_payload["pipeline"]["events"]
    doc_id = ingest_payload["documents"][0]["doc_id"]

    duplicate = client.post(
        "/collections/demo/ingest",
        json={"source_uri": str(source), "tenant_id": "default"},
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["documents"] == []
    assert duplicate.json()["skipped"][0]["reason"] == "unchanged content hash"

    documents = client.get("/collections/demo/documents")
    assert documents.status_code == 200
    assert documents.json()["documents"][0]["doc_id"] == doc_id

    document_detail = client.get(f"/collections/demo/documents/{doc_id}")
    assert document_detail.status_code == 200
    assert document_detail.json()["document"]["doc_id"] == doc_id
    assert document_detail.json()["active_chunk_count"] >= 1
    assert document_detail.json()["latest_chunk_count"] >= 1

    versions = client.get(f"/collections/demo/documents/{doc_id}/versions")
    assert versions.status_code == 200
    assert versions.json()["versions"][0]["doc_id"] == doc_id

    chunks = client.get("/collections/demo/chunks")
    assert chunks.status_code == 200
    assert chunks.json()["chunks"]

    reindex = client.post("/collections/demo/reindex")
    assert reindex.status_code == 200
    assert reindex.json()["ok"] is False
    assert reindex.json()["reason"] == "embedding disabled"
    assert reindex.json()["pipeline"]["operation"] == "reindex"

    collection_health = client.get("/collections/demo/health")
    assert collection_health.status_code == 200
    assert collection_health.json()["status"] == "embedding_disabled"
    assert collection_health.json()["documents_total"] == 1
    assert collection_health.json()["latest_chunks"] >= 1
    assert collection_health.json()["documents"][0]["doc_id"] == doc_id
    assert collection_health.json()["pipeline"]["operation"] == "health"

    query = client.post(
        "/collections/demo/query",
        json={
            "query": "住宿标准",
            "tenant_id": "default",
            "context_window": 1,
            "max_context_chars": 12000,
            "include_trace": True,
        },
    )
    assert query.status_code == 200
    assert query.json()["contexts"][0]["doc_id"] == doc_id
    assert query.json()["trace"]["retrieval"]["bm25_hits"] >= 1
    assert query.json()["trace"]["retrieval"]["bm25_candidates"][0]["doc_id"] == doc_id
    assert query.json()["trace"]["fusion"]["candidates"]
    assert query.json()["trace"]["context"]["contexts"][0]["doc_id"] == doc_id
    assert query.json()["trace"]["context"]["context_window"] == 1
    assert query.json()["contexts"][0]["metadata"]["packed_chunk_ids"]
    assert query.json()["pipeline"]["operation"] == "query"

    filtered_out = client.post(
        "/collections/demo/query",
        json={
            "query": "住宿标准",
            "tenant_id": "default",
            "filters": {"domain": "engineering"},
        },
    )
    assert filtered_out.status_code == 200
    assert filtered_out.json()["contexts"] == []

    answer = client.post(
        "/collections/demo/answer",
        json={"query": "住宿标准", "tenant_id": "default", "include_trace": True},
    )
    assert answer.status_code == 200
    assert answer.json()["answer"] is None
    assert answer.json()["error"] == "llm disabled"
    assert answer.json()["contexts"][0]["doc_id"] == doc_id
    assert answer.json()["trace"]["context"]["final_items"] >= 1
    assert answer.json()["pipeline"]["operation"] == "answer"

    evalset = tmp_path / "eval.jsonl"
    evalset.write_text(
        json.dumps(
            {
                "query": "住宿标准",
                "gold_doc_ids": [doc_id],
                "query_type": "exact",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    report = client.post(
        "/collections/demo/eval",
        json={"dataset_path": str(evalset), "tenant_id": "default", "top_k": 3},
    )
    assert report.status_code == 200
    assert report.json()["metrics"]["recall_at_k"] == 1.0
    assert report.json()["queries"][0]["hit"] is True
    assert report.json()["queries"][0]["first_hit_rank"] == 1
    assert report.json()["queries"][0]["retrieved"][0]["doc_id"] == doc_id
    assert report.json()["queries"][0]["trace"]["retrieval"]["bm25_candidates"]

    deleted = client.delete(f"/collections/demo/documents/{doc_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert deleted.json()["vector_points_deleted"] == 0
    assert deleted.json()["pipeline"]["operation"] == "delete"

    query_after_delete = client.post(
        "/collections/demo/query",
        json={"query": "住宿标准", "tenant_id": "default"},
    )
    assert query_after_delete.status_code == 200
    assert query_after_delete.json()["contexts"] == []

    hidden = client.get("/collections/demo/documents")
    assert hidden.status_code == 200
    assert hidden.json()["documents"] == []

    inactive = client.get("/collections/demo/documents", params={"include_inactive": True})
    assert inactive.status_code == 200
    assert inactive.json()["documents"][0]["is_active"] is False

    hidden_detail = client.get(f"/collections/demo/documents/{doc_id}")
    assert hidden_detail.status_code == 404

    inactive_detail = client.get(
        f"/collections/demo/documents/{doc_id}",
        params={"include_inactive": True},
    )
    assert inactive_detail.status_code == 200
    assert inactive_detail.json()["document"]["is_active"] is False

    scratch_created = client.post("/collections", params={"name": "scratch"})
    assert scratch_created.status_code == 200
    scratch_ingest = client.post(
        "/collections/scratch/ingest",
        json={"source_uri": str(source), "tenant_id": "default"},
    )
    assert scratch_ingest.status_code == 200
    scratch_clear = client.post("/collections/scratch/clear")
    assert scratch_clear.status_code == 200
    assert scratch_clear.json()["ok"] is True
    assert scratch_clear.json()["documents_removed"] == 1
    assert scratch_clear.json()["pipeline"]["operation"] == "clear"
    assert client.get("/collections/scratch/documents").json()["documents"] == []

    scratch_ingest_again = client.post(
        "/collections/scratch/ingest",
        json={"source_uri": str(source), "tenant_id": "default"},
    )
    assert scratch_ingest_again.status_code == 200
    scratch_delete = client.delete("/collections/scratch")
    assert scratch_delete.status_code == 200
    assert scratch_delete.json()["ok"] is True
    assert scratch_delete.json()["operation"] == "delete"
    assert scratch_delete.json()["pipeline"]["operation"] == "delete"
    assert "scratch" not in client.get("/collections").json()["collections"]
