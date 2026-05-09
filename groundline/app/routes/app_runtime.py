from __future__ import annotations

from fastapi import APIRouter, HTTPException

from groundline.core.app_recipe import (
    app_document_registry,
    app_provider_readiness,
    app_runtime_profile,
    app_status,
    apply_app_profile,
    latest_app_artifact,
    load_app_recipe,
    plan_app_recipe,
    run_app_recipe,
    settings_for_app_runtime,
    validate_app_recipe,
)
from groundline.core.config import get_settings
from groundline.core.engine import Groundline
from groundline.core.schemas import (
    AppArtifact,
    AppDocumentRegistryReport,
    AppPlanReport,
    AppRecipe,
    AppRunReport,
    AppRuntimeProfile,
    AppStatusReport,
    AppValidationReport,
    ProviderReadinessReport,
)

router = APIRouter(prefix="/app", tags=["app"])


@router.post("/run", response_model=AppRunReport)
def run_app(recipe: AppRecipe | None = None, profile: str = "default") -> AppRunReport:
    recipe, runtime, engine = _app_context(recipe, profile)
    return run_app_recipe(
        engine=engine,
        recipe=recipe,
        data_dir=settings_for_app_runtime(runtime).data_dir,
        runtime=runtime,
    )


@router.post("/plan", response_model=AppPlanReport)
def plan_app(recipe: AppRecipe | None = None, profile: str = "default") -> AppPlanReport:
    recipe, runtime, engine = _app_context(recipe, profile)
    return plan_app_recipe(
        engine=engine,
        recipe=recipe,
        data_dir=settings_for_app_runtime(runtime).data_dir,
        runtime=runtime,
    )


@router.post("/validate", response_model=AppValidationReport)
def validate_app(
    recipe: AppRecipe | None = None,
    profile: str = "default",
) -> AppValidationReport:
    recipe, runtime, engine = _app_context(recipe, profile)
    return validate_app_recipe(
        engine=engine,
        recipe=recipe,
        data_dir=settings_for_app_runtime(runtime).data_dir,
        runtime=runtime,
    )


@router.post("/docs", response_model=AppDocumentRegistryReport)
def app_docs(
    recipe: AppRecipe | None = None,
    profile: str = "default",
) -> AppDocumentRegistryReport:
    recipe, _, engine = _app_context(recipe, profile)
    return app_document_registry(engine=engine, recipe=recipe)


@router.get("/providers", response_model=ProviderReadinessReport)
def app_providers(profile: str = "default") -> ProviderReadinessReport:
    _, _, engine = _app_context(None, profile)
    return app_provider_readiness(engine)


@router.get("/status", response_model=AppStatusReport)
def get_app_status(profile: str = "default") -> AppStatusReport:
    recipe, _, engine = _app_context(None, profile)
    return app_status(engine, recipe)


@router.get("/artifacts/latest", response_model=AppArtifact)
def get_latest_app_artifact(profile: str = "default") -> AppArtifact:
    recipe, _, _ = _app_context(None, profile)
    artifact = latest_app_artifact(recipe)
    if artifact is None:
        raise HTTPException(status_code=404, detail="No app artifact found")
    return artifact


def _app_context(
    recipe: AppRecipe | None,
    profile: str,
) -> tuple[AppRecipe, AppRuntimeProfile, Groundline]:
    settings = get_settings()
    base_recipe = recipe or load_app_recipe()
    resolved_recipe = apply_app_profile(base_recipe, profile)
    runtime = app_runtime_profile(
        settings=settings,
        recipe=base_recipe,
        profile=profile,
    )
    engine = Groundline(settings_for_app_runtime(runtime))
    return resolved_recipe, runtime, engine
