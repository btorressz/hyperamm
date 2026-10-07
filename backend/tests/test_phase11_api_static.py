import ast
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def test_required_fastapi_endpoints_and_decimal_contracts():
    paths = ("health", "strategy", "positions", "risk", "vault", "accounting/pnl",
             "accounting/position", "accounting/ledger", "accounting/events")
    with TestClient(app) as client:
        for path in paths:
            assert client.get("/api/v1/" + path).status_code == 200, path
        vault = client.get("/api/v1/vault").json()
        assert vault["mode"] == "PAPER" and vault["simulated"]
        assert isinstance(vault["equity_quote"], str)
        assert vault["accounting_complete"] == "COMPLETE"
        assert client.get("/api/v1/accounting/ledger?limit=500").status_code == 200
        for limit in (0, -1, 501):
            assert client.get(f"/api/v1/accounting/ledger?limit={limit}").status_code == 422
            assert client.get(f"/api/v1/accounting/events?limit={limit}").status_code == 422
        assert client.post("/api/v1/vault").status_code == 405


def test_terminal_websocket_has_compact_accounting_without_full_ledger():
    with TestClient(app) as client:
        assert client.get("/api/v1/vault").status_code == 200
        with client.websocket_connect("/ws/terminal") as ws:
            payload = ws.receive_json()
            assert "vault" in payload and "accounting" in payload
            assert payload["vault"]["simulated"]
            assert payload["accounting"]["accounting_fingerprint"] == payload["vault"]["accounting_fingerprint"]
            assert len(payload["accounting"]["events"]) <= 20
            assert "ledger" not in payload["accounting"]
            assert "entries" not in payload["accounting"]
            for field in ("market", "strategy", "risk_authorization", "agents", "orders", "fills", "pnl_drawdown"):
                assert field in payload


def test_accounting_has_no_execution_network_or_credential_access():
    root = Path(__file__).resolve().parents[2]
    for path in (root / "backend/app/accounting").glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                assert not any(name.startswith(("httpx", "requests", "websockets", "eth_account", "hyperliquid", "os")) for name in names)
            if isinstance(node, ast.FunctionDef):
                assert node.name not in {"submit_order", "cancel_order", "replace_order", "submit_orders", "cancel_orders"}
    assert not (root / ".github").exists()


def test_single_position_formula_and_simulation_consumption():
    root = Path(__file__).resolve().parents[2]
    runtime = (root / "backend/app/runtime.py").read_text()
    engine = (root / "backend/app/simulation/engine.py").read_text()
    metrics = (root / "backend/app/simulation/metrics.py").read_text()
    assert "paper_pnl(" not in runtime + engine + metrics
    assert "AccountingService" in runtime and "AccountingService" in engine
    assert "to_pnl_drawdown" in runtime and "to_pnl_drawdown" in engine
    assert "peak_equity-equity" not in engine
    assert "self.initial_equity+session" not in metrics


def test_read_only_accounting_routes_and_active_vault_ui():
    root = Path(__file__).resolve().parents[2]
    for route in app.routes:
        path = getattr(route, "path", "")
        if path.startswith("/api/v1/accounting") or path == "/api/v1/vault":
            assert route.methods == {"GET"}
    sidebar = (root / "frontend/src/components/Sidebar.tsx").read_text()
    assert "['Vault','active']" in sidebar
    ui = "\n".join((root / path).read_text() for path in (
        "frontend/src/pages/Vault.tsx", "frontend/src/components/VaultSummary.tsx", "frontend/src/components/AccountingLedger.tsx"))
    assert "PAPER / SIMULATED" in ui and "TESTNET /" in ui and "Unavailable" in ui
    for token in ("deposit", "withdrawal", "transfer", "bridge", "investor", "management_fee", "performance_fee"):
        assert token not in ui.lower()
