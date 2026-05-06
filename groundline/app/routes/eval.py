from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from groundline.core.config import get_settings
from groundline.core.engine import Groundline
from groundline.core.schemas import EvalReport, EvalRequest
from groundline.evals.runner import run_eval

router = APIRouter(prefix="/collections/{collection_name}", tags=["eval"])


@router.post("/eval", response_model=EvalReport)
def eval_collection(collection_name: str, request: EvalRequest) -> EvalReport:
    engine = Groundline(get_settings())
    return run_eval(
        engine=engine,
        collection=collection_name,
        dataset_path=Path(request.dataset_path),
        tenant_id=request.tenant_id,
        top_k=request.top_k,
    )

