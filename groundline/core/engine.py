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
from groundline.core.schemas import (
    AnswerResponse,
    Chunk,
    CollectionOperationResponse,
    DeleteResponse,
    Document,
    DocumentDetail,
    DocumentVersion,
    GroundedContext,
    IngestedDocument,
    IngestResponse,
    QueryResponse,
    RetrievalHit,
    SkippedSource,
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
        if not self.metadata.collection_exists(collection):
            return CollectionOperationResponse(
                collection=collection,
                operation="clear",
                ok=False,
                reason="collection not found",
            )
        documents, versions, chunks = self.metadata.clear_collection(collection)
        vector_deleted, vector_error = self._try_delete_vector_collection(collection)
        return CollectionOperationResponse(
            collection=collection,
            operation="clear",
            ok=True,
            documents_removed=documents,
            versions_removed=versions,
            chunks_removed=chunks,
            vector_collection_deleted=vector_deleted,
            vector_error=vector_error,
        )

    def delete_collection(self, collection: str) -> CollectionOperationResponse:
        if not self.metadata.collection_exists(collection):
            return CollectionOperationResponse(
                collection=collection,
                operation="delete",
                ok=False,
                reason="collection not found",
            )
        documents, versions, chunks = self.metadata.delete_collection(collection)
        vector_deleted, vector_error = self._try_delete_vector_collection(collection)
        return CollectionOperationResponse(
            collection=collection,
            operation="delete",
            ok=True,
            documents_removed=documents,
            versions_removed=versions,
            chunks_removed=chunks,
            vector_collection_deleted=vector_deleted,
            vector_error=vector_error,
        )

    def delete_document(self, collection: str, doc_id: str) -> DeleteResponse:
        document = self.metadata.get_document(collection, doc_id)
        if document is None:
            return DeleteResponse(
                collection=collection,
                doc_id=doc_id,
                deleted=False,
                reason="document not found",
            )
        if not document.is_active:
            return DeleteResponse(
                collection=collection,
                doc_id=doc_id,
                deleted=False,
                reason="document already inactive",
            )
        chunks_deactivated = self.metadata.tombstone_document(collection, doc_id)
        vector_points_deleted, vector_error = self._try_delete_document_vectors(
            collection,
            doc_id,
        )
        return DeleteResponse(
            collection=collection,
            doc_id=doc_id,
            deleted=True,
            chunks_deactivated=chunks_deactivated,
            vector_points_deleted=vector_points_deleted,
            vector_error=vector_error,
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
        self.metadata.create_collection(collection)
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
                )
                if isinstance(ingest_result, IngestedDocument):
                    documents.append(ingest_result)
                else:
                    skipped.append(ingest_result)
            except UnsupportedSourceTypeError as error:
                skipped.append(SkippedSource(source_uri=str(source), reason=str(error)))

        if path.is_file() and not documents and not skipped:
            raise GroundlineError(f"No supported document found at {path}")

        return IngestResponse(collection=collection, documents=documents, skipped=skipped)

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
    ) -> IngestedDocument | SkippedSource:
        source_uri = str(source)
        content_hash = hash_file(source)
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

        if existing_document:
            self._try_delete_document_vectors(collection, doc_id)
            self.metadata.deactivate_versions_for_document(
                collection,
                doc_id,
                superseded_by=version_id,
            )
            self.metadata.deactivate_chunks_for_document(collection, doc_id)
        self.metadata.put_document(collection, document)
        self.metadata.put_version(collection, version)
        self.metadata.put_chunks(collection, chunks)
        self._try_index_vectors(collection, chunks)

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
        chunk_by_id = {chunk.chunk_id: chunk for chunk in chunks}
        search = InMemoryBM25Store()
        search.index(collection, chunks)
        bm25_hits = search.search(collection, query, top_k=max(top_k, 20))
        raw_vector_hits, vector_error = self._try_vector_search(
            collection,
            query,
            top_k=max(top_k, 20),
        )
        vector_hits = [hit for hit in raw_vector_hits if hit.chunk_id in chunk_by_id]
        hits = reciprocal_rank_fusion([bm25_hits, vector_hits], top_n=top_k)
        doc_by_id = {
            document.doc_id: document for document in self.metadata.list_documents(collection)
        }
        reranked_chunks, rerank_error = self._try_rerank(
            query,
            [chunk_by_id[hit.chunk_id] for hit in hits if hit.chunk_id in chunk_by_id],
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

        return QueryResponse(query=query, contexts=contexts, trace=trace)

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
        try:
            llm = build_llm(self.providers.llm)
            if llm is None:
                return AnswerResponse(
                    query=query,
                    contexts=query_response.contexts,
                    trace=query_response.trace,
                    error="llm disabled",
                )
            messages = build_answer_messages(
                query=query,
                contexts=query_response.contexts,
                system_prompt=system_prompt,
            )
            return AnswerResponse(
                query=query,
                answer=llm.generate(messages),
                contexts=query_response.contexts,
                trace=query_response.trace,
            )
        except (BackendUnavailableError, ProviderConfigurationError, ImportError) as error:
            return AnswerResponse(
                query=query,
                contexts=query_response.contexts,
                trace=query_response.trace,
                error=str(error),
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

    @staticmethod
    def _vector_point_id(chunk_id: str) -> str:
        raw_id = chunk_id.removeprefix("chunk_")
        try:
            return str(UUID(hex=raw_id))
        except ValueError:
            return str(UUID(bytes=raw_id.encode("utf-8")[:16].ljust(16, b"_")))
