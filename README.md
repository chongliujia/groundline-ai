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

## Quickstart

Run the local BM25-only demo without external API keys:

```bash
groundline quickstart
```

Run the fuller developer demo flow when you want reusable diagnostics:

```bash
groundline demo --json
```

The demo runs ingest, health, query, answer, eval, reindex, and persisted run
history against the bundled example documents.

For a reusable app-style workflow, initialize and run an app recipe:

```bash
groundline app init
groundline app scaffold my-rag-app --template developer-support
groundline app validate
groundline app plan
groundline app docs
groundline app providers
groundline app run --json
groundline app run --profile dev
groundline app compare .groundline/artifacts/base.json .groundline/artifacts/latest.json
groundline app status
groundline app export .groundline/artifacts/demo-report.json
```

To scaffold a standalone developer demo project:

```bash
groundline app scaffold my-rag-app --template developer-support
cd my-rag-app
groundline app validate
groundline app run
```

`groundline app run` is the engineering entrypoint: it uses the recipe to run an
incremental ingest plus optional query, answer, eval, and reindex steps. It does
not clear the collection unless `reset_collection = true` is set in
`groundline.app.toml`. `groundline app validate` and `groundline app plan` are
side-effect-free checks for developer demos and CI.

Each app run writes a manifest into its artifact with the recipe hash, input
document hashes, provider status, executed steps, and pipeline run ids.
Use `groundline app docs` to compare local source files with indexed document
versions and detect new, changed, or missing sources before running ingest.
Use `groundline app providers` to inspect LLM, embedding, rerank, and Qdrant
readiness before wiring real API keys into the app.
Use profiles in `groundline.app.toml`, such as `[profiles.dev]`, to override
collection, data dir, artifacts, Qdrant URL, or provider config per environment.
Use `groundline app compare` to diff two run artifacts for recipe, document,
provider, step, and eval metric changes.
See `docs/app-artifacts.md` for the artifact contract used by compare, CI,
future Web UI views, and regression reports.

For a more engineering-style reusable app example:

```bash
cd examples/developer-support
groundline app validate
groundline app run
```

The example evalset uses `gold_source_uris`, so it stays stable across runs even
though Groundline generates fresh document ids on ingest.

Provider API configuration lives in one local file:

```bash
cp groundline.example.toml groundline.toml
```

Use `groundline.toml` for LLM, embedding, and rerank provider settings. Put actual
API keys in environment variables referenced by that file.

For an OpenAI-compatible LLM API:

```toml
[llm]
provider = "http"
model = "chat-model"
base_url = "https://provider.example/v1"
endpoint_path = "/chat/completions"
api_key_env = "GROUNDLINE_LLM_API_KEY"
```

By default, embedding is disabled so the local demo runs with BM25 only. To test
the vector path without external API keys, set:

```toml
[embedding]
provider = "hash"
dimension = 384
```

To call an OpenAI-compatible embedding API:

```toml
[embedding]
provider = "http"
model = "embedding-model"
base_url = "https://provider.example/v1"
endpoint_path = "/embeddings"
api_key_env = "GROUNDLINE_EMBEDDING_API_KEY"
dimension = 1536
```

When embedding is enabled, Groundline will try to write/query Qdrant and fall
back to BM25 if Qdrant is unavailable.

Rerank is also disabled by default. For a dependency-free local rerank smoke test:

```toml
[rerank]
provider = "keyword"
```

To call an HTTP rerank API:

```toml
[rerank]
provider = "http"
model = "rerank-model"
base_url = "https://provider.example"
endpoint_path = "/rerank"
api_key_env = "GROUNDLINE_RERANK_API_KEY"
```

The embedding adapter sends `{ "model": ..., "input": [...] }` and reads
`data[].embedding`. The rerank adapter sends `{ "model": ..., "query": ...,
"documents": [...] }` and reads `results[].index` plus `score` or
`relevance_score`.

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

Open the local enterprise console:

```text
http://127.0.0.1:8080/ui
```

The API exposes the same core flow as the CLI:

```text
GET    /health
GET    /ui
POST   /demo
POST   /app/plan
POST   /app/validate
POST   /app/docs
GET    /app/providers
POST   /app/run
GET    /app/status
GET    /app/artifacts/latest
POST   /app/compare
GET    /providers
POST   /collections
GET    /collections
GET    /collections/{collection}/health
GET    /collections/{collection}/pipeline-runs
GET    /collections/{collection}/pipeline-runs/{run_id}
POST   /collections/{collection}/ingest
POST   /collections/{collection}/query
POST   /collections/{collection}/answer
POST   /collections/{collection}/clear
POST   /collections/{collection}/reindex
GET    /collections/{collection}/documents
GET    /collections/{collection}/documents/{doc_id}
GET    /collections/{collection}/documents/{doc_id}/versions
GET    /collections/{collection}/chunks
POST   /collections/{collection}/eval
DELETE /collections/{collection}
DELETE /collections/{collection}/documents/{doc_id}
```

Run retrieval eval:

```bash
groundline eval ./evalset.jsonl --collection demo --top-k 8
```

Eval JSONL rows support `query`, `gold_doc_ids`, `gold_chunk_ids`,
`gold_source_uris`, and `query_type`.
Eval reports include aggregate metrics plus per-query hit/miss diagnostics:
retrieved contexts, matched gold ids, first hit rank, and retrieval trace details.

Inspect local ids for debugging and eval authoring:

```bash
groundline inspect collections
groundline inspect documents --collection demo
groundline inspect chunks --collection demo
```

Most CLI commands support `--json` for scripts and future UI integration:

```bash
groundline ingest ./docs --collection demo --domain finance --metadata '{"department":"finance"}' --json
groundline providers --json
groundline health --collection demo --json
groundline runs --collection demo --json
groundline demo --json
groundline quickstart --json
groundline query "住宿标准" --collection demo --trace --json
groundline answer "住宿标准" --collection demo --trace --json
groundline inspect documents --collection demo --json
groundline inspect document --collection demo --doc-id <doc_id> --json
groundline inspect versions --collection demo --doc-id <doc_id> --json
groundline eval ./evalset.jsonl --collection demo --json
groundline clear collection --collection demo --json
groundline reindex collection --collection demo --json
groundline delete collection demo --json
groundline delete document <doc_id> --collection demo --json
```

Operational commands return a reusable `pipeline` object in JSON/API responses.
It contains a `run_id`, operation status, and ordered step events such as parse,
chunk, vector index, retrieval, rerank, context packing, and reindex. The shape is
stable enough for demos, diagnostics, logs, and the future Web UI to consume.
Pipeline runs are also persisted locally, so `groundline runs --collection demo`
can inspect recent operation history after the original response is gone.

Query supports exact-match filters on chunk/document fields and metadata:

```bash
groundline query "住宿标准" --collection demo --domain finance
groundline query "住宿标准" --collection demo --filters '{"metadata":{"department":"finance"}}'
groundline query "住宿标准" --collection demo --context-window 1 --max-context-chars 8000
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

Context packing is off by default. Set `context_window` / `--context-window` to
include adjacent chunks around each hit, and `max_context_chars` /
`--max-context-chars` to cap the total packed context size.

Repeated ingest skips unchanged files by `source_uri + content_hash`. Changed files
reuse the existing `doc_id`, create a new version, and deactivate old chunks.
When embedding is enabled, Groundline also removes the previous document vectors
from Qdrant before indexing the new version.

Check collection health before demos or after backend maintenance:

```bash
groundline health --collection demo
```

Health diagnostics report metadata counts, expected vector points, actual Qdrant
points, and whether the collection needs `reindex`.

Delete a document with a tombstone:

```bash
groundline delete document <doc_id> --collection demo
```

Deletion is logical: documents and chunks are marked inactive and hidden from query
and default inspect output. Use `--include-inactive` with `inspect` to audit them.
When embedding is enabled, document delete also removes that document's Qdrant
vectors by `doc_id`.
