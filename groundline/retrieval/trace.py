from __future__ import annotations

from typing import Any


def empty_trace() -> dict[str, Any]:
    return {
        "routing": {},
        "retrieval": {},
        "fusion": {},
        "rerank": {"enabled": False},
        "context": {},
    }

