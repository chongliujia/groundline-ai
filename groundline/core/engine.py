from __future__ import annotations

from pathlib import Path
from uuid import UUID

from groundline.adapters.embedding.factory import build_embedder
from groundline.adapters.llm.factory import build_llm
from groundline.adapters.metadata.sqlite_store import SQLiteMetadataStore
from groundline.adapters.rerank.factory import build_reranker
from groundline.adapters.search.bm25_store import InMemoryBM25Store
from groundline.adapters.vector.qdrant_store import QdrantVectorStore
from groundline.core.config import Settings
from groundline.core.errors import (
    BackendUnavailableError,
    GroundlineError,
    ProviderConfigurationError,
    UnsupportedSourceTypeError,
)
from groundline.core.hashing import hash_file
from groundline.core.ids import new_id
from groundline.core.pipeline import PipelineRecorder, RunStatus
from groundline.core.schemas import (
    AnswerResponse,
    Chunk,
    CollectionHealthReport,
    CollectionOperationResponse,
    DeleteResponse,
    Document,
    DocumentDetail,
    DocumentIndexHealth,
    DocumentVersion,
    GroundedContext,
    IngestedDocument,
    IngestResponse,
    PipelineRun,
    ProviderStatus,
    ProviderStatusResponse,
    QueryResponse,
    ReindexResponse,
    RetrievalHit,
    SkippedSource,
    VectorIndexHealth,
    utc_now,
)
from groundline.ingestion.chunker import CHUNKER_VERSION, ChunkerConfig, HeadingAwareChunker
from groundline.ingestion.loader import infer_source_type, iter_local_documents
from groundline.ingestion.parser import PARSER_VERSION, ParserRegistry
from groundline.retrieval.context_builder import chunk_to_context, pack_adjacent_chunks
from groundline.retrieval.fusion import reciprocal_rank_fusion
from groundline.retrieval.prompt_builder import build_answer_messages
from groundline.retrieval.trace import empty_trace


class Groundline:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.metadata = SQLiteMetadataStore(settings.resolved_sqlite_path)
        self.parsers = ParserRegistry()
        self.providers = settings.providers

    @classmethod
    def from_local(cls, data_dir: Path = Path(".groundline")) -> Groundline:
        return cls(Settings(data_dir=data_dir))

    def list_collections(self) -> list[str]:
        return self.metadata.list_collections()

    def list_pipeline_runs(
        self,
        collection: str | None = None,
        operation: str | None = None,
        limit: int = 20,
    ) -> list[PipelineRun]:
        return self.metadata.list_pipeline_runs(
            collection=collection,
            operation=operation,
            limit=max(limit, 1),
        )

    def get_pipeline_run(self, run_id: str) -> PipelineRun | None:
        return self.metadata.get_pipeline_run(run_id)

    def provider_status(self) -> ProviderStatusResponse:
        providers = self.providers
        return ProviderStatusResponse(
            providers=[
                ProviderStatus(
                    name="llm",
                    provider=providers.llm.provider,
                    model=providers.llm.model,
                    base_url=providers.llm.base_url,
                    endpoint_path=providers.llm.endpoint_path,
                    api_key_env=providers.llm.api_key_env,
                    api_key_configured=bool(providers.llm.api_key),
                    timeout_seconds=providers.llm.timeout_seconds,
                ),
                ProviderStatus(
                    name="embedding",
                    provider=providers.embedding.provider,
                    model=providers.embedding.model,
                    base_url=providers.embedding.base_url,
                    endpoint_path=providers.embedding.endpoint_path,
                    api_key_env=providers.embedding.api_key_env,
                    api_key_configured=bool(providers.embedding.api_key),
                    timeout_seconds=providers.embedding.timeout_seconds,
                    dimension=providers.embedding.dimension,
                ),
                ProviderStatus(
                    name="rerank",
                    provider=providers.rerank.provider,
                    model=providers.rerank.model,
                    base_url=providers.rerank.base_url,
                    endpoint_path=providers.rerank.endpoint_path,
                    api_key_env=providers.rerank.api_key_env,
                    api_key_configured=bool(providers.rerank.api_key),
                    timeout_seconds=providers.rerank.timeout_seconds,
                ),
            ]
        )

    def collection_health(
        self,
        collection: str,
        include_documents: bool = True,
    ) -> CollectionHealthReport:
        pipeline = PipelineRecorder(
            "health",
            collection,
            metadata={"include_documents": include_documents},
        )
        if not self.metadata.collection_exists(collection):
            pipeline.event("collection_lookup", status="failed", message="collection not found")
            return CollectionHealthReport(
                collection=collection,
                exists=False,
                ok=False,
                status="missing",
                vector_index=VectorIndexHealth(enabled=False),
                reason="collection not found",
                pipeline=self._complete_pipeline(pipeline, status="failed"),
            )

        documents = self.list_documents(collection, include_inactive=True)
        chunks = self.list_chunks(collection, include_inactive=True)
        active_chunks = [chunk for chunk in chunks if chunk.is_active]
        latest_chunks = [chunk for chunk in chunks if chunk.is_active and chunk.is_latest]
        pipeline.event(
            "metadata_counts",
            metadata={
                "documents_total": len(documents),
                "chunks_total": len(chunks),
                "latest_chunks": len(latest_chunks),
            },
        )
        latest_chunks_by_doc = self._count_chunks_by_doc(latest_chunks)
        active_chunks_by_doc = self._count_chunks_by_doc(active_chunks)
        chunks_by_doc = self._count_chunks_by_doc(chunks)
        embedding_enabled = self.providers.embedding.provider.lower() not in {
            "none",
            "disabled",
        }
        vector_points_by_doc: dict[str, int] = {}
        vector_error: str | None = None
        actual_points: int | None = None

        if embedding_enabled:
            try:
                store = QdrantVectorStore(url=self.settings.qdrant_url)
                actual_points = store.count_points(collection)
                pipeline.event(
                    "vector_count",
                    metadata={"actual_points": actual_points},
                )
                if include_documents:
                    vector_points_by_doc = {
                        document.doc_id: store.count_points(collection, document.doc_id)
                        for document in documents
                    }
                    pipeline.event(
                        "document_vector_counts",
                        metadata={"documents": len(vector_points_by_doc)},
                    )
            except (BackendUnavailableError, ImportError) as error:
                vector_error = str(error)
                pipeline.event("vector_count", status="failed", message=vector_error)
        else:
            pipeline.event("vector_count", status="skipped", message="embedding disabled")

        expected_points = len(latest_chunks) if embedding_enabled else 0
        if actual_points is None:
            missing_points = None
            extra_points = None
        else:
            missing_points = max(expected_points - actual_points, 0)
            extra_points = max(actual_points - expected_points, 0)
        document_reports = (
            [
                self._document_index_health(
                    document,
                    chunks_total=chunks_by_doc.get(document.doc_id, 0),
                    active_chunks=active_chunks_by_doc.get(document.doc_id, 0),
                    latest_chunks=latest_chunks_by_doc.get(document.doc_id, 0),
                    vector_points=vector_points_by_doc.get(document.doc_id)
                    if embedding_enabled and vector_error is None
                    else None,
                )
                for document in documents
            ]
            if include_documents
            else []
        )
        needs_reindex = bool(
            embedding_enabled
            and vector_error is None
            and (
                (missing_points or 0) > 0
                or (extra_points or 0) > 0
                or any(report.needs_reindex for report in document_reports)
            )
        )
        vector_index = VectorIndexHealth(
            enabled=embedding_enabled,
            expected_points=expected_points,
            actual_points=actual_points,
            missing_points=missing_points,
            extra_points=extra_points,
            needs_reindex=needs_reindex,
            error=vector_error,
        )
        if vector_error:
            status = "vector_unavailable"
        elif not embedding_enabled:
            status = "embedding_disabled"
        elif needs_reindex:
            status = "needs_reindex"
        else:
            status = "ready"
        return CollectionHealthReport(
            collection=collection,
            exists=True,
            ok=status in {"ready", "embedding_disabled"},
            status=status,
            documents_total=len(documents),
            active_documents=len([document for document in documents if document.is_active]),
            chunks_total=len(chunks),
            active_chunks=len(active_chunks),
            latest_chunks=len(latest_chunks),
            vector_index=vector_index,
            documents=document_reports,
            pipeline=self._complete_pipeline(
                pipeline,
                status="failed" if status == "vector_unavailable" else "completed",
                metadata={"status": status},
            ),
        )

    def list_documents(
        self,
        collection: str,
        include_inactive: bool = False,
    ) -> list[Document]:
        documents = self.metadata.list_documents(collection)
        if include_inactive:
            return documents
        return [document for document in documents if document.is_active]

    def list_chunks(
        self,
        collection: str,
        doc_id: str | None = None,
        include_inactive: bool = False,
    ) -> list[Chunk]:
        chunks = self.metadata.list_chunks(collection)
        if not include_inactive:
            chunks = [chunk for chunk in chunks if chunk.is_active and chunk.is_latest]
        if doc_id is None:
            return chunks
        return [chunk for chunk in chunks if chunk.doc_id == doc_id]

    def get_document(
        self,
        collection: str,
        doc_id: str,
        include_inactive: bool = False,
    ) -> Document | None:
        document = self.metadata.get_document(collection, doc_id)
        if document is None:
            return None
        if not include_inactive and not document.is_active:
            return None
        return document

    def list_document_versions(
        self,
        collection: str,
        doc_id: str,
        include_inactive: bool = False,
    ) -> list[DocumentVersion]:
        versions = self.metadata.list_versions(collection, doc_id)
        if include_inactive:
            return versions
        return [version for version in versions if version.is_active]

    def get_document_detail(
        self,
        collection: str,
        doc_id: str,
        include_inactive: bool = False,
    ) -> DocumentDetail | None:
        document = self.get_document(
            collection,
            doc_id,
            include_inactive=include_inactive,
        )
        if document is None:
            return None
        chunks = self.list_chunks(
            collection,
            doc_id=doc_id,
            include_inactive=True,
        )
        return DocumentDetail(
            collection=collection,
            document=document,
            versions=self.list_document_versions(
                collection,
                doc_id,
                include_inactive=include_inactive,
            ),
            chunk_count=len(chunks),
            active_chunk_count=len([chunk for chunk in chunks if chunk.is_active]),
            latest_chunk_count=len(
                [chunk for chunk in chunks if chunk.is_active and chunk.is_latest]
            ),
        )

    def clear_collection(self, collection: str) -> CollectionOperationResponse:
        pipeline = PipelineRecorder("clear", collection)
        if not self.metadata.collection_exists(collection):
            pipeline.event("collection_lookup", status="failed", message="collection not found")
            return CollectionOperationResponse(
                collection=collection,
                operation="clear",
                ok=False,
                reason="collection not found",
                pipeline=self._complete_pipeline(pipeline, status="failed"),
            )
        documents, versions, chunks = self.metadata.clear_collection(collection)
        pipeline.event(
            "metadata_clear",
            metadata={
                "documents_removed": documents,
                "versions_removed": versions,
                "chunks_removed": chunks,
            },
        )
        vector_deleted, vector_error = self._try_delete_vector_collection(collection)
        pipeline.event(
            "vector_delete_collection",
            status="failed" if vector_error else "completed",
            message=vector_error,
            metadata={"deleted": vector_deleted},
        )
        return CollectionOperationResponse(
            collection=collection,
            operation="clear",
            ok=True,
            documents_removed=documents,
            versions_removed=versions,
            chunks_removed=chunks,
            vector_collection_deleted=vector_deleted,
            vector_error=vector_error,
            pipeline=self._complete_pipeline(pipeline),
        )

    def delete_collection(self, collection: str) -> CollectionOperationResponse:
        pipeline = PipelineRecorder("delete", collection)
        if not self.metadata.collection_exists(collection):
            pipeline.event("collection_lookup", status="failed", message="collection not found")
            return CollectionOperationResponse(
                collection=collection,
                operation="delete",
                ok=False,
                reason="collection not found",
                pipeline=self._complete_pipeline(pipeline, status="failed"),
            )
        documents, versions, chunks = self.metadata.delete_collection(collection)
        pipeline.event(
            "metadata_delete",
            metadata={
                "documents_removed": documents,
                "versions_removed": versions,
                "chunks_removed": chunks,
            },
        )
        vector_deleted, vector_error = self._try_delete_vector_collection(collection)
        pipeline.event(
            "vector_delete_collection",
            status="failed" if vector_error else "completed",
            message=vector_error,
            metadata={"deleted": vector_deleted},
        )
        return CollectionOperationResponse(
            collection=collection,
            operation="delete",
            ok=True,
            documents_removed=documents,
            versions_removed=versions,
            chunks_removed=chunks,
            vector_collection_deleted=vector_deleted,
            vector_error=vector_error,
            pipeline=self._complete_pipeline(pipeline),
        )

    def reindex_collection(
        self,
        collection: str,
        doc_id: str | None = None,
    ) -> ReindexResponse:
        pipeline = PipelineRecorder("reindex", collection, metadata={"doc_id": doc_id})
        if not self.metadata.collection_exists(collection):
            pipeline.event("collection_lookup", status="failed", message="collection not found")
            return ReindexResponse(
                collection=collection,
                doc_id=doc_id,
                ok=False,
                reason="collection not found",
                pipeline=self._complete_pipeline(pipeline, status="failed"),
            )
        if doc_id is not None and self.get_document(collection, doc_id) is None:
            pipeline.event(
                "document_lookup",
                status="failed",
                doc_id=doc_id,
                message="document not found",
            )
            return ReindexResponse(
                collection=collection,
                doc_id=doc_id,
                ok=False,
                reason="document not found",
                pipeline=self._complete_pipeline(pipeline, status="failed"),
            )

        chunks = self.list_chunks(collection, doc_id=doc_id)
        pipeline.event(
            "chunk_load",
            doc_id=doc_id,
            metadata={"chunks_considered": len(chunks)},
        )
        if self.providers.embedding.provider.lower() in {"none", "disabled"}:
            pipeline.event("embedding", status="skipped", message="embedding disabled")
            return ReindexResponse(
                collection=collection,
                doc_id=doc_id,
                ok=False,
                chunks_considered=len(chunks),
                reason="embedding disabled",
                vector_error="embedding disabled",
                pipeline=self._complete_pipeline(pipeline, status="failed"),
            )
        if doc_id is None:
            vector_collection_deleted, vector_error = self._try_delete_vector_collection(
                collection
            )
            vector_points_deleted = 0
            pipeline.event(
                "vector_delete_collection",
                status="failed" if vector_error else "completed",
                message=vector_error,
                metadata={"deleted": vector_collection_deleted},
            )
        else:
            vector_points_deleted, vector_error = self._try_delete_document_vectors(
                collection,
                doc_id,
            )
            vector_collection_deleted = False
            pipeline.event(
                "vector_delete_document",
                status="failed" if vector_error else "completed",
                doc_id=doc_id,
                message=vector_error,
                metadata={"points_deleted": vector_points_deleted},
            )

        if vector_error:
            return ReindexResponse(
                collection=collection,
                doc_id=doc_id,
                ok=False,
                chunks_considered=len(chunks),
                vector_collection_deleted=vector_collection_deleted,
                vector_points_deleted=vector_points_deleted,
                vector_error=vector_error,
                pipeline=self._complete_pipeline(pipeline, status="failed"),
            )

        index_error = self._try_index_vectors(collection, chunks)
        pipeline.event(
            "vector_index",
            status="failed" if index_error else "completed",
            message=index_error,
            metadata={"chunks_indexed": 0 if index_error else len(chunks)},
        )
        if index_error:
            return ReindexResponse(
                collection=collection,
                doc_id=doc_id,
                ok=False,
                chunks_considered=len(chunks),
                vector_collection_deleted=vector_collection_deleted,
                vector_points_deleted=vector_points_deleted,
                reason=index_error,
                vector_error=index_error,
                pipeline=self._complete_pipeline(pipeline, status="failed"),
            )

        return ReindexResponse(
            collection=collection,
            doc_id=doc_id,
            ok=True,
            chunks_considered=len(chunks),
            chunks_indexed=len(chunks),
            vector_collection_deleted=vector_collection_deleted,
            vector_points_deleted=vector_points_deleted,
            pipeline=self._complete_pipeline(
                pipeline,
                metadata={"chunks_indexed": len(chunks)},
            ),
        )

    def delete_document(self, collection: str, doc_id: str) -> DeleteResponse:
        pipeline = PipelineRecorder("delete", collection, metadata={"doc_id": doc_id})
        document = self.metadata.get_document(collection, doc_id)
        if document is None:
            pipeline.event(
                "document_lookup",
                status="failed",
                doc_id=doc_id,
                message="document not found",
            )
            return DeleteResponse(
                collection=collection,
                doc_id=doc_id,
                deleted=False,
                reason="document not found",
                pipeline=self._complete_pipeline(pipeline, status="failed"),
            )
        if not document.is_active:
            pipeline.event(
                "document_lookup",
                status="skipped",
                doc_id=doc_id,
                message="document already inactive",
            )
            return DeleteResponse(
                collection=collection,
                doc_id=doc_id,
                deleted=False,
                reason="document already inactive",
                pipeline=self._complete_pipeline(pipeline, status="failed"),
            )
        chunks_deactivated = self.metadata.tombstone_document(collection, doc_id)
        pipeline.event(
            "metadata_tombstone",
            doc_id=doc_id,
            metadata={"chunks_deactivated": chunks_deactivated},
        )
        vector_points_deleted, vector_error = self._try_delete_document_vectors(
            collection,
            doc_id,
        )
        pipeline.event(
            "vector_delete_document",
            status="failed" if vector_error else "completed",
            doc_id=doc_id,
            message=vector_error,
            metadata={"points_deleted": vector_points_deleted},
        )
        return DeleteResponse(
            collection=collection,
            doc_id=doc_id,
            deleted=True,
            chunks_deactivated=chunks_deactivated,
            vector_points_deleted=vector_points_deleted,
            vector_error=vector_error,
            pipeline=self._complete_pipeline(pipeline),
        )

    def ingest_path(
        self,
        path: Path,
        collection: str,
        tenant_id: str = "default",
        title: str | None = None,
        doc_type: str | None = None,
        domain: str | None = None,
        language: str | None = None,
        acl_groups: list[str] | None = None,
        metadata: dict | None = None,
    ) -> IngestResponse:
        pipeline = PipelineRecorder(
            "ingest",
            collection,
            metadata={"path": str(path), "tenant_id": tenant_id},
        )
        self.metadata.create_collection(collection)
        pipeline.event("collection_ensure")
        documents: list[IngestedDocument] = []
        skipped: list[SkippedSource] = []

        for source in iter_local_documents(path):
            try:
                ingest_result = self._ingest_file(
                    source=source,
                    collection=collection,
                    tenant_id=tenant_id,
                    title=title if path.is_file() else None,
                    doc_type=doc_type,
                    domain=domain,
                    language=language,
                    acl_groups=acl_groups or [],
                    metadata=metadata or {},
                    pipeline=pipeline,
                )
                if isinstance(ingest_result, IngestedDocument):
                    documents.append(ingest_result)
                else:
                    skipped.append(ingest_result)
            except UnsupportedSourceTypeError as error:
                skipped.append(SkippedSource(source_uri=str(source), reason=str(error)))
                pipeline.event(
                    "source_load",
                    status="skipped",
                    source_uri=str(source),
                    message=str(error),
                )

        if path.is_file() and not documents and not skipped:
            raise GroundlineError(f"No supported document found at {path}")

        return IngestResponse(
            collection=collection,
            documents=documents,
            skipped=skipped,
            pipeline=self._complete_pipeline(
                pipeline,
                metadata={"documents": len(documents), "skipped": len(skipped)}
            ),
        )

    def _ingest_file(
        self,
        source: Path,
        collection: str,
        tenant_id: str,
        title: str | None,
        doc_type: str | None,
        domain: str | None,
        language: str | None,
        acl_groups: list[str],
        metadata: dict,
        pipeline: PipelineRecorder,
    ) -> IngestedDocument | SkippedSource:
        source_uri = str(source)
        pipeline.event("source_load", source_uri=source_uri)
        content_hash = hash_file(source)
        pipeline.event(
            "content_hash",
            source_uri=source_uri,
            metadata={"content_hash": content_hash},
        )
        existing_document = self.metadata.get_document_by_source_uri(collection, source_uri)
        existing_version = (
            self.metadata.get_version(
                collection,
                existing_document.doc_id,
                existing_document.current_version_id,
            )
            if existing_document and existing_document.current_version_id
            else None
        )
        if (
            existing_document
            and existing_document.is_active
            and existing_version
            and existing_version.is_active
            and existing_version.content_hash == content_hash
        ):
            pipeline.event(
                "dedupe",
                status="skipped",
                doc_id=existing_document.doc_id,
                source_uri=source_uri,
                message="unchanged content hash",
            )
            return SkippedSource(source_uri=source_uri, reason="unchanged content hash")

        doc_id = existing_document.doc_id if existing_document else new_id("doc")
        version_id = new_id("version")
        source_type = infer_source_type(source)
        document_title = (
            title or existing_document.title if existing_document else title or source.stem
        )

        document = (
            existing_document.model_copy(
                update={
                    "tenant_id": tenant_id,
                    "source_type": source_type,
                    "title": document_title,
                    "doc_type": doc_type,
                    "domain": domain,
                    "language": language,
                    "current_version_id": version_id,
                    "is_active": True,
                    "deleted_at": None,
                    "acl_groups": acl_groups,
                    "metadata": {**metadata, "path": source_uri},
                    "updated_at": utc_now(),
                }
            )
            if existing_document
            else Document(
                doc_id=doc_id,
                tenant_id=tenant_id,
                source_uri=source_uri,
                source_type=source_type,
                title=document_title,
                doc_type=doc_type,
                domain=domain,
                language=language,
                current_version_id=version_id,
                acl_groups=acl_groups,
                metadata={**metadata, "path": source_uri},
            )
        )
        version = DocumentVersion(
            doc_id=doc_id,
            version_id=version_id,
            content_hash=content_hash,
            parser_version=PARSER_VERSION,
            chunker_version=CHUNKER_VERSION,
            supersedes=existing_version.version_id if existing_version else None,
        )

        blocks = self.parsers.parse(source, doc_id=doc_id, version_id=version_id)
        pipeline.event(
            "parse",
            doc_id=doc_id,
            source_uri=source_uri,
            metadata={"blocks": len(blocks), "parser_version": PARSER_VERSION},
        )
        chunks = HeadingAwareChunker(
            ChunkerConfig(
                tenant_id=tenant_id,
                title=document_title,
                doc_type=doc_type,
                domain=domain,
                language=language,
                acl_groups=tuple(acl_groups),
                metadata=metadata,
            )
        ).chunk(blocks, doc_id=doc_id, version_id=version_id)
        pipeline.event(
            "chunk",
            doc_id=doc_id,
            source_uri=source_uri,
            metadata={"chunks": len(chunks), "chunker_version": CHUNKER_VERSION},
        )

        if existing_document:
            vector_points_deleted, vector_error = self._try_delete_document_vectors(
                collection,
                doc_id,
            )
            pipeline.event(
                "vector_delete_document",
                status="failed" if vector_error else "completed",
                doc_id=doc_id,
                source_uri=source_uri,
                message=vector_error,
                metadata={"points_deleted": vector_points_deleted},
            )
            self.metadata.deactivate_versions_for_document(
                collection,
                doc_id,
                superseded_by=version_id,
            )
            self.metadata.deactivate_chunks_for_document(collection, doc_id)
        self.metadata.put_document(collection, document)
        self.metadata.put_version(collection, version)
        self.metadata.put_chunks(collection, chunks)
        pipeline.event(
            "metadata_persist",
            doc_id=doc_id,
            source_uri=source_uri,
            metadata={"version_id": version_id},
        )
        vector_index_error = self._try_index_vectors(collection, chunks)
        pipeline.event(
            "vector_index",
            status="failed" if vector_index_error else "completed",
            doc_id=doc_id,
            source_uri=source_uri,
            message=vector_index_error,
            metadata={"chunks_indexed": 0 if vector_index_error else len(chunks)},
        )

        return IngestedDocument(
            doc_id=doc_id,
            version_id=version_id,
            source_uri=str(source),
            source_type=source_type,
            title=document_title,
            chunk_count=len(chunks),
        )

    def query(
        self,
        collection: str,
        query: str,
        tenant_id: str = "default",
        user_groups: list[str] | None = None,
        filters: dict[str, object] | None = None,
        top_k: int = 8,
        context_window: int = 0,
        max_context_chars: int = 12000,
        include_trace: bool = False,
    ) -> QueryResponse:
        pipeline = PipelineRecorder(
            "query",
            collection,
            metadata={
                "tenant_id": tenant_id,
                "top_k": top_k,
                "include_trace": include_trace,
            },
        )
        context_window = min(max(context_window, 0), 5)
        max_context_chars = max(max_context_chars, 1)
        chunks = [
            chunk
            for chunk in self.metadata.list_chunks(collection)
            if chunk.tenant_id == tenant_id
            and chunk.is_active
            and chunk.is_latest
            and self._is_allowed(chunk.acl_groups, user_groups or [])
            and self._matches_filters(chunk, filters or {})
        ]
        pipeline.event(
            "candidate_filter",
            metadata={"candidate_chunks": len(chunks), "filters": filters or {}},
        )
        chunk_by_id = {chunk.chunk_id: chunk for chunk in chunks}
        search = InMemoryBM25Store()
        search.index(collection, chunks)
        bm25_hits = search.search(collection, query, top_k=max(top_k, 20))
        pipeline.event("bm25_search", metadata={"hits": len(bm25_hits)})
        raw_vector_hits, vector_error = self._try_vector_search(
            collection,
            query,
            top_k=max(top_k, 20),
        )
        pipeline.event(
            "vector_search",
            status="failed" if vector_error and vector_error != "embedding disabled" else (
                "skipped" if vector_error == "embedding disabled" else "completed"
            ),
            message=vector_error,
            metadata={"raw_hits": len(raw_vector_hits)},
        )
        vector_hits = [hit for hit in raw_vector_hits if hit.chunk_id in chunk_by_id]
        hits = reciprocal_rank_fusion([bm25_hits, vector_hits], top_n=top_k)
        pipeline.event(
            "fusion",
            metadata={"method": "rrf", "fused_hits": len(hits)},
        )
        doc_by_id = {
            document.doc_id: document for document in self.metadata.list_documents(collection)
        }
        reranked_chunks, rerank_error = self._try_rerank(
            query,
            [chunk_by_id[hit.chunk_id] for hit in hits if hit.chunk_id in chunk_by_id],
        )
        pipeline.event(
            "rerank",
            status="skipped" if rerank_error == "rerank disabled" else (
                "failed" if rerank_error else "completed"
            ),
            message=rerank_error,
            metadata={"input_candidates": len(hits), "output_candidates": len(reranked_chunks)},
        )

        contexts: list[GroundedContext] = []
        hit_by_chunk_id = {hit.chunk_id: hit for hit in hits}
        packed_chunk_ids: set[str] = set()
        skipped_contexts: list[dict[str, object]] = []
        used_context_chars = 0
        for chunk, rerank_score in reranked_chunks:
            if chunk.chunk_id in packed_chunk_ids:
                skipped_contexts.append(
                    {
                        "chunk_id": chunk.chunk_id,
                        "reason": "anchor already included in higher-ranked packed context",
                    }
                )
                continue
            remaining_chars = max_context_chars - used_context_chars
            if remaining_chars <= 0:
                skipped_contexts.append(
                    {
                        "chunk_id": chunk.chunk_id,
                        "reason": "context character budget exhausted",
                    }
                )
                continue
            hit = hit_by_chunk_id.get(chunk.chunk_id)
            document = doc_by_id.get(chunk.doc_id)
            packed_chunks = pack_adjacent_chunks(
                anchor=chunk,
                chunk_by_id=chunk_by_id,
                context_window=context_window,
                max_chars=remaining_chars,
            )
            context = chunk_to_context(
                chunk,
                source_uri=document.source_uri if document else None,
                packed_chunks=packed_chunks,
            )
            if hit is not None:
                context.scores[f"{hit.source}_score"] = hit.score
            if rerank_score is not None:
                context.scores["rerank_score"] = rerank_score
            contexts.append(context)
            packed_chunk_ids.update(context.metadata["packed_chunk_ids"])
            used_context_chars += len(context.content_markdown)
        pipeline.event(
            "context_pack",
            metadata={
                "final_items": len(contexts),
                "used_context_chars": used_context_chars,
                "skipped_items": len(skipped_contexts),
            },
        )

        trace = None
        if include_trace:
            trace = empty_trace()
            trace["routing"] = {
                "collection": collection,
                "tenant_id": tenant_id,
                "user_groups": user_groups or [],
                "filters": filters or {},
            }
            trace["retrieval"] = {
                "bm25_hits": len(bm25_hits),
                "bm25_candidates": self._trace_hits(bm25_hits, chunk_by_id),
                "vector_hits_raw": len(raw_vector_hits),
                "vector_hits": len(vector_hits),
                "vector_candidates": self._trace_hits(vector_hits, chunk_by_id),
                "candidate_chunks": len(chunks),
            }
            if vector_error:
                trace["retrieval"]["vector_error"] = vector_error
            trace["fusion"] = {
                "method": "rrf",
                "fused_hits": len(hits),
                "candidates": self._trace_hits(hits, chunk_by_id, use_hit_rank=False),
            }
            trace["rerank"] = {
                "enabled": self.providers.rerank.provider.lower() not in {"none", "disabled"},
                "input_candidates": len(hits),
                "output_candidates": len(reranked_chunks),
                "candidates": self._trace_reranked_chunks(reranked_chunks),
            }
            if rerank_error:
                trace["rerank"]["error"] = rerank_error
            trace["context"] = {
                "final_items": len(contexts),
                "context_window": context_window,
                "max_context_chars": max_context_chars,
                "used_context_chars": used_context_chars,
                "skipped_items": skipped_contexts,
                "contexts": [
                    {
                        "rank": rank,
                        "chunk_id": context.chunk_id,
                        "doc_id": context.doc_id,
                        "title": context.title,
                        "section": context.section,
                        "scores": context.scores,
                        "packed_chunk_ids": context.metadata.get("packed_chunk_ids", []),
                        "chars": len(context.content_markdown),
                    }
                    for rank, context in enumerate(contexts, start=1)
                ],
            }

        return QueryResponse(
            query=query,
            contexts=contexts,
            trace=trace,
            pipeline=self._complete_pipeline(pipeline, metadata={"contexts": len(contexts)}),
        )

    def answer(
        self,
        collection: str,
        query: str,
        tenant_id: str = "default",
        user_groups: list[str] | None = None,
        filters: dict[str, object] | None = None,
        top_k: int = 8,
        context_window: int = 0,
        max_context_chars: int = 12000,
        include_trace: bool = False,
        system_prompt: str | None = None,
    ) -> AnswerResponse:
        pipeline = PipelineRecorder(
            "answer",
            collection,
            metadata={"top_k": top_k, "include_trace": include_trace},
        )
        query_response = self.query(
            collection=collection,
            query=query,
            tenant_id=tenant_id,
            user_groups=user_groups,
            filters=filters,
            top_k=top_k,
            context_window=context_window,
            max_context_chars=max_context_chars,
            include_trace=include_trace,
        )
        pipeline.event(
            "query",
            metadata={
                "query_run_id": query_response.pipeline.run_id
                if query_response.pipeline
                else None,
                "contexts": len(query_response.contexts),
            },
        )
        try:
            llm = build_llm(self.providers.llm)
            if llm is None:
                pipeline.event("llm_generate", status="skipped", message="llm disabled")
                return AnswerResponse(
                    query=query,
                    contexts=query_response.contexts,
                    trace=query_response.trace,
                    error="llm disabled",
                    pipeline=self._complete_pipeline(pipeline, status="failed"),
                )
            messages = build_answer_messages(
                query=query,
                contexts=query_response.contexts,
                system_prompt=system_prompt,
            )
            answer_text = llm.generate(messages)
            pipeline.event(
                "llm_generate",
                metadata={"messages": len(messages), "answer_chars": len(answer_text)},
            )
            return AnswerResponse(
                query=query,
                answer=answer_text,
                contexts=query_response.contexts,
                trace=query_response.trace,
                pipeline=self._complete_pipeline(pipeline),
            )
        except (BackendUnavailableError, ProviderConfigurationError, ImportError) as error:
            pipeline.event("llm_generate", status="failed", message=str(error))
            return AnswerResponse(
                query=query,
                contexts=query_response.contexts,
                trace=query_response.trace,
                error=str(error),
                pipeline=self._complete_pipeline(pipeline, status="failed"),
            )

    @staticmethod
    def _is_allowed(chunk_groups: list[str], user_groups: list[str]) -> bool:
        return not chunk_groups or bool(set(chunk_groups) & set(user_groups))

    @classmethod
    def _matches_filters(cls, chunk: Chunk, filters: dict[str, object]) -> bool:
        if not filters:
            return True

        for key, expected in filters.items():
            if expected is None:
                continue
            if key == "metadata" and isinstance(expected, dict):
                if not all(
                    cls._matches_value(chunk.metadata.get(metadata_key), metadata_value)
                    for metadata_key, metadata_value in expected.items()
                ):
                    return False
                continue
            if key.startswith("metadata."):
                metadata_key = key.removeprefix("metadata.")
                if not cls._matches_value(chunk.metadata.get(metadata_key), expected):
                    return False
                continue
            if not hasattr(chunk, key):
                return False
            if not cls._matches_value(getattr(chunk, key), expected):
                return False
        return True

    @staticmethod
    def _matches_value(actual: object, expected: object) -> bool:
        if isinstance(expected, list):
            return actual in expected
        return actual == expected

    @staticmethod
    def _trace_hits(
        hits: list[RetrievalHit],
        chunk_by_id: dict[str, Chunk],
        limit: int = 20,
        use_hit_rank: bool = True,
    ) -> list[dict[str, object]]:
        traced: list[dict[str, object]] = []
        for rank, hit in enumerate(hits[:limit], start=1):
            chunk = chunk_by_id.get(hit.chunk_id)
            traced.append(
                {
                    "rank": hit.rank if use_hit_rank and hit.rank is not None else rank,
                    "chunk_id": hit.chunk_id,
                    "doc_id": chunk.doc_id if chunk else hit.metadata.get("doc_id"),
                    "title": chunk.title if chunk else hit.metadata.get("title"),
                    "section": " > ".join(chunk.heading_path)
                    if chunk and chunk.heading_path
                    else None,
                    "source": hit.source,
                    "score": hit.score,
                }
            )
        return traced

    @staticmethod
    def _trace_reranked_chunks(
        reranked_chunks: list[tuple[Chunk, float | None]],
        limit: int = 20,
    ) -> list[dict[str, object]]:
        return [
            {
                "rank": rank,
                "chunk_id": chunk.chunk_id,
                "doc_id": chunk.doc_id,
                "title": chunk.title,
                "section": " > ".join(chunk.heading_path) if chunk.heading_path else None,
                "score": score,
            }
            for rank, (chunk, score) in enumerate(reranked_chunks[:limit], start=1)
        ]

    def _try_index_vectors(self, collection: str, chunks: list[Chunk]) -> str | None:
        if not chunks:
            return None
        try:
            embedder = build_embedder(self.providers.embedding)
            if embedder is None:
                return "embedding disabled"
            vectors = embedder.embed([chunk.text_for_embedding for chunk in chunks])
            store = QdrantVectorStore(
                url=self.settings.qdrant_url,
                vector_size=len(vectors[0]),
            )
            store.upsert(
                collection,
                [
                    (
                        self._vector_point_id(chunk.chunk_id),
                        vector,
                        {
                            "chunk_id": chunk.chunk_id,
                            "doc_id": chunk.doc_id,
                            "version_id": chunk.version_id,
                            "tenant_id": chunk.tenant_id,
                            "title": chunk.title,
                            "doc_type": chunk.doc_type,
                            "domain": chunk.domain,
                            "language": chunk.language,
                            "metadata": chunk.metadata,
                        },
                    )
                    for chunk, vector in zip(chunks, vectors, strict=True)
                ],
            )
            return None
        except (BackendUnavailableError, ProviderConfigurationError, ImportError) as error:
            return str(error)

    def _try_vector_search(
        self,
        collection: str,
        query: str,
        top_k: int,
    ) -> tuple[list[RetrievalHit], str | None]:
        try:
            embedder = build_embedder(self.providers.embedding)
            if embedder is None:
                return [], "embedding disabled"
            vector = embedder.embed([query])[0]
            store = QdrantVectorStore(
                url=self.settings.qdrant_url,
                vector_size=len(vector),
            )
            return store.search(collection, vector, top_k=top_k), None
        except (BackendUnavailableError, ProviderConfigurationError, ImportError) as error:
            return [], str(error)

    def _try_delete_vector_collection(self, collection: str) -> tuple[bool, str | None]:
        try:
            store = QdrantVectorStore(url=self.settings.qdrant_url)
            return store.delete_collection(collection), None
        except (BackendUnavailableError, ImportError) as error:
            return False, str(error)

    def _try_delete_document_vectors(
        self,
        collection: str,
        doc_id: str,
    ) -> tuple[int, str | None]:
        if self.providers.embedding.provider.lower() in {"none", "disabled"}:
            return 0, None
        try:
            store = QdrantVectorStore(url=self.settings.qdrant_url)
            return store.delete_by_doc_id(collection, doc_id), None
        except (BackendUnavailableError, ImportError) as error:
            return 0, str(error)

    def _try_rerank(
        self,
        query: str,
        candidates: list[Chunk],
    ) -> tuple[list[tuple[Chunk, float | None]], str | None]:
        try:
            reranker = build_reranker(self.providers.rerank)
            if reranker is None:
                return [(chunk, None) for chunk in candidates], "rerank disabled"
            return reranker.rerank(query, candidates), None
        except (ProviderConfigurationError, ImportError) as error:
            return [(chunk, None) for chunk in candidates], str(error)

    def _complete_pipeline(
        self,
        pipeline: PipelineRecorder,
        status: RunStatus = "completed",
        metadata: dict[str, object] | None = None,
    ) -> PipelineRun:
        run = pipeline.complete(status=status, metadata=metadata)
        self.metadata.put_pipeline_run(run)
        return run

    @staticmethod
    def _count_chunks_by_doc(chunks: list[Chunk]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for chunk in chunks:
            counts[chunk.doc_id] = counts.get(chunk.doc_id, 0) + 1
        return counts

    @staticmethod
    def _document_index_health(
        document: Document,
        chunks_total: int,
        active_chunks: int,
        latest_chunks: int,
        vector_points: int | None,
    ) -> DocumentIndexHealth:
        expected_vectors = latest_chunks if document.is_active else 0
        missing_vectors = (
            max(expected_vectors - vector_points, 0) if vector_points is not None else None
        )
        extra_vectors = (
            max(vector_points - expected_vectors, 0) if vector_points is not None else None
        )
        return DocumentIndexHealth(
            doc_id=document.doc_id,
            title=document.title,
            is_active=document.is_active,
            chunks_total=chunks_total,
            active_chunks=active_chunks,
            latest_chunks=latest_chunks,
            vector_points=vector_points,
            missing_vectors=missing_vectors,
            extra_vectors=extra_vectors,
            needs_reindex=bool((missing_vectors or 0) > 0 or (extra_vectors or 0) > 0),
        )

    @staticmethod
    def _vector_point_id(chunk_id: str) -> str:
        raw_id = chunk_id.removeprefix("chunk_")
        try:
            return str(UUID(hex=raw_id))
        except ValueError:
            return str(UUID(bytes=raw_id.encode("utf-8")[:16].ljust(16, b"_")))
