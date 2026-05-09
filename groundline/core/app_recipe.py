from __future__ import annotations

import json
import shutil
import tomllib
from datetime import UTC, datetime
from pathlib import Path

from groundline.core.demo import demo_step
from groundline.core.engine import Groundline
from groundline.core.schemas import (
    AppArtifact,
    AppExecutionReport,
    AppRecipe,
    AppRunReport,
    AppStatusReport,
    DemoStepReport,
)
from groundline.evals.runner import run_eval

DEFAULT_RECIPE_PATH = Path("groundline.app.toml")


def default_app_recipe() -> AppRecipe:
    return AppRecipe()


def load_app_recipe(path: Path = DEFAULT_RECIPE_PATH) -> AppRecipe:
    if not path.exists():
        return default_app_recipe()
    with path.open("rb") as file:
        data = tomllib.load(file)
    return AppRecipe.model_validate(data)


def write_app_recipe(path: Path, recipe: AppRecipe) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_recipe_toml(recipe), encoding="utf-8")


def run_app_recipe(
    engine: Groundline,
    recipe: AppRecipe,
    data_dir: Path,
    write_artifacts: bool = True,
) -> AppRunReport:
    collection = recipe.collection
    steps = []
    cleared = None
    if recipe.reset_collection:
        cleared = engine.clear_collection(collection)
        steps.append(
            demo_step(
                "clear",
                cleared.pipeline,
                ok=cleared.ok or cleared.reason == "collection not found",
            )
        )

    providers_result = engine.provider_status()
    ingest_result = engine.ingest_path(Path(recipe.docs_path), collection=collection)
    steps.append(
        demo_step(
            "ingest",
            ingest_result.pipeline,
            ok=bool(ingest_result.documents or ingest_result.skipped),
        )
    )
    health_result = engine.collection_health(collection)
    steps.append(demo_step("health", health_result.pipeline, ok=health_result.ok))

    query_result = None
    if recipe.run_query:
        query_result = engine.query(
            collection=collection,
            query=recipe.query_text,
            top_k=recipe.top_k,
            context_window=recipe.context_window,
            max_context_chars=recipe.max_context_chars,
            include_trace=recipe.include_trace,
        )
        steps.append(demo_step("query", query_result.pipeline, ok=bool(query_result.contexts)))

    answer_result = None
    if recipe.run_answer:
        answer_result = engine.answer(
            collection=collection,
            query=recipe.query_text,
            top_k=recipe.top_k,
            context_window=recipe.context_window,
            max_context_chars=recipe.max_context_chars,
            include_trace=recipe.include_trace,
        )
        steps.append(
            demo_step(
                "answer",
                answer_result.pipeline,
                ok=answer_result.error in {None, "llm disabled"},
            )
        )

    eval_report = None
    if recipe.run_eval:
        eval_report = run_eval(
            engine=engine,
            collection=collection,
            dataset_path=Path(recipe.evalset),
            top_k=recipe.top_k,
        )
        steps.append(
            DemoStepReport(
                name="eval",
                ok=True,
                events=len(eval_report.queries),
            )
        )

    reindex_result = None
    health_after_reindex = None
    if recipe.run_reindex:
        reindex_result = engine.reindex_collection(collection)
        steps.append(
            demo_step(
                "reindex",
                reindex_result.pipeline,
                ok=reindex_result.ok or reindex_result.reason == "embedding disabled",
            )
        )
        health_after_reindex = engine.collection_health(collection)
        steps.append(
            demo_step(
                "health_after_reindex",
                health_after_reindex.pipeline,
                ok=health_after_reindex.ok,
            )
        )

    runs = engine.list_pipeline_runs(collection=collection, limit=20)
    app_run = AppExecutionReport(
        collection=collection,
        data_dir=str(data_dir),
        docs_path=recipe.docs_path,
        evalset=recipe.evalset,
        query=recipe.query_text,
        steps=steps,
        providers=providers_result,
        cleared=cleared,
        ingest=ingest_result,
        health=health_result,
        query_result=query_result,
        answer=answer_result,
        eval=eval_report,
        reindex=reindex_result,
        health_after_reindex=health_after_reindex,
        runs=runs,
    )
    artifacts = write_app_artifacts(recipe=recipe, report=app_run) if write_artifacts else []
    return AppRunReport(recipe=recipe, run=app_run, artifacts=artifacts)


def app_status(engine: Groundline, recipe: AppRecipe) -> AppStatusReport:
    runs = engine.list_pipeline_runs(collection=recipe.collection, limit=20)
    latest = latest_app_artifact(recipe)
    return AppStatusReport(
        recipe=recipe,
        latest_artifact=latest,
        latest_run=runs[0] if runs else None,
        runs=runs,
    )


def export_latest_artifact(recipe: AppRecipe, output_path: Path) -> AppArtifact:
    latest = latest_app_artifact(recipe)
    if latest is None:
        raise FileNotFoundError("No app artifact found. Run `groundline app run` first.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(latest.path, output_path)
    return AppArtifact(kind="export", path=str(output_path))


def write_app_artifacts(
    recipe: AppRecipe,
    report: AppExecutionReport,
) -> list[AppArtifact]:
    artifacts_dir = Path(recipe.artifacts_dir)
    runs_dir = artifacts_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "recipe": recipe.model_dump(mode="json"),
        "run": report.model_dump(mode="json"),
    }
    latest_path = artifacts_dir / "latest.json"
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_path = runs_dir / f"{timestamp}-{report.collection}.json"
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    latest_path.write_text(serialized + "\n", encoding="utf-8")
    run_path.write_text(serialized + "\n", encoding="utf-8")
    return [
        AppArtifact(kind="latest", path=str(latest_path)),
        AppArtifact(kind="run", path=str(run_path)),
    ]


def latest_app_artifact(recipe: AppRecipe) -> AppArtifact | None:
    latest_path = Path(recipe.artifacts_dir) / "latest.json"
    if not latest_path.exists():
        return None
    return AppArtifact(kind="latest", path=str(latest_path))


def _recipe_toml(recipe: AppRecipe) -> str:
    return "\n".join(
        [
            f'name = "{_escape_toml(recipe.name)}"',
            f'collection = "{_escape_toml(recipe.collection)}"',
            f'docs_path = "{_escape_toml(recipe.docs_path)}"',
            f'evalset = "{_escape_toml(recipe.evalset)}"',
            f'query_text = "{_escape_toml(recipe.query_text)}"',
            f"top_k = {recipe.top_k}",
            f"context_window = {recipe.context_window}",
            f"max_context_chars = {recipe.max_context_chars}",
            f"reset_collection = {_toml_bool(recipe.reset_collection)}",
            f"run_query = {_toml_bool(recipe.run_query)}",
            f"run_answer = {_toml_bool(recipe.run_answer)}",
            f"run_eval = {_toml_bool(recipe.run_eval)}",
            f"run_reindex = {_toml_bool(recipe.run_reindex)}",
            f"include_trace = {_toml_bool(recipe.include_trace)}",
            f'artifacts_dir = "{_escape_toml(recipe.artifacts_dir)}"',
            "",
        ]
    )


def _escape_toml(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _toml_bool(value: bool) -> str:
    return "true" if value else "false"
