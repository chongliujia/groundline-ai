import json
from pathlib import Path

from groundline.core.app_recipe import (
    app_status,
    default_app_recipe,
    export_latest_artifact,
    load_app_recipe,
    plan_app_recipe,
    run_app_recipe,
    validate_app_recipe,
    write_app_recipe,
)
from groundline.core.engine import Groundline


def test_app_recipe_run_writes_artifacts_and_status(tmp_path: Path) -> None:
    recipe = default_app_recipe().model_copy(
        update={
            "collection": "app_demo",
            "artifacts_dir": str(tmp_path / "artifacts"),
        }
    )
    recipe_path = tmp_path / "groundline.app.toml"
    data_dir = tmp_path / "data"
    engine = Groundline.from_local(data_dir)

    write_app_recipe(recipe_path, recipe)
    loaded = load_app_recipe(recipe_path)
    plan = plan_app_recipe(engine=engine, recipe=loaded, data_dir=data_dir)
    validation = validate_app_recipe(engine=engine, recipe=loaded, data_dir=data_dir)
    report = run_app_recipe(engine=engine, recipe=loaded, data_dir=data_dir)
    status = app_status(engine, loaded)
    exported = export_latest_artifact(loaded, tmp_path / "exported.json")

    assert loaded == recipe
    assert [step.name for step in plan.steps] == [
        "clear",
        "ingest",
        "health",
        "query",
        "answer",
        "eval",
        "reindex",
        "health_after_reindex",
        "artifact",
    ]
    assert plan.collection_exists is False
    assert validation.ok is True
    assert {issue.code for issue in validation.issues} >= {
        "collection_will_be_created",
        "embedding_disabled",
        "llm_disabled",
        "rerank_disabled",
    }
    assert report.run.ingest.documents
    assert [step.name for step in report.run.steps] == [
        "ingest",
        "health",
        "query",
        "answer",
    ]
    assert report.artifacts[0].kind == "latest"
    assert Path(report.artifacts[0].path).exists()
    artifact_payload = json.loads(Path(report.artifacts[0].path).read_text())
    assert artifact_payload["recipe"]["collection"] == "app_demo"
    assert artifact_payload["run"]["collection"] == "app_demo"
    assert status.latest_artifact is not None
    assert status.latest_run is not None
    assert exported.path.endswith("exported.json")
    assert (tmp_path / "exported.json").exists()


def test_app_recipe_optional_maintenance_steps(tmp_path: Path) -> None:
    recipe = default_app_recipe().model_copy(
        update={
            "collection": "app_maintenance",
            "artifacts_dir": str(tmp_path / "artifacts"),
            "reset_collection": True,
            "run_eval": True,
            "run_reindex": True,
        }
    )
    data_dir = tmp_path / "data"
    engine = Groundline.from_local(data_dir)

    report = run_app_recipe(engine=engine, recipe=recipe, data_dir=data_dir)
    step_names = [step.name for step in report.run.steps]

    assert step_names == [
        "clear",
        "ingest",
        "health",
        "query",
        "answer",
        "eval",
        "reindex",
        "health_after_reindex",
    ]
    assert report.run.cleared is not None
    assert report.run.eval is not None
    assert report.run.reindex is not None


def test_app_recipe_validation_reports_blocking_errors(tmp_path: Path) -> None:
    recipe = default_app_recipe().model_copy(
        update={
            "collection": "app_invalid",
            "docs_path": str(tmp_path / "missing-docs"),
            "evalset": str(tmp_path / "missing-eval.jsonl"),
            "query_text": "",
            "run_eval": True,
        }
    )
    engine = Groundline.from_local(tmp_path / "data")

    validation = validate_app_recipe(
        engine=engine,
        recipe=recipe,
        data_dir=tmp_path / "data",
    )

    assert validation.ok is False
    assert {issue.code for issue in validation.issues} >= {
        "docs_path_missing",
        "evalset_missing",
        "query_text_empty",
    }
