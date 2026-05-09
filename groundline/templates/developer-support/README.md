# Developer Support App

This project is a generated Groundline app for a developer support assistant.
It is intended as a reusable engineering starting point: local documents,
an evalset, environment profiles, and app run artifacts are all wired together.

```bash
groundline app validate
groundline app docs
groundline app run
```

After the first run, save a baseline artifact before testing changes:

```bash
cp .groundline/artifacts/latest.json .groundline/artifacts/base.json
groundline app run
groundline app compare .groundline/artifacts/base.json .groundline/artifacts/latest.json
```

The default configuration uses local BM25 retrieval and does not require LLM,
embedding, or rerank API keys. To test vector retrieval without external API
keys, copy `groundline.example.toml` into this project, enable the hash
embedding provider, start Qdrant, then run:

```bash
groundline app run --profile vector-smoke
```

