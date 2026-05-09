import json
from pathlib import Path

from groundline.core.app_recipe import (
    app_document_registry,
    app_provider_readiness,
    app_status,
    default_app_recipe,
    export_latest_artifact,
    init_app_project,
    load_app_recipe,
    plan_app_recipe,
    run_app_recipe,
    validate_app_recipe,
    write_app_recipe,
)
from groundline.core.config import Settings
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
    assert report.run.manifest.recipe_hash
    assert report.run.manifest.sources[0].path.endswith("finance_policy.md")
    assert report.run.manifest.sources[0].content_hash
    assert report.run.manifest.run_ids
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
    assert artifact_payload["run"]["manifest"]["recipe_hash"]
    assert artifact_payload["run"]["manifest"]["sources"][0]["content_hash"]
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


def test_init_app_project_creates_runnable_template(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "Support Bot"
    report = init_app_project(project_dir)

    assert report.recipe_path.endswith("groundline.app.toml")
    assert {Path(file.path).name for file in report.files} == {
        ".gitignore",
        "evalset.jsonl",
        "groundline.app.toml",
        "policy.md",
    }
    assert all(file.created for file in report.files)

    monkeypatch.chdir(project_dir)
    recipe = load_app_recipe()
    engine = Groundline.from_local(Path(".groundline"))
    validation = validate_app_recipe(
        engine=engine,
        recipe=recipe,
        data_dir=Path(".groundline"),
    )
    run = run_app_recipe(engine=engine, recipe=recipe, data_dir=Path(".groundline"))

    assert recipe.collection == "support_bot"
    assert validation.ok is True
    assert run.run.ingest.documents
    assert run.run.manifest.sources[0].path == "docs/policy.md"
    assert run.run.manifest.recipe_hash
    assert run.run.query_result is not None
    assert run.run.query_result.contexts

    skipped = init_app_project(project_dir)
    assert not any(file.created for file in skipped.files)


def test_app_document_registry_tracks_source_state(tmp_path: Path, monkeypatch) -> None:
    project_dir = tmp_path / "registry-app"
    init_app_project(project_dir)
    monkeypatch.chdir(project_dir)
    recipe = load_app_recipe()
    engine = Groundline.from_local(Path(".groundline"))

    before = app_document_registry(engine=engine, recipe=recipe)
    assert [item.status for item in before.items] == ["new"]

    run_app_recipe(engine=engine, recipe=recipe, data_dir=Path(".groundline"))
    after = app_document_registry(engine=engine, recipe=recipe)
    assert [item.status for item in after.items] == ["unchanged"]
    assert after.items[0].doc_id is not None
    assert after.items[0].indexed_hash == after.items[0].content_hash

    policy = Path("docs/policy.md")
    policy.write_text(policy.read_text() + "\nNew reimbursement rule.\n")
    changed = app_document_registry(engine=engine, recipe=recipe)
    assert [item.status for item in changed.items] == ["changed"]

    policy.unlink()
    missing = app_document_registry(engine=engine, recipe=recipe)
    assert [item.status for item in missing.items] == ["missing"]
    assert missing.missing_total == 1


def test_app_provider_readiness_reports_configuration_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "groundline.toml"
    config_path.write_text(
        """
        [llm]
        provider = "openai_compatible"
        model = "chat-model"
        base_url = "https://llm.example/v1"
        api_key_env = "GROUNDLINE_TEST_LLM_KEY"

        [embedding]
        provider = "hash"
        dimension = 16

        [rerank]
        provider = "keyword"
        """,
        encoding="utf-8",
    )
    monkeypatch.setenv("GROUNDLINE_TEST_LLM_KEY", "test-key")
    engine = Groundline(
        Settings(
            data_dir=tmp_path / "data",
            provider_config_path=config_path,
            qdrant_url="http://qdrant.local:6333",
        )
    )

    readiness = app_provider_readiness(engine)
    by_name = {provider.name: provider for provider in readiness.providers}

    assert readiness.ok is True
    assert by_name["llm"].status == "ready"
    assert by_name["embedding"].status == "ready"
    assert by_name["rerank"].status == "ready"
    assert by_name["vector"].status == "ready"
    assert by_name["vector"].dimension == 16


def test_app_provider_readiness_reports_missing_http_settings(tmp_path: Path) -> None:
    config_path = tmp_path / "groundline.toml"
    config_path.write_text(
        """
        [llm]
        provider = "openai_compatible"
        api_key_env = "GROUNDLINE_MISSING_LLM_KEY"
        """,
        encoding="utf-8",
    )
    engine = Groundline(
        Settings(
            data_dir=tmp_path / "data",
            provider_config_path=config_path,
        )
    )

    readiness = app_provider_readiness(engine)
    llm = {provider.name: provider for provider in readiness.providers}["llm"]

    assert readiness.ok is False
    assert llm.status == "error"
    assert {check.code for check in llm.checks} >= {
        "model_missing",
        "base_url_missing",
        "api_key_missing",
    }
