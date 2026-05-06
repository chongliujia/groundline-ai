from __future__ import annotations

import json
from pathlib import Path

from groundline.core.schemas import EvalItem


def load_eval_dataset(path: Path) -> list[EvalItem]:
    items: list[EvalItem] = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid JSONL at line {line_number}: {error}") from error
            items.append(EvalItem.model_validate(payload))
    return items

