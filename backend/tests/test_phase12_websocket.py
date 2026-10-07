from datetime import datetime
from fastapi.testclient import TestClient
from app.main import app


def test_websocket_sequence_compact_fields_and_disconnect():
    with TestClient(app) as client:
        assert client.get("/api/v1/amm/curve").status_code == 200
        with client.websocket_connect("/ws/terminal") as ws:
            a, b = ws.receive_json(), ws.receive_json()
            assert b["sequence"] > a["sequence"]
            for s in (a, b):
                assert s["contract_version"] == "phase12-v1"
                assert datetime.fromisoformat(s["emitted_at"]).tzinfo is not None
                assert s["vault"]["execution_accounting"]["status"] == "CONSISTENT"
                for k in (
                    "market",
                    "strategy",
                    "risk",
                    "risk_authorization",
                    "agents",
                    "accounting",
                    "strategy_quotes",
                    "agent_quotes",
                    "authorized_quotes",
                    "system_health",
                ):
                    assert k in s
                assert len(s["fills"]) <= 100 and len(s["accounting"]["events"]) <= 20
                assert (
                    not {
                        "history",
                        "ledger",
                        "simulation_trace",
                        "optimizer_results",
                        "credentials",
                    }
                    & s.keys()
                )
                assert not {"ledger", "entries"} & s["accounting"].keys()
        assert client.get("/api/v1/health").status_code == 200


def test_history_and_events_routes_are_readonly_bounded_and_validated():
    with TestClient(app) as client:
        h = client.get("/api/v1/terminal/history").json()
        assert h["max_points"] == 3600 and h["query_max"] == 1000
        assert "session" in h["available_ranges"]
        for path in (
            "history?limit=0",
            "history?limit=1001",
            "history?range=24h",
            "events?limit=501",
            "events?category=RAW_LOGS",
        ):
            assert client.get("/api/v1/terminal/" + path).status_code == 422
        e = client.get("/api/v1/terminal/events?category=MARKET").json()
        assert all(x["category"] == "MARKET" for x in e["events"])
        for path in ("history", "events"):
            assert client.post("/api/v1/terminal/" + path).status_code == 405
