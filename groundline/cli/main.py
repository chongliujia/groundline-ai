from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

from groundline.core.config import Settings
from groundline.core.engine import Groundline
from groundline.core.schemas import CollectionOperationResponse
from groundline.evals.runner import run_eval

app = typer.Typer(help="Groundline CLI")
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
