from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


BlockType = Literal[
    "heading",
    "paragraph",
    "list",
    "table",
    "image",
    "code",
    "quote",
    "header",
    "footer",
    "footnote",
    "page_break",
]


class GroundlineModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Document(GroundlineModel):
    doc_id: str
    tenant_id: str
    source_uri: str
    source_type: str
    title: str | None = None
    doc_type: str | None = None
    domain: str | None = None
    language: str | None = None
    current_version_id: str | None = None
    is_active: bool = True
    deleted_at: datetime | None = None
    acl_groups: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class DocumentVersion(GroundlineModel):
    doc_id: str
    version_id: str
    content_hash: str
    parser_version: str
    chunker_version: str
    embedding_model: str | None = None
    is_latest: bool = True
    is_active: bool = True
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    supersedes: str | None = None
    superseded_by: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Block(GroundlineModel):
    block_id: str
    doc_id: str
    version_id: str
    block_type: BlockType
    text: str | None = None
    markdown: str | None = None
    page: int | None = None
    bbox: list[float] | None = None
    heading_level: int | None = None
    heading_path: list[str] = Field(default_factory=list)
    table_id: str | None = None
    image_id: str | None = None
    confidence: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ImageAsset(GroundlineModel):
    image_id: str
    doc_id: str
    version_id: str
    image_uri: str
    page: int | None = None
    bbox: list[float] | None = None
    caption: str | None = None
    ocr_text: str | None = None
    visual_summary: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TableAsset(GroundlineModel):
    table_id: str
    doc_id: str
    version_id: str
    markdown: str
    html: str | None = None
    cells: list[dict[str, Any]] = Field(default_factory=list)
    page: int | None = None
    bbox: list[float] | None = None
    summary: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Chunk(GroundlineModel):
    chunk_id: str
    doc_id: str
    version_id: str
    tenant_id: str
    parent_chunk_id: str | None = None
    prev_chunk_id: str | None = None
    next_chunk_id: str | None = None
    title: str | None = None
    heading_path: list[str] = Field(default_factory=list)
    content_markdown: str
    content_text: str
    text_for_embedding: str
    block_ids: list[str] = Field(default_factory=list)
    image_ids: list[str] = Field(default_factory=list)
    table_ids: list[str] = Field(default_factory=list)
    page_start: int | None = None
    page_end: int | None = None
    doc_type: str | None = None
    domain: str | None = None
    language: str | None = None
    acl_groups: list[str] = Field(default_factory=list)
    content_hash: str
    embedding_hash: str | None = None
    is_latest: bool = True
    is_active: bool = True
    index_generation: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class RetrievalHit(GroundlineModel):
    chunk_id: str
    score: float
    source: str
    rank: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Citation(GroundlineModel):
    doc_id: str
    version_id: str
    chunk_id: str
    page_start: int | None = None
    page_end: int | None = None


class GroundedContext(GroundlineModel):
    chunk_id: str
    doc_id: str
    version_id: str
    title: str | None = None
    section: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    content_markdown: str
    source_uri: str | None = None
    citation: Citation
    scores: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PipelineEvent(GroundlineModel):
    event_id: str
    stage: str
    status: Literal["started", "completed", "skipped", "failed"]
    message: str | None = None
    doc_id: str | None = None
    source_uri: str | None = None
    duration_ms: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class PipelineRun(GroundlineModel):
    run_id: str
    operation: Literal[
        "ingest",
        "query",
        "answer",
        "reindex",
        "health",
        "clear",
        "delete",
    ]
    collection: str
    status: Literal["started", "completed", "failed"]
    events: list[PipelineEvent] = Field(default_factory=list)
    duration_ms: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None


class QueryRequest(GroundlineModel):
    query: str
    tenant_id: str = "default"
    user_groups: list[str] = Field(default_factory=list)
    top_k: int = 8
    context_window: int = Field(default=0, ge=0, le=5)
    max_context_chars: int = Field(default=12000, ge=1)
    filters: dict[str, Any] = Field(default_factory=dict)
    include_trace: bool = False


class QueryResponse(GroundlineModel):
    query: str
    contexts: list[GroundedContext] = Field(default_factory=list)
    trace: dict[str, Any] | None = None
    pipeline: PipelineRun | None = None


class AnswerRequest(QueryRequest):
    system_prompt: str | None = None


class AnswerResponse(GroundlineModel):
    query: str
    answer: str | None = None
    contexts: list[GroundedContext] = Field(default_factory=list)
    trace: dict[str, Any] | None = None
    error: str | None = None
    pipeline: PipelineRun | None = None


class ProviderStatus(GroundlineModel):
    name: Literal["llm", "embedding", "rerank"]
    provider: str
    model: str
    base_url: str
    endpoint_path: str
    api_key_env: str
    api_key_configured: bool
    timeout_seconds: int
    dimension: int | None = None


class ProviderStatusResponse(GroundlineModel):
    providers: list[ProviderStatus] = Field(default_factory=list)


class DocumentIndexHealth(GroundlineModel):
    doc_id: str
    title: str | None = None
    is_active: bool
    chunks_total: int = 0
    active_chunks: int = 0
    latest_chunks: int = 0
    vector_points: int | None = None
    missing_vectors: int | None = None
    extra_vectors: int | None = None
    needs_reindex: bool = False


class VectorIndexHealth(GroundlineModel):
    enabled: bool
    backend: str = "qdrant"
    expected_points: int = 0
    actual_points: int | None = None
    missing_points: int | None = None
    extra_points: int | None = None
    needs_reindex: bool = False
    error: str | None = None


class CollectionHealthReport(GroundlineModel):
    collection: str
    exists: bool
    ok: bool
    status: Literal[
        "ready",
        "embedding_disabled",
        "needs_reindex",
        "vector_unavailable",
        "missing",
    ]
    documents_total: int = 0
    active_documents: int = 0
    chunks_total: int = 0
    active_chunks: int = 0
    latest_chunks: int = 0
    vector_index: VectorIndexHealth
    documents: list[DocumentIndexHealth] = Field(default_factory=list)
    reason: str | None = None
    pipeline: PipelineRun | None = None


class IngestRequest(GroundlineModel):
    source_uri: str
    tenant_id: str = "default"
    title: str | None = None
    doc_type: str | None = None
    domain: str | None = None
    language: str | None = None
    acl_groups: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestedDocument(GroundlineModel):
    doc_id: str
    version_id: str
    source_uri: str
    source_type: str
    title: str | None = None
    chunk_count: int


class SkippedSource(GroundlineModel):
    source_uri: str
    reason: str


class IngestResponse(GroundlineModel):
    collection: str
    documents: list[IngestedDocument] = Field(default_factory=list)
    skipped: list[SkippedSource] = Field(default_factory=list)
    pipeline: PipelineRun | None = None


class CollectionOperationResponse(GroundlineModel):
    collection: str
    operation: Literal["clear", "delete"]
    ok: bool
    documents_removed: int = 0
    versions_removed: int = 0
    chunks_removed: int = 0
    vector_collection_deleted: bool = False
    reason: str | None = None
    vector_error: str | None = None
    pipeline: PipelineRun | None = None


class ReindexResponse(GroundlineModel):
    collection: str
    doc_id: str | None = None
    ok: bool
    chunks_considered: int = 0
    chunks_indexed: int = 0
    vector_collection_deleted: bool = False
    vector_points_deleted: int = 0
    reason: str | None = None
    vector_error: str | None = None
    pipeline: PipelineRun | None = None


class DeleteResponse(GroundlineModel):
    collection: str
    doc_id: str
    deleted: bool
    chunks_deactivated: int = 0
    vector_points_deleted: int = 0
    reason: str | None = None
    vector_error: str | None = None
    pipeline: PipelineRun | None = None


class DocumentDetail(GroundlineModel):
    collection: str
    document: Document
    versions: list[DocumentVersion] = Field(default_factory=list)
    chunk_count: int = 0
    active_chunk_count: int = 0
    latest_chunk_count: int = 0


class EvalItem(GroundlineModel):
    query: str
    gold_chunk_ids: list[str] = Field(default_factory=list)
    gold_doc_ids: list[str] = Field(default_factory=list)
    gold_source_uris: list[str] = Field(default_factory=list)
    query_type: str = "default"


class EvalRequest(GroundlineModel):
    dataset_path: str
    tenant_id: str = "default"
    top_k: int = 8


class EvalMetrics(GroundlineModel):
    recall_at_k: float
    mrr: float
    queries: int


class EvalRetrievedContext(GroundlineModel):
    rank: int
    chunk_id: str
    doc_id: str
    title: str | None = None
    section: str | None = None
    scores: dict[str, float] = Field(default_factory=dict)


class EvalQueryResult(GroundlineModel):
    query: str
    query_type: str
    gold_chunk_ids: list[str] = Field(default_factory=list)
    gold_doc_ids: list[str] = Field(default_factory=list)
    gold_source_uris: list[str] = Field(default_factory=list)
    resolved_gold_doc_ids: list[str] = Field(default_factory=list)
    retrieved: list[EvalRetrievedContext] = Field(default_factory=list)
    recall_at_k: float
    mrr: float
    hit: bool
    first_hit_rank: int | None = None
    matched_doc_ids: list[str] = Field(default_factory=list)
    matched_chunk_ids: list[str] = Field(default_factory=list)
    trace: dict[str, Any] | None = None


class EvalReport(GroundlineModel):
    collection: str
    top_k: int
    metrics: EvalMetrics
    by_query_type: dict[str, EvalMetrics] = Field(default_factory=dict)
    queries: list[EvalQueryResult] = Field(default_factory=list)


class DemoRequest(GroundlineModel):
    collection: str = "demo"
    docs_path: str = "examples/quickstart/docs"
    evalset: str = "examples/quickstart/evalset.example.jsonl"
    query_text: str = "住宿标准"
    context_window: int = Field(default=1, ge=0, le=5)


class DemoStepReport(GroundlineModel):
    name: str
    ok: bool
    run_id: str | None = None
    status: str | None = None
    events: int = 0


class DemoReport(GroundlineModel):
    collection: str
    data_dir: str
    docs_path: str
    evalset: str
    query: str
    steps: list[DemoStepReport] = Field(default_factory=list)
    providers: ProviderStatusResponse
    cleared: CollectionOperationResponse
    ingest: IngestResponse
    health: CollectionHealthReport
    query_result: QueryResponse
    answer: AnswerResponse
    eval: EvalReport
    reindex: ReindexResponse
    health_after_reindex: CollectionHealthReport
    runs: list[PipelineRun] = Field(default_factory=list)


class AppRecipe(GroundlineModel):
    name: str = "groundline-demo"
    collection: str = "demo"
    docs_path: str = "examples/quickstart/docs"
    evalset: str = "examples/quickstart/evalset.example.jsonl"
    query_text: str = "住宿标准"
    top_k: int = Field(default=8, ge=1, le=100)
    context_window: int = Field(default=1, ge=0, le=5)
    max_context_chars: int = Field(default=12000, ge=1)
    reset_collection: bool = False
    run_query: bool = True
    run_answer: bool = True
    run_eval: bool = False
    run_reindex: bool = False
    include_trace: bool = True
    artifacts_dir: str = ".groundline/artifacts"


class AppArtifact(GroundlineModel):
    kind: str
    path: str


class AppTemplateFile(GroundlineModel):
    path: str
    created: bool


class AppInitReport(GroundlineModel):
    project_dir: str
    recipe_path: str
    files: list[AppTemplateFile] = Field(default_factory=list)


class AppPlanStep(GroundlineModel):
    name: str
    enabled: bool = True
    description: str
    destructive: bool = False


class AppPlanReport(GroundlineModel):
    recipe: AppRecipe
    data_dir: str
    collection_exists: bool
    providers: ProviderStatusResponse
    latest_artifact: AppArtifact | None = None
    steps: list[AppPlanStep] = Field(default_factory=list)


class AppValidationIssue(GroundlineModel):
    severity: Literal["error", "warning", "info"]
    code: str
    message: str
    path: str | None = None


class AppValidationReport(GroundlineModel):
    recipe: AppRecipe
    ok: bool
    issues: list[AppValidationIssue] = Field(default_factory=list)
    plan: AppPlanReport


class AppSourceSnapshot(GroundlineModel):
    path: str
    source_type: str
    content_hash: str
    bytes: int


class AppRunManifest(GroundlineModel):
    manifest_version: str = "app-manifest.v0.1"
    recipe_hash: str
    collection: str
    data_dir: str
    docs_path: str
    evalset: str
    query_text: str
    started_at: datetime
    finished_at: datetime
    duration_ms: float
    sources: list[AppSourceSnapshot] = Field(default_factory=list)
    providers: ProviderStatusResponse
    steps: list[DemoStepReport] = Field(default_factory=list)
    run_ids: list[str] = Field(default_factory=list)


class AppExecutionReport(GroundlineModel):
    collection: str
    data_dir: str
    docs_path: str
    evalset: str
    query: str
    steps: list[DemoStepReport] = Field(default_factory=list)
    providers: ProviderStatusResponse
    manifest: AppRunManifest
    cleared: CollectionOperationResponse | None = None
    ingest: IngestResponse
    health: CollectionHealthReport
    query_result: QueryResponse | None = None
    answer: AnswerResponse | None = None
    eval: EvalReport | None = None
    reindex: ReindexResponse | None = None
    health_after_reindex: CollectionHealthReport | None = None
    runs: list[PipelineRun] = Field(default_factory=list)


class AppRunReport(GroundlineModel):
    recipe: AppRecipe
    run: AppExecutionReport
    demo: DemoReport | None = None
    artifacts: list[AppArtifact] = Field(default_factory=list)


class AppStatusReport(GroundlineModel):
    recipe: AppRecipe
    latest_artifact: AppArtifact | None = None
    latest_run: PipelineRun | None = None
    runs: list[PipelineRun] = Field(default_factory=list)
