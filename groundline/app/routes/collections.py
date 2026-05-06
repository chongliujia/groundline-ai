from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from groundline.core.config import get_settings
from groundline.core.engine import Groundline
from groundline.core.schemas import DeleteResponse, IngestRequest, IngestResponse

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
