from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse
from app.deployment import LocalOnlyBoundary, validate_local_deployment
from app.config import get_settings
from app.runtime import HyperAmmRuntime
from app.simulation.executor import SimulationExecutor
from app.market_data.hyperliquid_metadata import HyperliquidMetadataCatalog
from app.market_data.live_observations import LiveMarketObservationService
from app.api.live_markets import router as live_markets_router
from app.market_data.models import MarketDataMode
from app.strategy.models import ExecutionMode
from app.api.research_markets import router as research_markets_router
from app.api.research_vault import router as research_vault_router, ResearchBodyLimit
from app.infrastructure.redis import RedisInfrastructure
from app.infrastructure.terminal_transport import RedisTerminalTransport
from app.infrastructure.research import CoordinatedSimulationExecutor
from app.api import accounting, agents, health, markets, simulation, strategy, orders, risk, websocket, positions, terminal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_local_deployment()
    app.state.runtime = HyperAmmRuntime(settings)
    app.state.simulation_executor = SimulationExecutor()
    app.state.live_market_observer = LiveMarketObservationService(settings)
    app.state.research_market_catalog = HyperliquidMetadataCatalog(
        allow_demo=settings.market_data_mode == MarketDataMode.DEMO and settings.execution_mode == ExecutionMode.PAPER)
    app.state.terminal_relay = None
    app.state.redis_infrastructure = None
    infrastructure = None
    try:
        if settings.redis_enabled:
            infrastructure = RedisInfrastructure(settings)
            app.state.redis_infrastructure = infrastructure
            await infrastructure.start()
            identity = lambda: (app.state.runtime.terminal_service.process_id,
                                app.state.runtime.terminal_service.session_id)
            app.state.terminal_relay = RedisTerminalTransport(infrastructure, identity)
            app.state.runtime.terminal_distribution = app.state.terminal_relay
            await app.state.terminal_relay.start()
            if settings.redis_research_enabled:
                app.state.simulation_executor = CoordinatedSimulationExecutor(
                    app.state.simulation_executor, infrastructure, identity)
        await app.state.runtime.start_services()
        yield
    finally:
        try:
            await app.state.simulation_executor.shutdown()
        finally:
            try:
                try:
                    await app.state.live_market_observer.close()
                finally:
                    await app.state.research_market_catalog.close()
            finally:
                try:
                    await app.state.runtime.stop_services()
                finally:
                    try:
                        if app.state.terminal_relay is not None:
                            await app.state.terminal_relay.close()
                    finally:
                        if infrastructure is not None:
                            await infrastructure.close()


app = FastAPI(title="HyperAMM API", version="0.12.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.add_middleware(LocalOnlyBoundary)
app.add_middleware(ResearchBodyLimit)


@app.exception_handler(RequestValidationError)
async def research_validation_errors(request, exc):
    if any(segment in request.url.path for segment in ("/research-vault/", "/simulation/", "/live-markets/")):
        # Do not echo credentials, oversized/nonfinite inputs or exception ctx.
        return JSONResponse(status_code=422, content={"detail": [
            {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
            for error in exc.errors()]})
    return await request_validation_exception_handler(request, exc)


for router in (health.router, markets.router, strategy.router, orders.router, risk.router, positions.router, agents.router, simulation.router, research_vault_router, research_markets_router, live_markets_router, accounting.router, terminal.router):
    app.include_router(router, prefix=settings.api_prefix)
app.include_router(websocket.router)


@app.get("/")
async def root():
    return {"name": "HyperAMM", "phase": "1-12", "docs": "/docs"}
