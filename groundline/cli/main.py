from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

from groundline.core.app_recipe import (
    DEFAULT_RECIPE_PATH,
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
from groundline.core.demo import run_demo_flow
from groundline.core.engine import Groundline
from groundline.core.schemas import (
    AppDocumentRegistryReport,
    AppInitReport,
    AppPlanReport,
    AppRunReport,
    AppStatusReport,
    AppValidationReport,
    CollectionHealthReport,
    CollectionOperationResponse,
    DemoReport,
    PipelineRun,
    ProviderReadinessReport,
    ReindexResponse,
)
from groundline.evals.runner import run_eval

app = typer.Typer(help="Groundline CLI")
app_commands = typer.Typer(help="Run Groundline as a reusable RAG application.")
app.add_typer(app_commands, name="app")
console = Console()


@app.callback()
def main() -> None:
    """Groundline command line interface."""


@app.command()
def init(
    data_dir: Annotated[Path, typer.Option(help="Local Groundline data dir.")] = Path(
        ".groundline"
    ),
) -> None:
    settings = Settings(data_dir=data_dir)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "objects").mkdir(exist_ok=True)
    console.print(f"Initialized Groundline at {settings.data_dir}")


@app.command()
def providers(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON."),
    ] = False,
    data_dir: Annotated[Path, typer.Option(help="Local Groundline data dir.")] = Path(
        ".groundline"
    ),
) -> None:
    engine = Groundline(Settings(data_dir=data_dir))
    result = engine.provider_status()
    if json_output:
        _print_json_model(result)
        return

    table = Table(title="Providers")
    table.add_column("Name")
    table.add_column("Provider")
    table.add_column("Model")
    table.add_column("Base URL")
    table.add_column("Endpoint")
    table.add_column("API Key")
    for provider in result.providers:
        table.add_row(
            provider.name,
            provider.provider,
            provider.model,
            provider.base_url,
            provider.endpoint_path,
            "set" if provider.api_key_configured else "missing",
        )
    console.print(table)


@app.command()
def health(
    collection: Annotated[str, typer.Option(help="Collection name.")] = "demo",
    include_documents: Annotated[
        bool,
        typer.Option(help="Include per-document index diagnostics."),
    ] = True,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON."),
    ] = False,
    data_dir: Annotated[Path, typer.Option(help="Local Groundline data dir.")] = Path(
        ".groundline"
    ),
) -> None:
    engine = Groundline(Settings(data_dir=data_dir))
    result = engine.collection_health(
        collection,
        include_documents=include_documents,
    )
    if json_output:
        _print_json_model(result)
        return
    _print_collection_health(result)


@app.command()
def runs(
    collection: Annotated[str | None, typer.Option(help="Filter by collection name.")] = None,
    operation: Annotated[str | None, typer.Option(help="Filter by operation.")] = None,
    run_id: Annotated[str | None, typer.Option(help="Show a single pipeline run.")] = None,
    limit: Annotated[int, typer.Option(help="Maximum runs to display.")] = 20,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON."),
    ] = False,
    data_dir: Annotated[Path, typer.Option(help="Local Groundline data dir.")] = Path(
        ".groundline"
    ),
) -> None:
    engine = Groundline(Settings(data_dir=data_dir))
    if run_id is not None:
        run = engine.get_pipeline_run(run_id)
        if json_output:
            _print_json({"run": run.model_dump(mode="json") if run else None})
            return
        if run is None:
            console.print(f"[yellow]Pipeline run not found[/yellow] {run_id}")
            return
        _print_pipeline_run(run)
        return

    runs = engine.list_pipeline_runs(
        collection=collection,
        operation=operation,
        limit=limit,
    )
    if json_output:
        _print_json({"runs": [run.model_dump(mode="json") for run in runs]})
        return
    _print_pipeline_runs(runs)


@app_commands.command("init")
def app_init(
    recipe_path: Annotated[
        Path,
        typer.Option("--recipe", help="App recipe TOML path."),
    ] = DEFAULT_RECIPE_PATH,
    project_dir: Annotated[
        Path | None,
        typer.Option("--project-dir", help="Create a runnable app project template."),
    ] = None,
    force: Annotated[bool, typer.Option(help="Overwrite an existing recipe.")] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON."),
    ] = False,
) -> None:
    if project_dir is not None:
        report = init_app_project(project_dir, force=force)
        if json_output:
            _print_json_model(report)
            return
        _print_app_init(report)
        return
    if recipe_path.exists() and not force:
        console.print(f"[yellow]Recipe already exists[/yellow] {recipe_path}")
        return
    write_app_recipe(recipe_path, default_app_recipe())
    report = AppInitReport(
        project_dir=str(recipe_path.parent),
        recipe_path=str(recipe_path),
        files=[],
    )
    if json_output:
        _print_json_model(report)
        return
    console.print(f"Initialized Groundline app recipe at {recipe_path}")


@app_commands.command("run")
def app_run(
    recipe_path: Annotated[
        Path,
        typer.Option("--recipe", help="App recipe TOML path."),
    ] = DEFAULT_RECIPE_PATH,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON."),
    ] = False,
    data_dir: Annotated[Path, typer.Option(help="Local Groundline data dir.")] = Path(
        ".groundline"
    ),
) -> None:
    recipe = load_app_recipe(recipe_path)
    engine = Groundline(Settings(data_dir=data_dir))
    report = run_app_recipe(engine=engine, recipe=recipe, data_dir=data_dir)
    if json_output:
        _print_json_model(report)
        return
    _print_app_run_summary(report)


@app_commands.command("plan")
def app_plan(
    recipe_path: Annotated[
        Path,
        typer.Option("--recipe", help="App recipe TOML path."),
    ] = DEFAULT_RECIPE_PATH,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON."),
    ] = False,
    data_dir: Annotated[Path, typer.Option(help="Local Groundline data dir.")] = Path(
        ".groundline"
    ),
) -> None:
    recipe = load_app_recipe(recipe_path)
    engine = Groundline(Settings(data_dir=data_dir))
    report = plan_app_recipe(engine=engine, recipe=recipe, data_dir=data_dir)
    if json_output:
        _print_json_model(report)
        return
    _print_app_plan(report)


@app_commands.command("validate")
def app_validate(
    recipe_path: Annotated[
        Path,
        typer.Option("--recipe", help="App recipe TOML path."),
    ] = DEFAULT_RECIPE_PATH,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON."),
    ] = False,
    data_dir: Annotated[Path, typer.Option(help="Local Groundline data dir.")] = Path(
        ".groundline"
    ),
) -> None:
    recipe = load_app_recipe(recipe_path)
    engine = Groundline(Settings(data_dir=data_dir))
    report = validate_app_recipe(engine=engine, recipe=recipe, data_dir=data_dir)
    if json_output:
        _print_json_model(report)
    else:
        _print_app_validation(report)
    if not report.ok:
        raise typer.Exit(1)


@app_commands.command("docs")
def app_docs(
    recipe_path: Annotated[
        Path,
        typer.Option("--recipe", help="App recipe TOML path."),
    ] = DEFAULT_RECIPE_PATH,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON."),
    ] = False,
    data_dir: Annotated[Path, typer.Option(help="Local Groundline data dir.")] = Path(
        ".groundline"
    ),
) -> None:
    recipe = load_app_recipe(recipe_path)
    engine = Groundline(Settings(data_dir=data_dir))
    report = app_document_registry(engine=engine, recipe=recipe)
    if json_output:
        _print_json_model(report)
        return
    _print_app_docs(report)


@app_commands.command("providers")
def app_providers(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON."),
    ] = False,
    data_dir: Annotated[Path, typer.Option(help="Local Groundline data dir.")] = Path(
        ".groundline"
    ),
) -> None:
    engine = Groundline(Settings(data_dir=data_dir))
    report = app_provider_readiness(engine)
    if json_output:
        _print_json_model(report)
        return
    _print_app_providers(report)


@app_commands.command("status")
def app_status_cmd(
    recipe_path: Annotated[
        Path,
        typer.Option("--recipe", help="App recipe TOML path."),
    ] = DEFAULT_RECIPE_PATH,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON."),
    ] = False,
    data_dir: Annotated[Path, typer.Option(help="Local Groundline data dir.")] = Path(
        ".groundline"
    ),
) -> None:
    recipe = load_app_recipe(recipe_path)
    engine = Groundline(Settings(data_dir=data_dir))
    report = app_status(engine, recipe)
    if json_output:
        _print_json_model(report)
        return
    _print_app_status(report)


@app_commands.command("export")
def app_export(
    output_path: Annotated[Path, typer.Argument(help="Output JSON artifact path.")],
    recipe_path: Annotated[
        Path,
        typer.Option("--recipe", help="App recipe TOML path."),
    ] = DEFAULT_RECIPE_PATH,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON."),
    ] = False,
) -> None:
    artifact = export_latest_artifact(load_app_recipe(recipe_path), output_path)
    if json_output:
        _print_json_model(artifact)
        return
    console.print(f"Exported latest app artifact to {artifact.path}")


@app.command()
def quickstart(
    collection: Annotated[str, typer.Option(help="Collection name.")] = "quickstart",
    docs_path: Annotated[Path, typer.Option(help="Quickstart docs path.")] = Path(
        "examples/quickstart/docs"
    ),
    evalset: Annotated[Path, typer.Option(help="Quickstart eval JSONL path.")] = Path(
        "examples/quickstart/evalset.example.jsonl"
    ),
    query_text: Annotated[str, typer.Option(help="Query text to run.")] = "住宿标准",
    context_window: Annotated[
        int,
        typer.Option(help="Number of adjacent chunks to pack on each side."),
    ] = 1,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON."),
    ] = False,
    data_dir: Annotated[Path, typer.Option(help="Local Groundline data dir.")] = Path(
        "/tmp/groundline-quickstart"
    ),
) -> None:
    engine = Groundline(Settings(data_dir=data_dir))
    cleared = engine.clear_collection(collection)
    ingest_result = engine.ingest_path(docs_path, collection=collection)
    query_result = engine.query(
        collection=collection,
        query=query_text,
        context_window=context_window,
        include_trace=True,
    )
    answer_result = engine.answer(
        collection=collection,
        query=query_text,
        context_window=context_window,
        include_trace=True,
    )
    eval_report = run_eval(
        engine=engine,
        collection=collection,
        dataset_path=evalset,
    )
    payload = {
        "collection": collection,
        "data_dir": str(data_dir),
        "cleared": cleared.model_dump(mode="json"),
        "ingest": ingest_result.model_dump(mode="json"),
        "query": query_result.model_dump(mode="json"),
        "answer": answer_result.model_dump(mode="json"),
        "eval": eval_report.model_dump(mode="json"),
    }
    if json_output:
        _print_json(payload)
        return

    console.rule("[bold]Quickstart[/bold]")
    console.print(f"Collection: {collection}")
    console.print(f"Data dir: {data_dir}")
    console.print(
        f"Ingested {len(ingest_result.documents)} documents; "
        f"skipped {len(ingest_result.skipped)} sources."
    )
    console.print(f"Query contexts: {len(query_result.contexts)}")
    if answer_result.answer:
        console.print(answer_result.answer)
    else:
        console.print(f"[yellow]Answer not generated[/yellow]: {answer_result.error}")
    console.print(
        f"Eval Recall@{eval_report.top_k}: {eval_report.metrics.recall_at_k:.3f}; "
        f"MRR: {eval_report.metrics.mrr:.3f}"
    )


@app.command()
def demo(
    collection: Annotated[str, typer.Option(help="Collection name.")] = "demo",
    docs_path: Annotated[Path, typer.Option(help="Demo docs path.")] = Path(
        "examples/quickstart/docs"
    ),
    evalset: Annotated[Path, typer.Option(help="Demo eval JSONL path.")] = Path(
        "examples/quickstart/evalset.example.jsonl"
    ),
    query_text: Annotated[str, typer.Option(help="Query text to run.")] = "住宿标准",
    context_window: Annotated[
        int,
        typer.Option(help="Number of adjacent chunks to pack on each side."),
    ] = 1,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON."),
    ] = False,
    data_dir: Annotated[Path, typer.Option(help="Local Groundline data dir.")] = Path(
        "/tmp/groundline-demo"
    ),
) -> None:
    engine = Groundline(Settings(data_dir=data_dir))
    report = run_demo_flow(
        engine=engine,
        collection=collection,
        docs_path=docs_path,
        evalset=evalset,
        query_text=query_text,
        context_window=context_window,
        data_dir=data_dir,
    )
    if json_output:
        _print_json_model(report)
        return
    _print_demo_summary(report)


@app.command()
def reindex(
    target: Annotated[str, typer.Argument(help="Currently supported: collection.")] = "collection",
    collection: Annotated[str, typer.Option(help="Collection name.")] = "demo",
    doc_id: Annotated[str | None, typer.Option(help="Optional document id to reindex.")] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON."),
    ] = False,
    data_dir: Annotated[Path, typer.Option(help="Local Groundline data dir.")] = Path(
        ".groundline"
    ),
) -> None:
    if target.lower() != "collection":
        raise typer.BadParameter("target must be collection")
    engine = Groundline(Settings(data_dir=data_dir))
    result = engine.reindex_collection(collection, doc_id=doc_id)
    if json_output:
        _print_json_model(result)
        return
    _print_reindex_result(result)


@app.command()
def ingest(
    path: Annotated[Path, typer.Argument(help="File or directory to ingest.")],
    collection: Annotated[str, typer.Option(help="Collection name.")] = "demo",
    tenant_id: Annotated[str, typer.Option(help="Tenant id.")] = "default",
    title: Annotated[str | None, typer.Option(help="Document title for a single file.")] = None,
    doc_type: Annotated[str | None, typer.Option(help="Document type metadata.")] = None,
    domain: Annotated[str | None, typer.Option(help="Domain metadata.")] = None,
    language: Annotated[str | None, typer.Option(help="Language metadata.")] = None,
    acl_groups: Annotated[
        list[str] | None,
        typer.Option("--acl-group", help="Allowed user group; may be repeated."),
    ] = None,
    metadata_json: Annotated[
        str | None,
        typer.Option("--metadata", help="JSON object with document metadata."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON."),
    ] = False,
    data_dir: Annotated[Path, typer.Option(help="Local Groundline data dir.")] = Path(
        ".groundline"
    ),
) -> None:
    engine = Groundline(Settings(data_dir=data_dir))
    metadata = _parse_json_object(metadata_json, option_name="--metadata")
    result = engine.ingest_path(
        path=path,
        collection=collection,
        tenant_id=tenant_id,
        title=title,
        doc_type=doc_type,
        domain=domain,
        language=language,
        acl_groups=acl_groups or [],
        metadata=metadata,
    )
    if json_output:
        _print_json_model(result)
        return

    table = Table(title=f"Ingested into {result.collection}")
    table.add_column("Source")
    table.add_column("Type")
    table.add_column("Chunks", justify="right")
    table.add_column("Document ID")
    for document in result.documents:
        table.add_row(
            document.source_uri,
            document.source_type,
            str(document.chunk_count),
            document.doc_id,
        )
    console.print(table)
    for skipped in result.skipped:
        console.print(f"[yellow]Skipped[/yellow] {skipped.source_uri}: {skipped.reason}")


@app.command()
def query(
    text: Annotated[str, typer.Argument(help="Query text.")],
    collection: Annotated[str, typer.Option(help="Collection name.")] = "demo",
    tenant_id: Annotated[str, typer.Option(help="Tenant id.")] = "default",
    doc_type: Annotated[str | None, typer.Option(help="Filter by document type.")] = None,
    domain: Annotated[str | None, typer.Option(help="Filter by domain.")] = None,
    language: Annotated[str | None, typer.Option(help="Filter by language.")] = None,
    filters_json: Annotated[
        str | None,
        typer.Option("--filters", help="JSON object with additional exact-match filters."),
    ] = None,
    top_k: Annotated[int, typer.Option(help="Number of contexts to return.")] = 8,
    context_window: Annotated[
        int,
        typer.Option(help="Number of adjacent chunks to pack on each side."),
    ] = 0,
    max_context_chars: Annotated[
        int,
        typer.Option(help="Maximum total context characters to return."),
    ] = 12000,
    trace: Annotated[bool, typer.Option(help="Include retrieval trace.")] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON."),
    ] = False,
    data_dir: Annotated[Path, typer.Option(help="Local Groundline data dir.")] = Path(
        ".groundline"
    ),
) -> None:
    engine = Groundline(Settings(data_dir=data_dir))
    filters = _build_query_filters(
        doc_type=doc_type,
        domain=domain,
        language=language,
        filters_json=filters_json,
    )
    result = engine.query(
        collection=collection,
        query=text,
        tenant_id=tenant_id,
        filters=filters,
        top_k=top_k,
        context_window=context_window,
        max_context_chars=max_context_chars,
        include_trace=trace,
    )
    if json_output:
        _print_json_model(result)
        return
    if not result.contexts:
        console.print("[yellow]No contexts found.[/yellow]")
        return

    for index, context in enumerate(result.contexts, start=1):
        console.rule(f"[bold]Context {index}[/bold]")
        console.print(f"[bold]{context.title or context.doc_id}[/bold]")
        if context.section:
            console.print(f"Section: {context.section}")
        console.print(f"Citation: {context.citation.model_dump()}")
        console.print(context.content_markdown)
    if result.trace:
        console.rule("[bold]Trace[/bold]")
        console.print(result.trace)


@app.command()
def answer(
    text: Annotated[str, typer.Argument(help="Question text.")],
    collection: Annotated[str, typer.Option(help="Collection name.")] = "demo",
    tenant_id: Annotated[str, typer.Option(help="Tenant id.")] = "default",
    doc_type: Annotated[str | None, typer.Option(help="Filter by document type.")] = None,
    domain: Annotated[str | None, typer.Option(help="Filter by domain.")] = None,
    language: Annotated[str | None, typer.Option(help="Filter by language.")] = None,
    filters_json: Annotated[
        str | None,
        typer.Option("--filters", help="JSON object with additional exact-match filters."),
    ] = None,
    top_k: Annotated[int, typer.Option(help="Number of contexts to use.")] = 8,
    context_window: Annotated[
        int,
        typer.Option(help="Number of adjacent chunks to pack on each side."),
    ] = 0,
    max_context_chars: Annotated[
        int,
        typer.Option(help="Maximum total context characters to return."),
    ] = 12000,
    trace: Annotated[bool, typer.Option(help="Include retrieval trace.")] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON."),
    ] = False,
    data_dir: Annotated[Path, typer.Option(help="Local Groundline data dir.")] = Path(
        ".groundline"
    ),
) -> None:
    engine = Groundline(Settings(data_dir=data_dir))
    filters = _build_query_filters(
        doc_type=doc_type,
        domain=domain,
        language=language,
        filters_json=filters_json,
    )
    result = engine.answer(
        collection=collection,
        query=text,
        tenant_id=tenant_id,
        filters=filters,
        top_k=top_k,
        context_window=context_window,
        max_context_chars=max_context_chars,
        include_trace=trace,
    )
    if json_output:
        _print_json_model(result)
        return
    if result.answer:
        console.print(result.answer)
    else:
        console.print(f"[yellow]No answer generated[/yellow]: {result.error}")
    if result.contexts:
        console.rule("[bold]Contexts[/bold]")
        for index, context in enumerate(result.contexts, start=1):
            console.print(f"[{index}] {context.title or context.doc_id} :: {context.section or ''}")
            console.print(context.citation.model_dump())
    if result.trace:
        console.rule("[bold]Trace[/bold]")
        console.print(result.trace)


@app.command()
def eval(
    dataset: Annotated[Path, typer.Argument(help="JSONL eval dataset path.")],
    collection: Annotated[str, typer.Option(help="Collection name.")] = "demo",
    tenant_id: Annotated[str, typer.Option(help="Tenant id.")] = "default",
    top_k: Annotated[int, typer.Option(help="Recall@K and query top_k.")] = 8,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON."),
    ] = False,
    data_dir: Annotated[Path, typer.Option(help="Local Groundline data dir.")] = Path(
        ".groundline"
    ),
) -> None:
    engine = Groundline(Settings(data_dir=data_dir))
    report = run_eval(
        engine=engine,
        collection=collection,
        dataset_path=dataset,
        tenant_id=tenant_id,
        top_k=top_k,
    )
    if json_output:
        _print_json_model(report)
        return

    table = Table(title=f"Eval: {collection}")
    table.add_column("Slice")
    table.add_column("Queries", justify="right")
    table.add_column(f"Recall@{top_k}", justify="right")
    table.add_column("MRR", justify="right")
    table.add_row(
        "overall",
        str(report.metrics.queries),
        f"{report.metrics.recall_at_k:.3f}",
        f"{report.metrics.mrr:.3f}",
    )
    for query_type, metrics in report.by_query_type.items():
        table.add_row(
            query_type,
            str(metrics.queries),
            f"{metrics.recall_at_k:.3f}",
            f"{metrics.mrr:.3f}",
        )
    console.print(table)
    _print_eval_queries(report)


@app.command()
def inspect(
    target: Annotated[
        str,
        typer.Argument(help="One of: collections, documents, document, versions, chunks."),
    ] = "collections",
    collection: Annotated[str, typer.Option(help="Collection name.")] = "demo",
    doc_id: Annotated[str | None, typer.Option(help="Filter chunks by document id.")] = None,
    include_inactive: Annotated[
        bool,
        typer.Option(help="Include inactive historical chunks."),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON."),
    ] = False,
    limit: Annotated[int, typer.Option(help="Maximum rows to display.")] = 20,
    data_dir: Annotated[Path, typer.Option(help="Local Groundline data dir.")] = Path(
        ".groundline"
    ),
) -> None:
    engine = Groundline(Settings(data_dir=data_dir))
    normalized = target.lower()
    if json_output:
        _print_json(
            _inspect_payload(
                engine,
                normalized,
                collection,
                doc_id,
                include_inactive,
                limit,
            )
        )
        return
    if normalized == "collections":
        _print_collections(engine)
    elif normalized == "documents":
        _print_documents(
            engine,
            collection=collection,
            include_inactive=include_inactive,
            limit=limit,
        )
    elif normalized in {"document", "doc"}:
        _print_document_detail(
            engine,
            collection=collection,
            doc_id=_require_doc_id(doc_id, target=normalized),
            include_inactive=include_inactive,
        )
    elif normalized in {"versions", "document-versions"}:
        _print_document_versions(
            engine,
            collection=collection,
            doc_id=_require_doc_id(doc_id, target=normalized),
            include_inactive=include_inactive,
            limit=limit,
        )
    elif normalized == "chunks":
        _print_chunks(
            engine,
            collection=collection,
            doc_id=doc_id,
            include_inactive=include_inactive,
            limit=limit,
        )
    else:
        raise typer.BadParameter(
            "target must be one of: collections, documents, document, versions, chunks"
        )


def _print_collections(engine: Groundline) -> None:
    table = Table(title="Collections")
    table.add_column("Collection")
    for collection in engine.list_collections():
        table.add_row(collection)
    console.print(table)


def _print_collection_health(result: CollectionHealthReport) -> None:
    table = Table(title=f"Collection Health: {result.collection}")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Status", result.status)
    table.add_row("OK", "yes" if result.ok else "no")
    table.add_row("Documents", f"{result.active_documents}/{result.documents_total} active")
    table.add_row("Chunks", f"{result.latest_chunks}/{result.chunks_total} latest")
    table.add_row(
        "Vector",
        (
            "disabled"
            if not result.vector_index.enabled
            else (
                f"{result.vector_index.actual_points}/"
                f"{result.vector_index.expected_points} points"
            )
        ),
    )
    if result.vector_index.error:
        table.add_row("Vector Error", result.vector_index.error)
    console.print(table)

    if not result.documents:
        return
    documents = Table(title="Document Index")
    documents.add_column("Document ID")
    documents.add_column("Title")
    documents.add_column("Active")
    documents.add_column("Chunks", justify="right")
    documents.add_column("Vectors", justify="right")
    documents.add_column("Needs Reindex")
    for document in result.documents:
        documents.add_row(
            document.doc_id,
            document.title or "",
            "yes" if document.is_active else "no",
            str(document.latest_chunks),
            "" if document.vector_points is None else str(document.vector_points),
            "yes" if document.needs_reindex else "no",
        )
    console.print(documents)


def _print_pipeline_runs(runs: list[PipelineRun]) -> None:
    table = Table(title="Pipeline Runs")
    table.add_column("Run ID")
    table.add_column("Collection")
    table.add_column("Operation")
    table.add_column("Status")
    table.add_column("Events", justify="right")
    table.add_column("Started")
    for run in runs:
        table.add_row(
            run.run_id,
            run.collection,
            run.operation,
            run.status,
            str(len(run.events)),
            run.started_at.isoformat(),
        )
    console.print(table)


def _print_pipeline_run(run: PipelineRun) -> None:
    table = Table(title=f"Pipeline Run: {run.run_id}")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Collection", run.collection)
    table.add_row("Operation", run.operation)
    table.add_row("Status", run.status)
    table.add_row("Duration", "" if run.duration_ms is None else f"{run.duration_ms} ms")
    table.add_row("Started", run.started_at.isoformat())
    table.add_row("Finished", run.finished_at.isoformat() if run.finished_at else "")
    console.print(table)

    events = Table(title="Events")
    events.add_column("Stage")
    events.add_column("Status")
    events.add_column("Message")
    events.add_column("Document ID")
    for event in run.events:
        events.add_row(
            event.stage,
            event.status,
            event.message or "",
            event.doc_id or "",
        )
    console.print(events)


def _print_app_run_summary(report: AppRunReport) -> None:
    run = report.run
    console.rule("[bold]Groundline App Run[/bold]")
    console.print(f"App: {report.recipe.name}")
    console.print(f"Collection: {run.collection}")
    console.print(f"Data dir: {run.data_dir}")
    console.print(f"Recipe hash: {run.manifest.recipe_hash}")
    console.print(f"Input sources: {len(run.manifest.sources)}")
    table = Table(title="App Steps")
    table.add_column("Step")
    table.add_column("OK")
    table.add_column("Run ID")
    table.add_column("Status")
    table.add_column("Events", justify="right")
    for step in run.steps:
        table.add_row(
            step.name,
            "yes" if step.ok else "no",
            step.run_id or "",
            step.status or "",
            str(step.events),
        )
    console.print(table)
    console.print(
        f"Documents: {len(run.ingest.documents)}; "
        f"skipped: {len(run.ingest.skipped)}; "
        f"contexts: {len(run.query_result.contexts) if run.query_result else 0}; "
        f"runs persisted: {len(run.runs)}"
    )
    if run.answer and run.answer.error:
        console.print(f"[yellow]Answer not generated[/yellow]: {run.answer.error}")
    for artifact in report.artifacts:
        console.print(f"{artifact.kind}: {artifact.path}")


def _print_app_init(report: AppInitReport) -> None:
    console.rule("[bold]Groundline App Init[/bold]")
    console.print(f"Project: {report.project_dir}")
    console.print(f"Recipe: {report.recipe_path}")
    table = Table(title="Template Files")
    table.add_column("Path")
    table.add_column("Created")
    for file in report.files:
        table.add_row(file.path, "yes" if file.created else "no")
    console.print(table)


def _print_app_plan(report: AppPlanReport) -> None:
    console.rule("[bold]Groundline App Plan[/bold]")
    console.print(f"App: {report.recipe.name}")
    console.print(f"Collection: {report.recipe.collection}")
    console.print(f"Data dir: {report.data_dir}")
    console.print(f"Collection exists: {'yes' if report.collection_exists else 'no'}")
    table = Table(title="Planned Steps")
    table.add_column("Step")
    table.add_column("Enabled")
    table.add_column("Destructive")
    table.add_column("Description")
    for step in report.steps:
        table.add_row(
            step.name,
            "yes" if step.enabled else "no",
            "yes" if step.destructive else "no",
            step.description,
        )
    console.print(table)
    if report.latest_artifact:
        console.print(f"Latest artifact: {report.latest_artifact.path}")


def _print_app_validation(report: AppValidationReport) -> None:
    console.rule("[bold]Groundline App Validate[/bold]")
    console.print(f"App: {report.recipe.name}")
    console.print(f"OK: {'yes' if report.ok else 'no'}")
    if not report.issues:
        console.print("No validation issues.")
        return
    table = Table(title="Validation Issues")
    table.add_column("Severity")
    table.add_column("Code")
    table.add_column("Message")
    table.add_column("Path")
    for issue in report.issues:
        table.add_row(
            issue.severity,
            issue.code,
            issue.message,
            issue.path or "",
        )
    console.print(table)


def _print_app_docs(report: AppDocumentRegistryReport) -> None:
    console.rule("[bold]Groundline App Docs[/bold]")
    console.print(f"Collection: {report.collection}")
    console.print(f"Docs path: {report.docs_path}")
    console.print(
        f"Sources: {report.sources_total}; indexed: {report.indexed_total}; "
        f"changed: {report.changed_total}; missing: {report.missing_total}"
    )
    table = Table(title="Document Registry")
    table.add_column("Status")
    table.add_column("Source")
    table.add_column("Doc ID")
    table.add_column("Version")
    table.add_column("Hash")
    table.add_column("Reason")
    for item in report.items:
        table.add_row(
            item.status,
            item.source_uri,
            item.doc_id or "",
            item.version_id or "",
            (item.content_hash or item.indexed_hash or "")[:12],
            item.reason or "",
        )
    console.print(table)


def _print_app_providers(report: ProviderReadinessReport) -> None:
    console.rule("[bold]Groundline App Providers[/bold]")
    console.print(f"OK: {'yes' if report.ok else 'no'}")
    console.print(f"Config: {report.provider_config_path}")
    console.print(f"Qdrant: {report.qdrant_url}")
    table = Table(title="Provider Readiness")
    table.add_column("Name")
    table.add_column("Provider")
    table.add_column("Status")
    table.add_column("Model")
    table.add_column("Dimension")
    table.add_column("Checks")
    for provider in report.providers:
        checks = "; ".join(f"{check.severity}:{check.code}" for check in provider.checks)
        table.add_row(
            provider.name,
            provider.provider,
            provider.status,
            provider.model,
            str(provider.dimension or ""),
            checks,
        )
    console.print(table)


def _print_app_status(report: AppStatusReport) -> None:
    table = Table(title=f"App Status: {report.recipe.name}")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Collection", report.recipe.collection)
    table.add_row("Docs", report.recipe.docs_path)
    table.add_row("Evalset", report.recipe.evalset)
    table.add_row(
        "Latest Artifact",
        report.latest_artifact.path if report.latest_artifact else "",
    )
    table.add_row("Recent Runs", str(len(report.runs)))
    if report.latest_run:
        table.add_row("Latest Run", f"{report.latest_run.operation} {report.latest_run.status}")
    console.print(table)


def _print_demo_summary(report: DemoReport) -> None:
    console.rule("[bold]Developer Demo[/bold]")
    console.print(f"Collection: {report.collection}")
    console.print(f"Data dir: {report.data_dir}")
    table = Table(title="Demo Steps")
    table.add_column("Step")
    table.add_column("OK")
    table.add_column("Run ID")
    table.add_column("Status")
    table.add_column("Events", justify="right")
    for step in report.steps:
        table.add_row(
            step.name,
            "yes" if step.ok else "no",
            step.run_id or "",
            step.status or "",
            str(step.events),
        )
    console.print(table)
    console.print(
        f"Documents: {len(report.ingest.documents)}; "
        f"contexts: {len(report.query_result.contexts)}; "
        f"runs persisted: {len(report.runs)}"
    )
    if report.answer.error:
        console.print(f"[yellow]Answer not generated[/yellow]: {report.answer.error}")


def _print_eval_queries(report: BaseModel) -> None:
    queries = getattr(report, "queries", [])
    if not queries:
        return
    table = Table(title="Eval Queries")
    table.add_column("Query")
    table.add_column("Type")
    table.add_column("Hit")
    table.add_column("First Hit", justify="right")
    table.add_column("Recall", justify="right")
    table.add_column("MRR", justify="right")
    table.add_column("Top Context")
    for result in queries:
        top_context = result.retrieved[0] if result.retrieved else None
        table.add_row(
            _preview(result.query, width=32),
            result.query_type,
            "yes" if result.hit else "no",
            str(result.first_hit_rank or ""),
            f"{result.recall_at_k:.3f}",
            f"{result.mrr:.3f}",
            _preview(
                " > ".join(
                    value
                    for value in [
                        top_context.title if top_context else None,
                        top_context.section if top_context else None,
                    ]
                    if value
                ),
                width=48,
            ),
        )
    console.print(table)


def _print_documents(
    engine: Groundline,
    collection: str,
    include_inactive: bool,
    limit: int,
) -> None:
    table = Table(title=f"Documents: {collection}")
    table.add_column("Document ID")
    table.add_column("Title")
    table.add_column("Active")
    table.add_column("Type")
    table.add_column("Source")
    table.add_column("Version ID")
    for document in engine.list_documents(
        collection,
        include_inactive=include_inactive,
    )[:limit]:
        table.add_row(
            document.doc_id,
            document.title or "",
            "yes" if document.is_active else "no",
            document.source_type,
            document.source_uri,
            document.current_version_id or "",
        )
    console.print(table)


def _print_chunks(
    engine: Groundline,
    collection: str,
    doc_id: str | None,
    include_inactive: bool,
    limit: int,
) -> None:
    table = Table(title=f"Chunks: {collection}")
    table.add_column("Chunk ID")
    table.add_column("Document ID")
    table.add_column("Active")
    table.add_column("Section")
    table.add_column("Preview")
    for chunk in engine.list_chunks(
        collection,
        doc_id=doc_id,
        include_inactive=include_inactive,
    )[:limit]:
        table.add_row(
            chunk.chunk_id,
            chunk.doc_id,
            "yes" if chunk.is_active and chunk.is_latest else "no",
            " > ".join(chunk.heading_path),
            _preview(chunk.content_text),
        )
    console.print(table)


def _print_document_detail(
    engine: Groundline,
    collection: str,
    doc_id: str,
    include_inactive: bool,
) -> None:
    detail = engine.get_document_detail(
        collection,
        doc_id,
        include_inactive=include_inactive,
    )
    if detail is None:
        console.print(f"[yellow]Document not found[/yellow] {doc_id}")
        return

    document = detail.document
    table = Table(title=f"Document: {doc_id}")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Title", document.title or "")
    table.add_row("Source", document.source_uri)
    table.add_row("Source Type", document.source_type)
    table.add_row("Active", "yes" if document.is_active else "no")
    table.add_row("Current Version", document.current_version_id or "")
    table.add_row("Tenant", document.tenant_id)
    table.add_row("Doc Type", document.doc_type or "")
    table.add_row("Domain", document.domain or "")
    table.add_row("Language", document.language or "")
    table.add_row("Chunks", str(detail.chunk_count))
    table.add_row("Active Chunks", str(detail.active_chunk_count))
    table.add_row("Latest Chunks", str(detail.latest_chunk_count))
    console.print(table)
    _print_document_versions(
        engine,
        collection=collection,
        doc_id=doc_id,
        include_inactive=include_inactive,
        limit=20,
    )


def _print_document_versions(
    engine: Groundline,
    collection: str,
    doc_id: str,
    include_inactive: bool,
    limit: int,
) -> None:
    table = Table(title=f"Versions: {doc_id}")
    table.add_column("Version ID")
    table.add_column("Latest")
    table.add_column("Active")
    table.add_column("Supersedes")
    table.add_column("Parser")
    table.add_column("Chunker")
    table.add_column("Hash")
    for version in engine.list_document_versions(
        collection,
        doc_id,
        include_inactive=include_inactive,
    )[:limit]:
        table.add_row(
            version.version_id,
            "yes" if version.is_latest else "no",
            "yes" if version.is_active else "no",
            version.supersedes or "",
            version.parser_version,
            version.chunker_version,
            version.content_hash[:12],
        )
    console.print(table)


def _require_doc_id(doc_id: str | None, target: str) -> str:
    if doc_id is None:
        raise typer.BadParameter(f"--doc-id is required for inspect {target}")
    return doc_id


def _preview(text: str, width: int = 80) -> str:
    compact = " ".join(text.split())
    if len(compact) <= width:
        return compact
    return compact[: width - 1] + "..."


def _build_query_filters(
    doc_type: str | None,
    domain: str | None,
    language: str | None,
    filters_json: str | None,
) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    if filters_json:
        filters.update(_parse_json_object(filters_json, option_name="--filters"))
    if doc_type is not None:
        filters["doc_type"] = doc_type
    if domain is not None:
        filters["domain"] = domain
    if language is not None:
        filters["language"] = language
    return filters


def _parse_json_object(value: str | None, option_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise typer.BadParameter(f"{option_name} must be valid JSON") from error
    if not isinstance(parsed, dict):
        raise typer.BadParameter(f"{option_name} must be a JSON object")
    return parsed


def _inspect_payload(
    engine: Groundline,
    target: str,
    collection: str,
    doc_id: str | None,
    include_inactive: bool,
    limit: int,
) -> dict[str, Any]:
    if target == "collections":
        return {"collections": engine.list_collections()}
    if target == "documents":
        return {
            "documents": [
                document.model_dump(mode="json")
                for document in engine.list_documents(
                    collection,
                    include_inactive=include_inactive,
                )[:limit]
            ]
        }
    if target in {"document", "doc"}:
        detail = engine.get_document_detail(
            collection,
            _require_doc_id(doc_id, target=target),
            include_inactive=include_inactive,
        )
        return {"document": detail.model_dump(mode="json") if detail else None}
    if target in {"versions", "document-versions"}:
        return {
            "versions": [
                version.model_dump(mode="json")
                for version in engine.list_document_versions(
                    collection,
                    _require_doc_id(doc_id, target=target),
                    include_inactive=include_inactive,
                )[:limit]
            ]
        }
    if target == "chunks":
        return {
            "chunks": [
                chunk.model_dump(mode="json")
                for chunk in engine.list_chunks(
                    collection,
                    doc_id=doc_id,
                    include_inactive=include_inactive,
                )[:limit]
            ]
        }
    raise typer.BadParameter(
        "target must be one of: collections, documents, document, versions, chunks"
    )


@app.command()
def delete(
    target: Annotated[str, typer.Argument(help="One of: document, collection.")],
    identifier: Annotated[str, typer.Argument(help="Document id or collection name.")],
    collection: Annotated[str, typer.Option(help="Collection name.")] = "demo",
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON."),
    ] = False,
    data_dir: Annotated[Path, typer.Option(help="Local Groundline data dir.")] = Path(
        ".groundline"
    ),
) -> None:
    engine = Groundline(Settings(data_dir=data_dir))
    normalized = target.lower()
    if normalized in {"document", "doc"}:
        result = engine.delete_document(collection, identifier)
        if json_output:
            _print_json_model(result)
            return
        if result.deleted:
            console.print(
                f"Deleted {result.doc_id}; deactivated {result.chunks_deactivated} chunks."
            )
        else:
            console.print(f"[yellow]Not deleted[/yellow] {result.doc_id}: {result.reason}")
        return
    if normalized == "collection":
        result = engine.delete_collection(identifier)
        if json_output:
            _print_json_model(result)
            return
        _print_collection_operation(result)
        return
    raise typer.BadParameter("target must be one of: document, collection")


@app.command()
def clear(
    target: Annotated[str, typer.Argument(help="Currently supported: collection.")] = "collection",
    collection: Annotated[str, typer.Option(help="Collection name.")] = "demo",
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON."),
    ] = False,
    data_dir: Annotated[Path, typer.Option(help="Local Groundline data dir.")] = Path(
        ".groundline"
    ),
) -> None:
    if target.lower() != "collection":
        raise typer.BadParameter("target must be collection")
    engine = Groundline(Settings(data_dir=data_dir))
    result = engine.clear_collection(collection)
    if json_output:
        _print_json_model(result)
        return
    _print_collection_operation(result)


def _print_collection_operation(result: CollectionOperationResponse) -> None:
    if not result.ok:
        console.print(
            f"[yellow]Collection {result.operation} skipped[/yellow] "
            f"{result.collection}: {result.reason}"
        )
        return
    action = "Cleared" if result.operation == "clear" else "Deleted"
    console.print(
        f"{action} collection {result.collection}; "
        f"removed {result.documents_removed} documents, "
        f"{result.versions_removed} versions, "
        f"{result.chunks_removed} chunks."
    )
    if result.vector_error:
        console.print(f"[yellow]Vector cleanup skipped[/yellow]: {result.vector_error}")


def _print_reindex_result(result: ReindexResponse) -> None:
    if not result.ok:
        console.print(
            f"[yellow]Reindex failed[/yellow] {result.collection}: "
            f"{result.reason or result.vector_error}"
        )
        return
    scope = f"document {result.doc_id}" if result.doc_id else "collection"
    console.print(
        f"Reindexed {scope} in {result.collection}; "
        f"indexed {result.chunks_indexed}/{result.chunks_considered} chunks."
    )


def _print_json_model(model: BaseModel) -> None:
    print(model.model_dump_json(indent=2))


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Host to bind."),
    port: int = typer.Option(8080, help="Port to bind."),
) -> None:
    import uvicorn

    uvicorn.run("groundline.app.main:app", host=host, port=port, reload=False)


@app.command()
def version() -> None:
    console.print("groundline 0.1.0a0")
