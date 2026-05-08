from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException

from groundline.core.config import get_settings
from groundline.core.engine import Groundline
from groundline.core.schemas import (
    CollectionHealthReport,
    CollectionOperationResponse,
    DeleteResponse,
    DocumentDetail,
    IngestRequest,
    IngestResponse,
    ReindexResponse,
)

router = APIRouter(prefix="/collections", tags=["collections"])


@router.get("")
def list_collections() -> dict[str, list[str]]:
    engine = Groundline(get_settings())
    return {"collections": engine.list_collections()}


@router.post("")
def create_collection(name: str) -> dict[str, str]:
    engine = Groundline(get_settings())
    engine.metadata.create_collection(name)
    return {"name": name, "status": "created"}


@router.get("/{collection_name}/health", response_model=CollectionHealthReport)
def collection_health(
    collection_name: str,
    include_documents: bool = True,
) -> CollectionHealthReport:
    engine = Groundline(get_settings())
    result = engine.collection_health(
        collection_name,
        include_documents=include_documents,
    )
    if not result.exists:
        raise HTTPException(status_code=404, detail=result.reason)
    return result


@router.post("/{collection_name}/clear", response_model=CollectionOperationResponse)
def clear_collection(collection_name: str) -> CollectionOperationResponse:
    engine = Groundline(get_settings())
    result = engine.clear_collection(collection_name)
    if not result.ok:
        raise HTTPException(status_code=404, detail=result.reason)
    return result


@router.post("/{collection_name}/reindex", response_model=ReindexResponse)
def reindex_collection(
    collection_name: str,
    doc_id: str | None = None,
) -> ReindexResponse:
    engine = Groundline(get_settings())
    result = engine.reindex_collection(collection_name, doc_id=doc_id)
    if not result.ok and result.reason in {"collection not found", "document not found"}:
        raise HTTPException(status_code=404, detail=result.reason)
    return result


@router.delete("/{collection_name}", response_model=CollectionOperationResponse)
def delete_collection(collection_name: str) -> CollectionOperationResponse:
    engine = Groundline(get_settings())
    result = engine.delete_collection(collection_name)
    if not result.ok:
        raise HTTPException(status_code=404, detail=result.reason)
    return result


@router.get("/{collection_name}/documents")
def list_documents(
    collection_name: str,
    include_inactive: bool = False,
) -> dict[str, list[dict]]:
    engine = Groundline(get_settings())
    return {
        "documents": [
            document.model_dump(mode="json")
            for document in engine.list_documents(
                collection_name,
                include_inactive=include_inactive,
            )
        ]
    }


@router.get("/{collection_name}/documents/{doc_id}", response_model=DocumentDetail)
def get_document(
    collection_name: str,
    doc_id: str,
    include_inactive: bool = False,
) -> DocumentDetail:
    engine = Groundline(get_settings())
    detail = engine.get_document_detail(
        collection_name,
        doc_id,
        include_inactive=include_inactive,
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="document not found")
    return detail


@router.get("/{collection_name}/documents/{doc_id}/versions")
def list_document_versions(
    collection_name: str,
    doc_id: str,
    include_inactive: bool = False,
) -> dict[str, list[dict]]:
    engine = Groundline(get_settings())
    return {
        "versions": [
            version.model_dump(mode="json")
            for version in engine.list_document_versions(
                collection_name,
                doc_id,
                include_inactive=include_inactive,
            )
        ]
    }


@router.get("/{collection_name}/chunks")
def list_chunks(
    collection_name: str,
    doc_id: str | None = None,
    include_inactive: bool = False,
) -> dict[str, list[dict]]:
    engine = Groundline(get_settings())
    return {
        "chunks": [
            chunk.model_dump(mode="json")
            for chunk in engine.list_chunks(
                collection_name,
                doc_id=doc_id,
                include_inactive=include_inactive,
            )
        ]
    }


@router.post("/{collection_name}/ingest", response_model=IngestResponse)
def ingest(collection_name: str, request: IngestRequest) -> IngestResponse:
    engine = Groundline(get_settings())
    return engine.ingest_path(
        path=Path(request.source_uri),
        collection=collection_name,
        tenant_id=request.tenant_id,
        title=request.title,
        doc_type=request.doc_type,
        domain=request.domain,
        language=request.language,
        acl_groups=request.acl_groups,
        metadata=request.metadata,
    )


@router.delete("/{collection_name}/documents/{doc_id}", response_model=DeleteResponse)
def delete_document(collection_name: str, doc_id: str) -> DeleteResponse:
    engine = Groundline(get_settings())
    return engine.delete_document(collection_name, doc_id)
