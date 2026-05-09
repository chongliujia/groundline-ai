from __future__ import annotations

import json
import shutil
import tomllib
from datetime import UTC, datetime
from pathlib import Path

from groundline.core.demo import demo_step
from groundline.core.engine import Groundline
from groundline.core.hashing import hash_file, hash_text
from groundline.core.schemas import (
    AppArtifact,
    AppExecutionReport,
    AppInitReport,
    AppPlanReport,
    AppPlanStep,
    AppRecipe,
    AppRunManifest,
    AppRunReport,
    AppSourceSnapshot,
    AppStatusReport,
    AppTemplateFile,
    AppValidationIssue,
    AppValidationReport,
    DemoStepReport,
)
from groundline.evals.runner import run_eval
from groundline.ingestion.loader import infer_source_type, iter_local_documents

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


def init_app_project(project_dir: Path, force: bool = False) -> AppInitReport:
    recipe = AppRecipe(
        name=project_dir.name or "groundline-app",
        collection=_collection_name(project_dir.name),
        docs_path="docs",
        evalset="evalset.jsonl",
        query_text="hotel standard",
        artifacts_dir=".groundline/artifacts",
    )
    files: list[AppTemplateFile] = []
    project_dir.mkdir(parents=True, exist_ok=True)
    files.append(_write_template_file(project_dir / "docs" / "policy.md", _sample_doc(), force))
    files.append(_write_template_file(project_dir / "evalset.jsonl", _sample_evalset(), force))
    files.append(
        _write_template_file(
            project_dir / ".gitignore",
            ".groundline/\n__pycache__/\n*.pyc\n",
            force,
        )
    )
    recipe_path = project_dir / DEFAULT_RECIPE_PATH
    if recipe_path.exists() and not force:
        files.append(AppTemplateFile(path=str(recipe_path), created=False))
    else:
        write_app_recipe(recipe_path, recipe)
        files.append(AppTemplateFile(path=str(recipe_path), created=True))
    return AppInitReport(
        project_dir=str(project_dir),
        recipe_path=str(recipe_path),
        files=files,
    )


def plan_app_recipe(
    engine: Groundline,
    recipe: AppRecipe,
    data_dir: Path,
) -> AppPlanReport:
    return AppPlanReport(
        recipe=recipe,
        data_dir=str(data_dir),
        collection_exists=recipe.collection in engine.list_collections(),
        providers=engine.provider_status(),
        latest_artifact=latest_app_artifact(recipe),
        steps=_planned_steps(recipe),
    )


def validate_app_recipe(
    engine: Groundline,
    recipe: AppRecipe,
    data_dir: Path,
) -> AppValidationReport:
    plan = plan_app_recipe(engine=engine, recipe=recipe, data_dir=data_dir)
    issues = _validation_issues(recipe, plan)
    return AppValidationReport(
        recipe=recipe,
        ok=not any(issue.severity == "error" for issue in issues),
        issues=issues,
        plan=plan,
    )


def run_app_recipe(
    engine: Groundline,
    recipe: AppRecipe,
    data_dir: Path,
    write_artifacts: bool = True,
) -> AppRunReport:
    started_at = datetime.now(UTC)
    sources = _source_snapshots(Path(recipe.docs_path))
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
    finished_at = datetime.now(UTC)
    manifest = AppRunManifest(
        recipe_hash=_recipe_hash(recipe),
        collection=collection,
        data_dir=str(data_dir),
        docs_path=recipe.docs_path,
        evalset=recipe.evalset,
        query_text=recipe.query_text,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=(finished_at - started_at).total_seconds() * 1000,
        sources=sources,
        providers=providers_result,
        steps=steps,
        run_ids=[step.run_id for step in steps if step.run_id],
    )
    app_run = AppExecutionReport(
        collection=collection,
        data_dir=str(data_dir),
        docs_path=recipe.docs_path,
        evalset=recipe.evalset,
        query=recipe.query_text,
        steps=steps,
        providers=providers_result,
        manifest=manifest,
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


def _planned_steps(recipe: AppRecipe) -> list[AppPlanStep]:
    return [
        AppPlanStep(
            name="clear",
            enabled=recipe.reset_collection,
            description="Clear collection metadata and vector index before ingest.",
            destructive=True,
        ),
        AppPlanStep(
            name="ingest",
            description="Ingest supported local documents into the configured collection.",
        ),
        AppPlanStep(
            name="health",
            description="Check metadata and vector index consistency after ingest.",
        ),
        AppPlanStep(
            name="query",
            enabled=recipe.run_query,
            description="Retrieve grounded contexts for the configured smoke query.",
        ),
        AppPlanStep(
            name="answer",
            enabled=recipe.run_answer,
            description="Generate an answer from retrieved contexts when LLM is configured.",
        ),
        AppPlanStep(
            name="eval",
            enabled=recipe.run_eval,
            description="Run the configured JSONL evalset.",
        ),
        AppPlanStep(
            name="reindex",
            enabled=recipe.run_reindex,
            description="Rebuild vector points for active latest chunks.",
        ),
        AppPlanStep(
            name="health_after_reindex",
            enabled=recipe.run_reindex,
            description="Check collection health again after reindex.",
        ),
        AppPlanStep(
            name="artifact",
            description="Write latest and timestamped app run artifacts.",
        ),
    ]


def _validation_issues(
    recipe: AppRecipe,
    plan: AppPlanReport,
) -> list[AppValidationIssue]:
    issues: list[AppValidationIssue] = []
    docs_path = Path(recipe.docs_path)
    evalset = Path(recipe.evalset)
    artifacts_dir = Path(recipe.artifacts_dir)

    if not docs_path.exists():
        issues.append(
            AppValidationIssue(
                severity="error",
                code="docs_path_missing",
                message="docs_path does not exist.",
                path=recipe.docs_path,
            )
        )
    elif not docs_path.is_file() and not docs_path.is_dir():
        issues.append(
            AppValidationIssue(
                severity="error",
                code="docs_path_invalid",
                message="docs_path must be a file or directory.",
                path=recipe.docs_path,
            )
        )

    if recipe.run_eval and not evalset.exists():
        issues.append(
            AppValidationIssue(
                severity="error",
                code="evalset_missing",
                message="run_eval is enabled but evalset does not exist.",
                path=recipe.evalset,
            )
        )

    if (recipe.run_query or recipe.run_answer) and not recipe.query_text.strip():
        issues.append(
            AppValidationIssue(
                severity="error",
                code="query_text_empty",
                message="query_text is required when query or answer steps are enabled.",
            )
        )

    if recipe.reset_collection:
        issues.append(
            AppValidationIssue(
                severity="warning",
                code="reset_collection_enabled",
                message="reset_collection will clear existing collection data before ingest.",
            )
        )

    if not plan.collection_exists:
        issues.append(
            AppValidationIssue(
                severity="info",
                code="collection_will_be_created",
                message="collection does not exist yet; ingest will create it.",
            )
        )

    provider_by_name = {provider.name: provider for provider in plan.providers.providers}
    llm = provider_by_name["llm"]
    embedding = provider_by_name["embedding"]
    rerank = provider_by_name["rerank"]

    if recipe.run_answer and llm.provider.lower() in {"none", "disabled"}:
        issues.append(
            AppValidationIssue(
                severity="warning",
                code="llm_disabled",
                message="run_answer is enabled but LLM provider is disabled.",
            )
        )

    if embedding.provider.lower() in {"none", "disabled"}:
        issues.append(
            AppValidationIssue(
                severity="info",
                code="embedding_disabled",
                message="embedding provider is disabled; retrieval will use BM25 only.",
            )
        )

    if recipe.run_reindex and embedding.provider.lower() in {"none", "disabled"}:
        issues.append(
            AppValidationIssue(
                severity="warning",
                code="reindex_without_embedding",
                message="run_reindex is enabled but embedding provider is disabled.",
            )
        )

    if rerank.provider.lower() in {"none", "disabled"}:
        issues.append(
            AppValidationIssue(
                severity="info",
                code="rerank_disabled",
                message="rerank provider is disabled; fused retrieval order will be used.",
            )
        )

    if not any([recipe.run_query, recipe.run_answer, recipe.run_eval, recipe.run_reindex]):
        issues.append(
            AppValidationIssue(
                severity="warning",
                code="only_ingest_enabled",
                message="app run will only ingest and check health.",
            )
        )

    artifacts_parent = artifacts_dir.parent
    if artifacts_parent != Path(".") and not artifacts_parent.exists():
        issues.append(
            AppValidationIssue(
                severity="info",
                code="artifacts_parent_will_be_created",
                message="artifact parent directory does not exist yet and will be created.",
                path=str(artifacts_parent),
            )
        )

    return issues


def _recipe_hash(recipe: AppRecipe) -> str:
    payload = json.dumps(
        recipe.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hash_text(payload)


def _source_snapshots(path: Path) -> list[AppSourceSnapshot]:
    if not path.exists():
        return []
    return [
        AppSourceSnapshot(
            path=str(source),
            source_type=infer_source_type(source),
            content_hash=hash_file(source),
            bytes=source.stat().st_size,
        )
        for source in iter_local_documents(path)
        if source.suffix.lower() != ".pdf"
    ]


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


def _write_template_file(path: Path, content: str, force: bool) -> AppTemplateFile:
    if path.exists() and not force:
        return AppTemplateFile(path=str(path), created=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return AppTemplateFile(path=str(path), created=True)


def _collection_name(name: str) -> str:
    normalized = "".join(
        char.lower() if char.isascii() and char.isalnum() else "_" for char in name
    )
    normalized = "_".join(part for part in normalized.split("_") if part)
    return normalized or "groundline_app"


def _sample_doc() -> str:
    return "\n".join(
        [
            "# Team Policy",
            "",
            "## Travel",
            "",
            "Employees can claim travel reimbursement after submitting receipts.",
            "",
            "## Hotel Standard",
            "",
            (
                "The hotel standard is 800 CNY per night in tier-one cities and "
                "600 CNY per night in tier-two cities."
            ),
            "",
        ]
    )


def _sample_evalset() -> str:
    return (
        '{"query":"hotel standard","gold_source_uris":["docs/policy.md"],'
        '"query_type":"smoke"}\n'
    )
