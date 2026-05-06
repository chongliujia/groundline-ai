from __future__ import annotations


def recall_at_k(results: list[str], gold: set[str], k: int) -> float:
    if not gold:
        return 0.0
    return len(set(results[:k]) & gold) / len(gold)


def mean_reciprocal_rank(results: list[str], gold: set[str]) -> float:
    for index, result in enumerate(results, start=1):
        if result in gold:
            return 1.0 / index
    return 0.0

