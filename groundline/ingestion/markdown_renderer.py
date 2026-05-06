from __future__ import annotations

from groundline.core.schemas import Block


def render_markdown(blocks: list[Block]) -> str:
    return "\n\n".join((block.markdown or block.text or "").strip() for block in blocks).strip()

