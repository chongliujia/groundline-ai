from __future__ import annotations

from groundline.core.schemas import GroundedContext

DEFAULT_ANSWER_SYSTEM_PROMPT = (
    "You answer using only the provided Groundline contexts. "
    "If the contexts are insufficient, say so. Cite sources with bracketed numbers."
)


def build_answer_messages(
    query: str,
    contexts: list[GroundedContext],
    system_prompt: str | None = None,
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": system_prompt or DEFAULT_ANSWER_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": _build_user_prompt(query, contexts),
        },
    ]


def _build_user_prompt(query: str, contexts: list[GroundedContext]) -> str:
    rendered_contexts = "\n\n".join(
        _render_context(index, context) for index, context in enumerate(contexts, start=1)
    )
    return (
        f"Question:\n{query}\n\n"
        "Contexts:\n"
        f"{rendered_contexts if rendered_contexts else '(no contexts retrieved)'}\n\n"
        "Answer with citations like [1]."
    )


def _render_context(index: int, context: GroundedContext) -> str:
    heading = context.section or context.title or context.doc_id
    return (
        f"[{index}] {heading}\n"
        f"doc_id: {context.doc_id}\n"
        f"version_id: {context.version_id}\n"
        f"chunk_id: {context.chunk_id}\n"
        f"source_uri: {context.source_uri or ''}\n"
        f"content:\n{context.content_markdown}"
    )
