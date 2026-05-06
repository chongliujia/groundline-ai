from groundline.adapters.rerank.factory import build_reranker
from groundline.core.provider_config import APIProviderConfig
from groundline.core.schemas import Chunk


def make_chunk(chunk_id: str, text: str) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        doc_id="doc_1",
        version_id="v1",
        tenant_id="default",
        content_markdown=text,
        content_text=text,
        text_for_embedding=text,
        content_hash=chunk_id,
    )


def test_rerank_factory_returns_none_when_disabled() -> None:
    assert build_reranker(APIProviderConfig(provider="none")) is None


def test_keyword_reranker_orders_by_overlap() -> None:
    reranker = build_reranker(APIProviderConfig(provider="keyword"))

    assert reranker is not None
    ranked = reranker.rerank(
        "住宿标准",
        [
            make_chunk("chunk_1", "Travel reimbursement"),
            make_chunk("chunk_2", "差旅住宿标准是一线城市 800 元每晚"),
        ],
    )

    assert ranked[0][0].chunk_id == "chunk_2"
    assert ranked[0][1] > ranked[1][1]

