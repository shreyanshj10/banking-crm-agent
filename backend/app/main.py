"""FastAPI application factory.

Lifespan:
- startup: configure logging, build the agent graph ONCE (so its in-memory
  MemorySaver persists across requests for the life of the server).
- shutdown: dispose the async DB engine.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent.graph import build_graph
from app.api.routes.chat import router as chat_router
from app.config import settings
from app.core.logging import configure_logging
from app.db.connection import engine

logger = logging.getLogger("banking_crm.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    app.state.graph = build_graph()  # built once; shared across requests
    logger.info("startup complete — agent graph ready")
    yield
    await engine.dispose()
    logger.info("shutdown — DB engine disposed")


def create_app() -> FastAPI:
    app = FastAPI(title="Banking CRM Agent", lifespan=lifespan)

    # CORS scoped to the dev frontend origin so the browser can call /chat.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    app.include_router(chat_router)
    return app


app = create_app()
