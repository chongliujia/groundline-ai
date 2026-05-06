from __future__ import annotations

import shutil
from pathlib import Path


class LocalObjectStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def put_file(self, source: Path, object_key: str) -> str:
        target = self.root / object_key
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        return str(target)

