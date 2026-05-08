from __future__ import annotations

from fastapi import APIRouter

from groundline.core.config import get_settings
from groundline.core.engine import Groundline
from groundline.core.schemas import ProviderStatusResponse

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("", response_model=ProviderStatusResponse)
def provider_status() -> ProviderStatusResponse:
    engine = Groundline(get_settings())
    return engine.provider_status()
