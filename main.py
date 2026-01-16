from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import (
    APP_NAME,
    CORS_ALLOW_CREDENTIALS,
    CORS_ALLOW_HEADERS,
    CORS_ALLOW_METHODS,
    CORS_ALLOW_ORIGINS,
)
from app.core.helpers import now_iso
from app.routers.agent_run import router as agent_router
from app.routers.webchat import router as webchat_router
from app.routers.debug import router as debug_router

# Prioritize local package resolution when running via `uvicorn agent.main:app`.
sys.path.insert(0, str(Path(__file__).resolve().parent))


def create_app() -> FastAPI:
    app = FastAPI(title="PazarGlobal Agent Backend")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ALLOW_ORIGINS,
        allow_credentials=CORS_ALLOW_CREDENTIALS,
        allow_methods=CORS_ALLOW_METHODS,
        allow_headers=CORS_ALLOW_HEADERS,
    )

    @app.get("/healthz")
    def healthz() -> dict[str, Any]:  # noqa: F841, reportUnusedFunction
        return {"ok": True, "service": APP_NAME, "time": now_iso()}

    app.include_router(webchat_router)
    app.include_router(agent_router)
    app.include_router(debug_router)

    return app


app = create_app()

