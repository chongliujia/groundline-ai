from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models

from groundline.core.errors import BackendUnavailableError
from groundline.core.schemas import RetrievalHit


@dataclass
class QdrantVectorStore:
    """Qdrant vector store adapter boundary for v0.1."""

    url: str = "http://localhost:6333"
    vector_size: int = 384
    distance: str = "cosine"

    def __post_init__(self) -> None:
        self._client: QdrantClient | None = None

    @property
    def client(self) -> QdrantClient:
        if self._client is None:
            self._client = QdrantClient(url=self.url)
        return self._client

    def ensure_collection(self, collection: str) -> None:
        try:
            if self.client.collection_exists(collection):
                return
            self.client.create_collection(
                collection_name=collection,
                vectors_config=models.VectorParams(
                    size=self.vector_size,
                    distance=self._distance(),
                ),
            )
        except Exception as error:  # pragma: no cover - depends on external Qdrant
            raise BackendUnavailableError(f"Qdrant is unavailable: {error}") from error

    def upsert(
        self,
        collection: str,
        vectors: list[tuple[str, list[float], dict[str, Any]]],
    ) -> None:
        if not vectors:
            return
        self.ensure_collection(collection)
        try:
            self.client.upsert(
                collection_name=collection,
                points=[
                    models.PointStruct(id=point_id, vector=vector, payload=payload)
                    for point_id, vector, payload in vectors
                ],
            )
        except Exception as error:  # pragma: no cover - depends on external Qdrant
            raise BackendUnavailableError(f"Qdrant upsert failed: {error}") from error

    def search(self, collection: str, vector: list[float], top_k: int) -> list[RetrievalHit]:
        try:
            if not self.client.collection_exists(collection):
                return []
            results = self.client.query_points(
                collection_name=collection,
                query=vector,
                limit=top_k,
                with_payload=True,
            ).points
        except Exception as error:  # pragma: no cover - depends on external Qdrant
            raise BackendUnavailableError(f"Qdrant search failed: {error}") from error

        return [
            RetrievalHit(
                chunk_id=str(point.payload.get("chunk_id", point.id)),
                score=float(point.score),
                source="vector",
                rank=rank,
                metadata=dict(point.payload or {}),
            )
            for rank, point in enumerate(results, start=1)
        ]

    def delete_collection(self, collection: str) -> bool:
        try:
            if not self.client.collection_exists(collection):
                return False
            self.client.delete_collection(collection_name=collection)
            return True
        except Exception as error:  # pragma: no cover - depends on external Qdrant
            raise BackendUnavailableError(f"Qdrant collection delete failed: {error}") from error

    def delete_by_doc_id(self, collection: str, doc_id: str) -> int:
        try:
            if not self.client.collection_exists(collection):
                return 0
            selector = self._doc_filter(doc_id)
            count = self._count_existing_collection(collection, selector)
            if count == 0:
                return 0
            self.client.delete(
                collection_name=collection,
                points_selector=selector,
                wait=True,
            )
            return int(count)
        except Exception as error:  # pragma: no cover - depends on external Qdrant
            raise BackendUnavailableError(
                f"Qdrant document vector delete failed: {error}"
            ) from error

    def count_points(self, collection: str, doc_id: str | None = None) -> int:
        try:
            if not self.client.collection_exists(collection):
                return 0
            selector = self._doc_filter(doc_id) if doc_id else None
            return self._count_existing_collection(collection, selector)
        except Exception as error:  # pragma: no cover - depends on external Qdrant
            raise BackendUnavailableError(f"Qdrant vector count failed: {error}") from error

    def _count_existing_collection(
        self,
        collection: str,
        selector: models.Filter | None,
    ) -> int:
        return int(
            self.client.count(
                collection_name=collection,
                count_filter=selector,
                exact=True,
            ).count
        )

    @staticmethod
    def _doc_filter(doc_id: str) -> models.Filter:
        return models.Filter(
            must=[
                models.FieldCondition(
                    key="doc_id",
                    match=models.MatchValue(value=doc_id),
                )
            ]
        )

    def _distance(self) -> models.Distance:
        value = self.distance.lower()
        if value == "dot":
            return models.Distance.DOT
        if value == "euclid":
            return models.Distance.EUCLID
        return models.Distance.COSINE
