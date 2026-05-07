# Groundline

Groundline is an open-source retrieval engine for grounded, citation-ready LLM context.

It turns local documents into structured blocks, retrieval chunks, hybrid indexes, and
traceable context for LLM applications.

## Current Focus

v0.1 targets developers and open-source demos:

```text
local docs
  -> Block AST
  -> heading-aware chunks
  -> Qdrant + BM25
  -> RRF
  -> citation-ready context
```

PDF parsing is intentionally out of scope for v0.1, but the source type, page/bbox fields,
asset schemas, and parser adapter slot are reserved.

## Development

```bash
source /Users/jiachongliu/anaconda3/etc/profile.d/conda.sh
conda activate rag

python -m pip install -e ".[dev]"
pytest
ruff check groundline tests
```

Provider API configuration lives in one local file:

```bash
cp groundline.example.toml groundline.toml
```

Use `groundline.toml` for LLM, embedding, and rerank provider settings. Put actual
API keys in environment variables referenced by that file.

By default, embedding is disabled so the local demo runs with BM25 only. To test
the vector path without external API keys, set:

```toml
[embedding]
provider = "hash"
dimension = 384
```

When embedding is enabled, Groundline will try to write/query Qdrant and fall
back to BM25 if Qdrant is unavailable.

Rerank is also disabled by default. For a dependency-free local rerank smoke test:

```toml
[rerank]
provider = "keyword"
```

Start local Qdrant:

```bash
docker compose up qdrant
```

Run the optional Qdrant integration test:

```bash
docker compose up -d qdrant
GROUNDLINE_TEST_QDRANT=1 pytest tests/integration/test_qdrant.py
```

This test uses the dependency-free `hash` embedder and verifies that vectors are
written to Qdrant and returned by vector search. It is skipped during normal
`pytest` runs.

Start the API:

```bash
groundline serve --host 127.0.0.1 --port 8080
```

The API exposes the same core flow as the CLI:

```text
GET    /health
POST   /collections
GET    /collections
POST   /collections/{collection}/ingest
POST   /collections/{collection}/query
GET    /collections/{collection}/documents
GET    /collections/{collection}/documents/{doc_id}
GET    /collections/{collection}/documents/{doc_id}/versions
GET    /collections/{collection}/chunks
POST   /collections/{collection}/eval
DELETE /collections/{collection}/documents/{doc_id}
```

Run retrieval eval:

```bash
groundline eval ./evalset.jsonl --collection demo --top-k 8
```

Eval JSONL rows support `query`, `gold_doc_ids`, `gold_chunk_ids`, and `query_type`.

Inspect local ids for debugging and eval authoring:

```bash
groundline inspect collections
groundline inspect documents --collection demo
groundline inspect chunks --collection demo
```

Most CLI commands support `--json` for scripts and future UI integration:

```bash
groundline ingest ./docs --collection demo --domain finance --metadata '{"department":"finance"}' --json
groundline query "住宿标准" --collection demo --trace --json
groundline inspect documents --collection demo --json
groundline inspect document --collection demo --doc-id <doc_id> --json
groundline inspect versions --collection demo --doc-id <doc_id> --json
groundline eval ./evalset.jsonl --collection demo --json
groundline delete document <doc_id> --collection demo --json
```

Query supports exact-match filters on chunk/document fields and metadata:

```bash
groundline query "住宿标准" --collection demo --domain finance
groundline query "住宿标准" --collection demo --filters '{"metadata":{"department":"finance"}}'
```

The API uses the same filter object:

```json
{
  "query": "住宿标准",
  "filters": {
    "domain": "finance",
    "metadata": {
      "department": "finance"
    }
  }
}
```

Use `--trace` to inspect retrieval internals. The trace includes routing inputs,
BM25 candidates, raw and filtered vector candidates, RRF fusion candidates,
rerank candidates, and the final context list.

Repeated ingest skips unchanged files by `source_uri + content_hash`. Changed files
reuse the existing `doc_id`, create a new version, and deactivate old chunks.

Delete a document with a tombstone:

```bash
groundline delete document <doc_id> --collection demo
```

Deletion is logical: documents and chunks are marked inactive and hidden from query
and default inspect output. Use `--include-inactive` with `inspect` to audit them.
