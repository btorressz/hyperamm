import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_terminal_package_has_no_authority_dependencies_or_order_methods():
    for path in (ROOT / "backend/app/terminal").glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert node.name not in {
                    "submit_order",
                    "cancel_order",
                    "replace_order",
                    "submit_orders",
                    "cancel_orders",
                }
            if isinstance(node, ast.ImportFrom):
                assert node.module not in {
                    "app.risk.firewall",
                    "app.agents.supervisor",
                    "app.accounting.service",
                    "app.execution.order_manager",
                }
            if isinstance(node, ast.Name):
                assert node.id not in {
                    "RiskFirewall",
                    "AgentSupervisor",
                    "AccountingService",
                    "OrderManager",
                }


def test_only_terminal_get_routes_added_no_automation_directory():
    source = (ROOT / "backend/app/api/terminal.py").read_text()
    assert "@router.post" not in source and "@router.put" not in source
    assert not (ROOT / ".github").exists()
    for word in ("sqlite", "redis", "psycopg"):
        assert (
            word not in (ROOT / "backend/app/terminal/history.py").read_text().lower()
        )
