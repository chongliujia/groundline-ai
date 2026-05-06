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
def ingest(
    path: Annotated[Path, typer.Argument(help="File or directory to ingest.")],
    collection: Annotated[str, typer.Option(help="Collection name.")] = "demo",
    tenant_id: Annotated[str, typer.Option(help="Tenant id.")] = "default",
    title: Annotated[str | None, typer.Option(help="Document title for a single file.")] = None,
    doc_type: Annotated[str | None, typer.Option(help="Document type metadata.")] = None,
    domain: Annotated[str | None, typer.Option(help="Domain metadata.")] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON."),
    ] = False,
    data_dir: Annotated[Path, typer.Option(help="Local Groundline data dir.")] = Path(
        ".groundline"
    ),
) -> None:
    engine = Groundline(Settings(data_dir=data_dir))
    result = engine.ingest_path(
        path=path,
        collection=collection,
        tenant_id=tenant_id,
        title=title,
        doc_type=doc_type,
        domain=domain,
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
    top_k: Annotated[int, typer.Option(help="Number of contexts to return.")] = 8,
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
    result = engine.query(
        collection=collection,
        query=text,
        tenant_id=tenant_id,
        top_k=top_k,
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


@app.command()
def inspect(
    target: Annotated[
        str,
        typer.Argument(help="One of: collections, documents, chunks."),
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
    elif normalized == "chunks":
        _print_chunks(
            engine,
            collection=collection,
            doc_id=doc_id,
            include_inactive=include_inactive,
            limit=limit,
        )
    else:
        raise typer.BadParameter("target must be one of: collections, documents, chunks")


def _print_collections(engine: Groundline) -> None:
    table = Table(title="Collections")
    table.add_column("Collection")
    for collection in engine.list_collections():
        table.add_row(collection)
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


def _preview(text: str, width: int = 80) -> str:
    compact = " ".join(text.split())
    if len(compact) <= width:
        return compact
    return compact[: width - 1] + "..."


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
    raise typer.BadParameter("target must be one of: collections, documents, chunks")


@app.command()
def delete(
    target: Annotated[str, typer.Argument(help="Currently supported: document.")],
    identifier: Annotated[str, typer.Argument(help="Document id.")],
    collection: Annotated[str, typer.Option(help="Collection name.")] = "demo",
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Emit machine-readable JSON."),
    ] = False,
    data_dir: Annotated[Path, typer.Option(help="Local Groundline data dir.")] = Path(
        ".groundline"
    ),
) -> None:
    if target.lower() not in {"document", "doc"}:
        raise typer.BadParameter("target must be document")
    engine = Groundline(Settings(data_dir=data_dir))
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
