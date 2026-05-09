from __future__ import annotations

from fastapi import APIRouter, HTTPException

from groundline.core.app_recipe import (
    app_status,
    latest_app_artifact,
    load_app_recipe,
    plan_app_recipe,
    run_app_recipe,
    validate_app_recipe,
)
from groundline.core.config import get_settings
from groundline.core.engine import Groundline
from groundline.core.schemas import (
    AppArtifact,
    AppPlanReport,
    AppRecipe,
    AppRunReport,
    AppStatusReport,
    AppValidationReport,
)

router = APIRouter(prefix="/app", tags=["app"])


@router.post("/run", response_model=AppRunReport)
def run_app(recipe: AppRecipe | None = None) -> AppRunReport:
    settings = get_settings()
    recipe = recipe or load_app_recipe()
    engine = Groundline(settings)
    return run_app_recipe(engine=engine, recipe=recipe, data_dir=settings.data_dir)


@router.post("/plan", response_model=AppPlanReport)
def plan_app(recipe: AppRecipe | None = None) -> AppPlanReport:
    settings = get_settings()
    recipe = recipe or load_app_recipe()
    engine = Groundline(settings)
    return plan_app_recipe(engine=engine, recipe=recipe, data_dir=settings.data_dir)


@router.post("/validate", response_model=AppValidationReport)
def validate_app(recipe: AppRecipe | None = None) -> AppValidationReport:
    settings = get_settings()
    recipe = recipe or load_app_recipe()
    engine = Groundline(settings)
    return validate_app_recipe(engine=engine, recipe=recipe, data_dir=settings.data_dir)


@router.get("/status", response_model=AppStatusReport)
def get_app_status() -> AppStatusReport:
    settings = get_settings()
    engine = Groundline(settings)
    return app_status(engine, load_app_recipe())


@router.get("/artifacts/latest", response_model=AppArtifact)
def get_latest_app_artifact() -> AppArtifact:
    artifact = latest_app_artifact(load_app_recipe())
    if artifact is None:
        raise HTTPException(status_code=404, detail="No app artifact found")
    return artifact
