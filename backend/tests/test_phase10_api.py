from fastapi.testclient import TestClient

from app.main import app

import asyncio
from threading import Event, get_ident

import httpx
import pytest

from app.simulation.service import SimulationService
from app.simulation.version import SIMULATION_ENGINE_VERSION


OPTIMIZE_PAYLOAD={
    "strategy_grid":{"levels_per_side":[4]},"agent_grid":{},
    "training_scenarios":["QUIET"],"validation_scenarios":["TREND_UP"],
    "frames":3,"max_candidates":1,"top_n":1,
}


@pytest.mark.asyncio
@pytest.mark.parametrize("operation",["run_scenario","optimize"])
async def test_worker_keeps_health_responsive_and_rejects_overflow(monkeypatch,operation):
    live_loop=asyncio.get_running_loop()
    live_thread=get_ident()
    started=asyncio.Event()
    release=Event()
    original=getattr(SimulationService,operation)
    seen=[]
    async def held(self,**inputs):
        assert get_ident()!=live_thread
        assert asyncio.get_running_loop() is not live_loop
        seen.append(self)
        live_loop.call_soon_threadsafe(started.set)
        assert release.wait(10),"test did not release research worker"
        return await original(self,**inputs)
    monkeypatch.setattr(SimulationService,operation,held)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://localhost") as client:
            path="optimize" if operation=="optimize" else "run"
            payload=OPTIMIZE_PAYLOAD if path=="optimize" else {"frames":3}
            first=asyncio.create_task(client.post(f"/api/v1/simulation/{path}",json=payload))
            try:
                await asyncio.wait_for(started.wait(),5)
                health=await asyncio.wait_for(client.get("/api/v1/health"),5)
                assert health.status_code==200
                for busy_path,busy_payload in (("optimize",OPTIMIZE_PAYLOAD),("run",{"frames":3})):
                    overflow=await client.post(f"/api/v1/simulation/{busy_path}",json=busy_payload)
                    assert overflow.status_code==429
                    assert "already running" in overflow.json()["detail"]
                assert not first.done()
            finally:
                release.set()
                response=await asyncio.wait_for(first,5)
            assert response.status_code==200,response.text
            next_response=await client.post(f"/api/v1/simulation/{path}",json=payload)
            assert next_response.status_code==200,next_response.text
            assert seen[0] is not seen[1]


@pytest.mark.parametrize("path,payload",[("run",{"frames":3}),("optimize",OPTIMIZE_PAYLOAD)])
def test_api_unexpected_failure_is_sanitized_and_slot_released(monkeypatch,caplog,path,payload):
    from app.simulation.engine import SimulationEngine
    original=SimulationEngine.run
    failed=False
    calls=0
    async def injected(self,**inputs):
        nonlocal failed,calls
        calls+=1
        # For optimization, fail in candidate execution after the baseline.
        if not failed and calls==(2 if path=="optimize" else 1):
            failed=True
            raise RuntimeError("unexpected simulation invariant failure")
        return await original(self,**inputs)
    monkeypatch.setattr(SimulationEngine,"run",injected)
    with TestClient(app) as client:
        response=client.post(f"/api/v1/simulation/{path}",json=payload)
        assert response.status_code==500
        assert "invariant" not in response.text
        assert "unexpected simulation invariant failure" in caplog.text
        assert client.post(f"/api/v1/simulation/{path}",json=payload).status_code==200


@pytest.mark.parametrize("path,payload",[("run",{"frames":3}),("optimize",OPTIMIZE_PAYLOAD)])
def test_api_rejects_spoofed_engine_version_and_unknown_fields(path,payload):
    with TestClient(app) as client:
        for extra in ({"simulation":{"engine_version":"fake-version"}},
                      {"simulation":{"safety_override":True}},
                      {"engine_version":"fake-version"}):
            response=client.post(f"/api/v1/simulation/{path}",json={**payload,**extra})
            assert response.status_code==422
            assert any(x["type"]=="extra_forbidden" for x in response.json()["detail"])
        response=client.post(f"/api/v1/simulation/{path}",json=payload)
        assert response.status_code==200,response.text
        assert response.json()["engine_version"]==SIMULATION_ENGINE_VERSION


@pytest.mark.parametrize("extra",[
    {"frames":1001},{"max_candidates":129},{"top_n":11},{"top_n":0},
    {"training_scenarios":["QUIET"]*9},{"validation_scenarios":["TREND_UP"]*9},
    {"simulation":{"max_frames":5001}},{"simulation":{"trace_max_points":5001}},
    {"objective":{"unknown_weight":1}},
])
def test_optimization_api_preserves_workload_bounds(extra):
    with TestClient(app) as client:
        assert client.post("/api/v1/simulation/optimize",json={**OPTIMIZE_PAYLOAD,**extra}).status_code==422


def test_worker_receives_only_detached_config_inputs(monkeypatch):
    original=SimulationService.optimize
    async def inspect(self,**inputs):
        rt=app.state.runtime
        # Inspect identities for the test only; production workers never read rt.
        for name,live in (("strategy",rt.config),("agents",rt.agent_config),("risk",rt.risk_config)):
            assert inputs[name] is not live
            assert inputs[name].model_dump()==live.model_dump()
        assert set(inputs)=={"strategy","agents","risk","simulation","strategy_grid","agent_grid",
                            "training_scenarios","validation_scenarios","objective","max_candidates","frames","top_n"}
        inputs["strategy"].levels_per_side=4
        inputs["agents"].agents_enabled=False
        inputs["risk"].enabled=False
        inputs["strategy_grid"]["levels_per_side"].append(6)
        return await original(self,**inputs)
    monkeypatch.setattr(SimulationService,"optimize",inspect)
    with TestClient(app) as client:
        rt=app.state.runtime
        def snapshot():
            return (rt.config.model_dump(),rt.agent_config.model_dump(),rt.risk_config.model_dump(),
                    rt.strategy.running,rt.risk.kill_switch_active,id(rt.execution),
                    [x.model_dump() for x in rt.paper.all_orders()])
        before=snapshot()
        response=client.post("/api/v1/simulation/optimize",json={**OPTIMIZE_PAYLOAD,"max_candidates":2})
        assert response.status_code==200,response.text
        assert snapshot()==before


def test_phase10_scenario_run_and_live_runtime_immutability():
    with TestClient(app) as client:
        before=client.get("/api/v1/strategy").json()
        scenarios=client.get("/api/v1/simulation/scenarios")
        assert scenarios.status_code==200
        payload=scenarios.json()
        assert payload["simulated"] is True
        names={x["name"] for x in payload["scenarios"]}
        assert {"QUIET","FLASH_MOVE","ORACLE_DISLOCATION","REFERENCE_DEGRADATION"}<=names

        response=client.post("/api/v1/simulation/run",json={
            "scenario":"QUIET","frames":8,
            "simulation":{"max_frames":8,"trace_max_points":4},
        })
        assert response.status_code==200,response.text
        data=response.json()
        assert data["simulated"] is True
        assert len(data["run_fingerprint"])==64
        assert data["metrics"]["frame_count"]==8
        assert len(data["trace"])<=4
        assert any("crossing-only" in item.lower() for item in data["limitations"])
        assert client.get("/api/v1/strategy").json()==before


def test_phase10_optimize_returns_baseline_and_ranked_candidates_without_runtime_mutation():
    with TestClient(app) as client:
        before=client.get("/api/v1/strategy").json()
        response=client.post("/api/v1/simulation/optimize",json={
            "strategy_grid":{"levels_per_side":[4,6]},
            "agent_grid":{},
            "training_scenarios":["QUIET"],
            "validation_scenarios":["TREND_UP"],
            "frames":6,
            "max_candidates":4,
            "top_n":2,
            "simulation":{"max_frames":6,"record_trace":False},
        })
        assert response.status_code==200,response.text
        data=response.json()
        assert data["simulated"] is True
        assert data["baseline"]["label"]=="BASELINE"
        assert data["candidate_count"]==2
        assert data["ranked_candidates"]
        assert all(item["validation"] for item in data["ranked_candidates"])
        assert client.get("/api/v1/strategy").json()==before


def test_phase10_api_rejects_unbounded_and_safety_parameter_requests():
    with TestClient(app) as client:
        too_many=client.post("/api/v1/simulation/optimize",json={
            "strategy_grid":{"levels_per_side":list(range(1,51))},
            "agent_grid":{"regime_spread_strength":[str(i/10) for i in range(1,10)]},
            "training_scenarios":["QUIET"],
            "validation_scenarios":["TREND_UP"],
            "frames":6,
            "max_candidates":32,
        })
        assert too_many.status_code==422

        safety=client.post("/api/v1/simulation/optimize",json={
            "strategy_grid":{"execution_mode":["TESTNET"]},
            "agent_grid":{},
            "training_scenarios":["QUIET"],
            "validation_scenarios":["TREND_UP"],
            "frames":6,
        })
        assert safety.status_code==422


def test_phase10_api_requires_frame_count_within_simulation_bound():
    with TestClient(app) as client:
        response=client.post("/api/v1/simulation/run",json={
            "scenario":"QUIET","frames":300,
            "simulation":{"max_frames":250},
        })
        assert response.status_code==422


def test_phase10_service_does_not_mutate_any_live_authority_state():
    with TestClient(app) as client:
        rt=app.state.runtime
        before={
            "config":rt.config.model_dump(mode="json"),
            "agents":rt.agent_config.model_dump(mode="json"),
            "risk_config":rt.risk_config.model_dump(mode="json"),
            "running":rt.strategy.running,
            "kill":rt.risk.kill_switch_active,
            "execution_id":id(rt.execution),
            "paper_orders":[o.model_dump(mode="json") for o in rt.paper.all_orders()],
        }
        response=client.post("/api/v1/simulation/run",json={
            "scenario":"FLASH_MOVE","frames":8,
            "simulation":{"max_frames":8,"record_trace":False},
        })
        assert response.status_code==200,response.text
        after={
            "config":rt.config.model_dump(mode="json"),
            "agents":rt.agent_config.model_dump(mode="json"),
            "risk_config":rt.risk_config.model_dump(mode="json"),
            "running":rt.strategy.running,
            "kill":rt.risk.kill_switch_active,
            "execution_id":id(rt.execution),
            "paper_orders":[o.model_dump(mode="json") for o in rt.paper.all_orders()],
        }
        assert after==before
