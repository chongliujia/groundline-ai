from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from groundline.core.config import get_settings
from groundline.core.demo import run_demo_flow
from groundline.core.engine import Groundline
from groundline.core.schemas import DemoReport, DemoRequest

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("", response_model=DemoReport)
def run_demo(request: DemoRequest | None = None) -> DemoReport:
    request = request or DemoRequest()
    settings = get_settings()
    engine = Groundline(settings)
    return run_demo_flow(
        engine=engine,
        collection=request.collection,
        docs_path=Path(request.docs_path),
        evalset=Path(request.evalset),
        query_text=request.query_text,
        context_window=request.context_window,
        data_dir=settings.data_dir,
    )
