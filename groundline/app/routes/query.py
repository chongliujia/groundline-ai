from __future__ import annotations

from fastapi import APIRouter

from groundline.core.config import get_settings
from groundline.core.engine import Groundline
from groundline.core.schemas import QueryRequest, QueryResponse

router = APIRouter(prefix="/collections/{collection_name}", tags=["query"])


@router.post("/query", response_model=QueryResponse)
def query_collection(collection_name: str, request: QueryRequest) -> QueryResponse:
    engine = Groundline(get_settings())
    return engine.query(
        collection=collection_name,
        query=request.query,
        tenant_id=request.tenant_id,
        user_groups=request.user_groups,
        filters=request.filters,
        top_k=request.top_k,
        include_trace=request.include_trace,
    )
