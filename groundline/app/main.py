from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from groundline.app.routes import app_runtime, collections, demo, eval, providers, query

STATIC_DIR = Path(__file__).parent / "static" / "console"


def create_app() -> FastAPI:
    app = FastAPI(
        title="Groundline",
        description="Retrieval engine for grounded, citation-ready LLM context.",
        version="0.1.0a0",
    )
    app.include_router(collections.router)
    app.include_router(app_runtime.router)
    app.include_router(query.router)
    app.include_router(eval.router)
    app.include_router(demo.router)
    app.include_router(providers.router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    if STATIC_DIR.exists():
        app.mount(
            "/ui/assets",
            StaticFiles(directory=STATIC_DIR),
            name="groundline-ui-assets",
        )

        @app.get("/ui", include_in_schema=False)
        def console_index() -> FileResponse:
            return FileResponse(STATIC_DIR / "index.html")

        @app.get("/ui/{_:path}", include_in_schema=False)
        def console_fallback(_: str) -> FileResponse:
            return FileResponse(STATIC_DIR / "index.html")

    return app


app = create_app()
