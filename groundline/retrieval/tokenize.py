from __future__ import annotations


def tokenize(text: str) -> list[str]:
    """Small tokenizer for the local demo path.

    English-like text is grouped into lowercase words. CJK characters are emitted
    individually so Chinese queries still have a useful BM25 baseline.
    """

    tokens: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            tokens.append("".join(current).lower())
            current.clear()

    for char in text:
        if "\u4e00" <= char <= "\u9fff":
            flush()
            tokens.append(char)
        elif char.isalnum() or char == "_":
            current.append(char)
        else:
            flush()
    flush()
    return tokens

