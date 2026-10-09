from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.deployment import LocalOnlyBoundary, validate_local_deployment
from app.config import get_settings
from app.runtime import HyperAmmRuntime
from app.simulation.executor import SimulationExecutor
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
for router in (health.router, markets.router, strategy.router, orders.router, risk.router, positions.router, agents.router, simulation.router, accounting.router, terminal.router):
    app.include_router(router, prefix=settings.api_prefix)
app.include_router(websocket.router)


@app.get("/")
async def root():
    return {"name": "HyperAMM", "phase": "1-12", "docs": "/docs"}
