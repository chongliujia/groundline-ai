from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ObjectStore(Protocol):
    def put_file(self, source: Path, object_key: str) -> str:
        ...

