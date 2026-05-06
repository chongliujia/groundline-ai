from pathlib import Path

from groundline.ingestion.chunker import HeadingAwareChunker
from groundline.ingestion.parser import ParserRegistry


def test_markdown_parser_and_chunker(tmp_path: Path) -> None:
    source = tmp_path / "policy.md"
    source.write_text("# Policy\n\n## Travel\n\nReimbursement rules apply.", encoding="utf-8")

    blocks = ParserRegistry().parse(source, doc_id="doc_1", version_id="v1")
    chunks = HeadingAwareChunker().chunk(blocks, doc_id="doc_1", version_id="v1")

    assert [block.block_type for block in blocks] == ["heading", "heading", "paragraph"]
    assert chunks
    assert chunks[-1].heading_path == ["Policy", "Travel"]

