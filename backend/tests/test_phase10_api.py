from fastapi.testclient import TestClient

from app.main import app


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
