from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.runtime import HyperAmmRuntime
from app.api import health, markets, strategy, orders, risk, websocket, positions

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.runtime = HyperAmmRuntime(settings)
    await app.state.runtime.start_services()
    yield
    await app.state.runtime.stop_services()


app = FastAPI(title="HyperAMM API", version="0.5.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
for router in (health.router, markets.router, strategy.router, orders.router, risk.router, positions.router):
    app.include_router(router, prefix=settings.api_prefix)
app.include_router(websocket.router)


@app.get("/")
async def root():
    return {"name": "HyperAMM", "phase": "1-5", "docs": "/docs"}
