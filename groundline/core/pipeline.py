from __future__ import annotations

from time import monotonic
from typing import Any, Literal

from groundline.core.ids import new_id
from groundline.core.schemas import PipelineEvent, PipelineRun, utc_now

PipelineOperation = Literal[
    "ingest",
    "query",
    "answer",
    "reindex",
    "health",
    "clear",
    "delete",
]
PipelineStatus = Literal["started", "completed", "skipped", "failed"]
RunStatus = Literal["started", "completed", "failed"]


class PipelineRecorder:
    def __init__(
        self,
        operation: PipelineOperation,
        collection: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.operation = operation
        self.collection = collection
        self.run_id = new_id("run")
        self.started_at = utc_now()
        self._started_monotonic = monotonic()
        self._events: list[PipelineEvent] = []
        self.metadata = metadata or {}
        self.event("operation", status="started", metadata=self.metadata)

    @property
    def events(self) -> list[PipelineEvent]:
        return list(self._events)

    def event(
        self,
        stage: str,
        status: PipelineStatus = "completed",
        message: str | None = None,
        doc_id: str | None = None,
        source_uri: str | None = None,
        duration_ms: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PipelineEvent:
        event = PipelineEvent(
            event_id=new_id("event"),
            stage=stage,
            status=status,
            message=message,
            doc_id=doc_id,
            source_uri=source_uri,
            duration_ms=duration_ms,
            metadata=metadata or {},
        )
        self._events.append(event)
        return event

    def complete(
        self,
        status: RunStatus = "completed",
        metadata: dict[str, Any] | None = None,
    ) -> PipelineRun:
        if metadata:
            self.metadata = {**self.metadata, **metadata}
        finished_at = utc_now()
        return PipelineRun(
            run_id=self.run_id,
            operation=self.operation,
            collection=self.collection,
            status=status,
            events=self.events,
            duration_ms=round((monotonic() - self._started_monotonic) * 1000, 3),
            metadata=self.metadata,
            started_at=self.started_at,
            finished_at=finished_at,
        )
