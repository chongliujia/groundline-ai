from __future__ import annotations

import sqlite3
from pathlib import Path

from groundline.core.schemas import Chunk, Document, DocumentVersion, utc_now


class SQLiteMetadataStore:
    """Minimal SQLite persistence shell for the first implementation slice."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS collections (
                    collection_name TEXT PRIMARY KEY
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    collection_name TEXT NOT NULL,
                    doc_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (collection_name, doc_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS document_versions (
                    collection_name TEXT NOT NULL,
                    doc_id TEXT NOT NULL,
                    version_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (collection_name, doc_id, version_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chunks (
                    collection_name TEXT NOT NULL,
                    chunk_id TEXT NOT NULL,
                    doc_id TEXT NOT NULL,
                    version_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (collection_name, chunk_id)
                )
                """
            )

    def create_collection(self, collection: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO collections (collection_name) VALUES (?)",
                (collection,),
            )

    def list_collections(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT collection_name FROM collections ORDER BY collection_name"
            ).fetchall()
        return [row[0] for row in rows]

    def put_document(self, collection: str, document: Document) -> None:
        self.create_collection(collection)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO documents (collection_name, doc_id, payload)
                VALUES (?, ?, ?)
                """,
                (collection, document.doc_id, document.model_dump_json()),
            )

    def list_documents(self, collection: str) -> list[Document]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload FROM documents
                WHERE collection_name = ?
                ORDER BY doc_id
                """,
                (collection,),
            ).fetchall()
        return [Document.model_validate_json(row[0]) for row in rows]

    def get_document(self, collection: str, doc_id: str) -> Document | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload FROM documents
                WHERE collection_name = ? AND doc_id = ?
                """,
                (collection, doc_id),
            ).fetchone()
        return Document.model_validate_json(row[0]) if row else None

    def get_document_by_source_uri(self, collection: str, source_uri: str) -> Document | None:
        for document in self.list_documents(collection):
            if document.source_uri == source_uri:
                return document
        return None

    def put_version(self, collection: str, version: DocumentVersion) -> None:
        self.create_collection(collection)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO document_versions
                (collection_name, doc_id, version_id, payload)
                VALUES (?, ?, ?, ?)
                """,
                (collection, version.doc_id, version.version_id, version.model_dump_json()),
            )

    def get_version(
        self,
        collection: str,
        doc_id: str,
        version_id: str,
    ) -> DocumentVersion | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload FROM document_versions
                WHERE collection_name = ? AND doc_id = ? AND version_id = ?
                """,
                (collection, doc_id, version_id),
            ).fetchone()
        return DocumentVersion.model_validate_json(row[0]) if row else None

    def list_versions(self, collection: str, doc_id: str) -> list[DocumentVersion]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload FROM document_versions
                WHERE collection_name = ? AND doc_id = ?
                """,
                (collection, doc_id),
            ).fetchall()
        return sorted(
            [DocumentVersion.model_validate_json(row[0]) for row in rows],
            key=lambda version: version.created_at,
        )

    def deactivate_versions_for_document(
        self,
        collection: str,
        doc_id: str,
        superseded_by: str | None = None,
    ) -> None:
        versions = [
            version.model_copy(
                update={
                    "is_latest": False,
                    "superseded_by": superseded_by,
                    "updated_at": utc_now(),
                },
            )
            for version in self.list_versions(collection, doc_id)
        ]
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO document_versions
                (collection_name, doc_id, version_id, payload)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        collection,
                        version.doc_id,
                        version.version_id,
                        version.model_dump_json(),
                    )
                    for version in versions
                ],
            )

    def tombstone_versions_for_document(self, collection: str, doc_id: str) -> None:
        versions = [
            version.model_copy(
                update={"is_latest": False, "is_active": False, "updated_at": utc_now()},
            )
            for version in self.list_versions(collection, doc_id)
        ]
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO document_versions
                (collection_name, doc_id, version_id, payload)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        collection,
                        version.doc_id,
                        version.version_id,
                        version.model_dump_json(),
                    )
                    for version in versions
                ],
            )

    def put_chunks(self, collection: str, chunks: list[Chunk]) -> None:
        self.create_collection(collection)
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO chunks
                (collection_name, chunk_id, doc_id, version_id, payload)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        collection,
                        chunk.chunk_id,
                        chunk.doc_id,
                        chunk.version_id,
                        chunk.model_dump_json(),
                    )
                    for chunk in chunks
                ],
            )

    def list_chunks(self, collection: str) -> list[Chunk]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload FROM chunks
                WHERE collection_name = ?
                ORDER BY chunk_id
                """,
                (collection,),
            ).fetchall()
        return [Chunk.model_validate_json(row[0]) for row in rows]

    def deactivate_chunks_for_document(self, collection: str, doc_id: str) -> None:
        chunks = [
            chunk.model_copy(
                update={"is_latest": False, "is_active": False, "updated_at": utc_now()},
            )
            for chunk in self.list_chunks(collection)
            if chunk.doc_id == doc_id
        ]
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO chunks
                (collection_name, chunk_id, doc_id, version_id, payload)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        collection,
                        chunk.chunk_id,
                        chunk.doc_id,
                        chunk.version_id,
                        chunk.model_dump_json(),
                    )
                    for chunk in chunks
                ],
            )

    def tombstone_document(self, collection: str, doc_id: str) -> int:
        document = self.get_document(collection, doc_id)
        if document is None:
            return 0

        deleted_at = utc_now()
        tombstoned = document.model_copy(
            update={
                "is_active": False,
                "deleted_at": deleted_at,
                "updated_at": deleted_at,
            }
        )
        self.put_document(collection, tombstoned)
        self.tombstone_versions_for_document(collection, doc_id)
        self.deactivate_chunks_for_document(collection, doc_id)
        return len([chunk for chunk in self.list_chunks(collection) if chunk.doc_id == doc_id])

    def get_chunk(self, collection: str, chunk_id: str) -> Chunk | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload FROM chunks
                WHERE collection_name = ? AND chunk_id = ?
                """,
                (collection, chunk_id),
            ).fetchone()
        return Chunk.model_validate_json(row[0]) if row else None
