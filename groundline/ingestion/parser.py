from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Protocol

from groundline.core.errors import UnsupportedSourceTypeError
from groundline.core.ids import new_id
from groundline.core.schemas import Block
from groundline.ingestion.loader import infer_source_type

PARSER_VERSION = "parser.v0.1"


class Parser(Protocol):
    source_types: set[str]

    def parse(self, path: Path, doc_id: str, version_id: str) -> list[Block]:
        ...


class PlainTextParser:
    source_types = {"txt"}

    def parse(self, path: Path, doc_id: str, version_id: str) -> list[Block]:
        text = path.read_text(encoding="utf-8")
        return [
            Block(
                block_id=new_id("block"),
                doc_id=doc_id,
                version_id=version_id,
                block_type="paragraph",
                text=text.strip(),
                markdown=text.strip(),
            )
        ]


class MarkdownParser:
    source_types = {"md", "markdown"}
    heading_pattern = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

    def parse(self, path: Path, doc_id: str, version_id: str) -> list[Block]:
        blocks: list[Block] = []
        heading_stack: list[str] = []
        paragraph: list[str] = []

        def flush_paragraph() -> None:
            if not paragraph:
                return
            text = "\n".join(paragraph).strip()
            blocks.append(
                Block(
                    block_id=new_id("block"),
                    doc_id=doc_id,
                    version_id=version_id,
                    block_type="paragraph",
                    text=text,
                    markdown=text,
                    heading_path=list(heading_stack),
                )
            )
            paragraph.clear()

        for line in path.read_text(encoding="utf-8").splitlines():
            match = self.heading_pattern.match(line)
            if match:
                flush_paragraph()
                level = len(match.group(1))
                title = match.group(2).strip()
                heading_stack = heading_stack[: level - 1] + [title]
                blocks.append(
                    Block(
                        block_id=new_id("block"),
                        doc_id=doc_id,
                        version_id=version_id,
                        block_type="heading",
                        text=title,
                        markdown=line.strip(),
                        heading_level=level,
                        heading_path=list(heading_stack),
                    )
                )
            elif line.strip():
                paragraph.append(line)
            else:
                flush_paragraph()
        flush_paragraph()
        return blocks


class _TextExtractingHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = data.strip()
        if value:
            self.parts.append(value)


class HTMLParserAdapter:
    source_types = {"html", "htm"}

    def parse(self, path: Path, doc_id: str, version_id: str) -> list[Block]:
        parser = _TextExtractingHTMLParser()
        parser.feed(path.read_text(encoding="utf-8"))
        text = "\n".join(parser.parts).strip()
        return [
            Block(
                block_id=new_id("block"),
                doc_id=doc_id,
                version_id=version_id,
                block_type="paragraph",
                text=text,
                markdown=text,
            )
        ]


class ReservedPDFParser:
    source_types = {"pdf"}

    def parse(self, path: Path, doc_id: str, version_id: str) -> list[Block]:
        raise UnsupportedSourceTypeError(
            "PDF parsing is reserved for a later release; v0.1 only records the adapter slot."
        )


class ParserRegistry:
    def __init__(self, parsers: list[Parser] | None = None) -> None:
        self._parsers: dict[str, Parser] = {}
        for parser in parsers or [
            PlainTextParser(),
            MarkdownParser(),
            HTMLParserAdapter(),
            ReservedPDFParser(),
        ]:
            self.register(parser)

    def register(self, parser: Parser) -> None:
        for source_type in parser.source_types:
            self._parsers[source_type] = parser

    def parse(self, path: Path, doc_id: str, version_id: str) -> list[Block]:
        source_type = infer_source_type(path)
        parser = self._parsers.get(source_type)
        if parser is None:
            raise UnsupportedSourceTypeError(f"No parser registered for source type: {source_type}")
        return parser.parse(path, doc_id, version_id)

