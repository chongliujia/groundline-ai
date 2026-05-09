# Developer Support Example

This example is a small engineering-style Groundline app for a developer support
assistant. It is meant to be run as a standalone app project, not as a one-off
demo command.

```bash
cd examples/developer-support
groundline app validate
groundline app docs
groundline app run
cp .groundline/artifacts/latest.json .groundline/artifacts/base.json
groundline app run
groundline app compare .groundline/artifacts/base.json .groundline/artifacts/latest.json
```

The default configuration uses local BM25 retrieval and does not require LLM,
embedding, or rerank API keys. To test vector retrieval without external API
keys, copy the root `groundline.example.toml` to this directory, enable the hash
embedding provider, start Qdrant, then run the app again.

The `ci` profile keeps artifacts and collection data separate from local
developer runs:

```bash
groundline app run --profile ci
```
