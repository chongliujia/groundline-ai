from __future__ import annotations

import json
import shutil
import tomllib
from datetime import UTC, datetime
from pathlib import Path

from groundline.core.demo import run_demo_flow
from groundline.core.engine import Groundline
from groundline.core.schemas import (
    AppArtifact,
    AppRecipe,
    AppRunReport,
    AppStatusReport,
    DemoReport,
)

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
    demo = run_demo_flow(
        engine=engine,
        collection=recipe.collection,
        docs_path=Path(recipe.docs_path),
        evalset=Path(recipe.evalset),
        query_text=recipe.query_text,
        context_window=recipe.context_window,
        data_dir=data_dir,
    )
    artifacts = write_app_artifacts(recipe=recipe, report=demo) if write_artifacts else []
    return AppRunReport(recipe=recipe, demo=demo, artifacts=artifacts)


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


def write_app_artifacts(recipe: AppRecipe, report: DemoReport) -> list[AppArtifact]:
    artifacts_dir = Path(recipe.artifacts_dir)
    runs_dir = artifacts_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "recipe": recipe.model_dump(mode="json"),
        "demo": report.model_dump(mode="json"),
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
            f"context_window = {recipe.context_window}",
            f'artifacts_dir = "{_escape_toml(recipe.artifacts_dir)}"',
            "",
        ]
    )


def _escape_toml(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
