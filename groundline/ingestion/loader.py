from __future__ import annotations

from pathlib import Path

SUPPORTED_LOCAL_EXTENSIONS = {".txt", ".md", ".markdown", ".html", ".htm"}
RESERVED_EXTENSIONS = {".pdf"}


def infer_source_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown"}:
        return "md"
    if suffix in {".html", ".htm"}:
        return "html"
    if suffix == ".txt":
        return "txt"
    if suffix == ".pdf":
        return "pdf"
    return suffix.lstrip(".") or "unknown"


def iter_local_documents(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and (path.suffix.lower() in SUPPORTED_LOCAL_EXTENSIONS | RESERVED_EXTENSIONS)
    )

