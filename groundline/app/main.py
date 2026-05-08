from __future__ import annotations

from fastapi import FastAPI

from groundline.app.routes import collections, eval, providers, query


def create_app() -> FastAPI:
    app = FastAPI(
        title="Groundline",
        description="Retrieval engine for grounded, citation-ready LLM context.",
        version="0.1.0a0",
    )
    app.include_router(collections.router)
    app.include_router(query.router)
    app.include_router(eval.router)
    app.include_router(providers.router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
