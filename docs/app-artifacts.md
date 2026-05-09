# App Artifact Contract

Groundline app artifacts are the stable boundary between a local RAG app run,
CI checks, future Web UI views, and regression comparisons.

Every `groundline app run` writes two JSON files:

```text
.groundline/artifacts/latest.json
.groundline/artifacts/runs/<timestamp>-<collection>.json
```

Both files contain the same shape. `latest.json` is for local iteration and the
timestamped file is for audit history.

## Top-Level Shape

```json
{
  "recipe": {},
  "run": {}
}
```

`recipe` is the resolved `AppRecipe` used for the run. It is included so a saved
artifact can be inspected without reading the working tree.

`run` is the execution report. It includes ingest, health, optional query,
optional answer, optional eval, optional reindex, recent pipeline runs, and the
manifest.

## Manifest

The manifest is the stable comparison surface:

```json
{
  "manifest_version": "app-manifest.v0.1",
  "profile": "default",
  "recipe_hash": "...",
  "collection": "developer_support",
  "data_dir": ".groundline",
  "provider_config_path": "groundline.toml",
  "qdrant_url": "http://localhost:6333",
  "docs_path": "docs",
  "evalset": "evalset.jsonl",
  "query_text": "How should a developer rotate a leaked API key?",
  "started_at": "2026-05-10T00:00:00Z",
  "finished_at": "2026-05-10T00:00:01Z",
  "duration_ms": 1000.0,
  "sources": [],
  "providers": {},
  "steps": [],
  "run_ids": []
}
```

Stable fields for automation:

- `manifest_version`: contract version for app artifacts.
- `profile`: selected app profile, such as `default`, `dev`, or `ci`.
- `recipe_hash`: deterministic hash of the resolved recipe.
- `collection`, `data_dir`, `docs_path`, `evalset`, `query_text`: run inputs.
- `provider_config_path`, `qdrant_url`: provider/runtime boundary.
- `sources`: local source snapshots with `path`, `source_type`,
  `content_hash`, and `bytes`.
- `providers`: LLM, embedding, rerank, and vector readiness snapshot.
- `steps`: executed step summaries with status and pipeline run ids.
- `run_ids`: ordered pipeline run ids created during the app run.

## Source Snapshots

`sources` records the local files observed under `docs_path` before ingest. v0.1
supports local Markdown and text-style documents. PDF parsing is intentionally
out of scope, but the source type slot remains reserved for future parser
adapters.

```json
{
  "path": "docs/api-auth.md",
  "source_type": "markdown",
  "content_hash": "...",
  "bytes": 1234
}
```

Use this surface to detect whether a run changed because documents changed, not
because retrieval behavior changed.

## Provider Snapshot

`providers` records which provider implementations were configured at run time.
It is safe to persist because API key values are never written into artifacts.
Only the environment variable name and whether it was present are recorded.

This lets CI compare runs across local BM25, hash embeddings, Qdrant-backed
vector search, HTTP embeddings, HTTP LLMs, or HTTP rerankers.

## Eval Metrics

When `run_eval = true`, the artifact includes:

```json
{
  "run": {
    "eval": {
      "metrics": {
        "queries": 2,
        "recall_at_k": 1.0,
        "mrr": 0.75
      }
    }
  }
}
```

These metrics are consumed by `groundline app compare` and are intended for
regression gates.

## Regression Compare

Use two saved artifacts as inputs:

```bash
groundline app compare .groundline/artifacts/base.json .groundline/artifacts/latest.json
groundline app compare .groundline/artifacts/base.json .groundline/artifacts/latest.json --json
```

The API exposes the same contract:

```http
POST /app/compare
```

```json
{
  "base_path": ".groundline/artifacts/base.json",
  "target_path": ".groundline/artifacts/latest.json"
}
```

The compare report separates:

- recipe changes
- source document changes
- provider configuration changes
- executed step changes
- eval metric changes

This makes it possible to distinguish expected content updates from retrieval
quality regressions.

## Compatibility Rules

For `app-manifest.v0.1`:

- Existing fields listed above should remain backward compatible.
- New fields may be added.
- Automation should ignore unknown fields.
- Breaking changes require a new `manifest_version`.
- Paths are stored exactly as the app recipe/runtime resolved them.
