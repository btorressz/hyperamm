"""Exercise independent advisory and operational outcomes in one runtime fixture."""
from copy import deepcopy
from datetime import timedelta

import pytest

from app import main
from app.agents.advisory_coordinator import RECEIPT_HEADER
from app.market_data.market_universe_discovery import DiscoveryFailure
from test_phase14_research_vault import authority
from test_phase182_generalized_paper import URL
from test_phase183c_market_risk_calculations import hypothetical
from test_phase183d_paper_risk_integration import offline_boundaries  # noqa: F401
from test_phase183ef_risk_api import EVIDENCE, risk_api, target  # noqa: F401
from test_phase184d_quote_economics import options
from test_phase184e_advisory_api import ADVISORY, advisory_api, assert_snapshot, paper_run  # noqa: F401
from test_phase185d_asset_paper import asset_proposal
from test_phase9_runtime import insufficient_refs, prepared_runtime


@pytest.fixture
async def seeded_runtime():
    # Build the disabled adapter before the research fixture installs its
    # no-construction and no-signing tripwires for the actual route calls.
    runtime, _ = await prepared_runtime()
    runtime.strategy.running = True
    assert runtime.authorization.authorized
    await runtime.orders.reconcile(runtime.config.market, runtime.quotes,
                                   runtime.config.replace_tolerance_bps, runtime.config.size_tolerance)
    assert await runtime.paper.get_open_orders()
    return runtime


async def test_qualified_research_preserves_seeded_authority_during_partial_advisory_failure(
    seeded_runtime, advisory_api, monkeypatch,
):
    client, discovery, _, request, records, clock, _, provider = advisory_api
    runtime = seeded_runtime
    before = deepcopy(authority(runtime))
    bindings = runtime.testnet, runtime.testnet.authority, runtime.orders.execution
    listeners = tuple(runtime.market._listeners)
    monkeypatch.setattr(main.app.state, "runtime", runtime, raising=False)
    assert not runtime.testnet.enabled

    catalog = await discovery.catalog()
    market = records["xyz"]
    risk = await client.get(EVIDENCE, params=target(catalog, market))
    assert risk.status_code == 200 and risk.json()["authority"] == "NONE"

    standard = await paper_run(client, market, research_risk=hypothetical(capital_paper_quote="10000"))
    asset = asset_proposal(market, price="3000", frames=12, catalog=catalog.catalog_fingerprint)
    payload = asset.model_dump(mode="json")
    admitted = await client.post(URL + "/eligibility", json=payload)
    assert admitted.status_code == 200 and admitted.json()["status"] == "ELIGIBLE"
    run_payload = {**payload, "expected": admitted.json()["binding"]}
    completed = await client.post(URL + "/run", json=run_payload)
    assert completed.status_code == 200 and completed.json()["execution_mode"] == "PAPER"

    def unavailable():
        raise DiscoveryFailure("RATE_LIMITED")

    provider["xyz"] = unavailable
    receipt = standard.headers[RECEIPT_HEADER]
    for point in standard.json()["result"]["trace"]:
        quote = {"sequence": point["sequence"], "assumptions": options().model_dump(mode="json")}
        result = await client.post(ADVISORY, json=request("xyz", "QUOTE_ECONOMICS", paper_receipt=receipt,
                                                         funding_mode="OBSERVED", quote=quote))
        assert result.status_code == 200, result.text
        wire = result.json()
        if wire["snapshot"]["quote_economics"]["status"] == "READY":
            break
    else:
        pytest.fail("fixture produced no mature quote cohort")
    assert_snapshot(wire)
    assert wire["snapshot"]["funding_basis"]["status"] == "ERROR"
    assert wire["snapshot"]["quote_economics"]["attributed_fill_count"] > 0
    assert wire["paper_result_fingerprint"] == standard.json()["result_fingerprint"]

    clock[0] += timedelta(seconds=61)
    replacement = await discovery.catalog()
    assert replacement.catalog_fingerprint != catalog.catalog_fingerprint
    stale = await client.post(ADVISORY, json=request("xyz", "QUOTE_ECONOMICS", paper_receipt=receipt))
    assert stale.status_code == 409
    assert authority(runtime) == before
    assert bindings == (runtime.testnet, runtime.testnet.authority, runtime.orders.execution)
    assert listeners == tuple(runtime.market._listeners)

    def agent_unavailable(*_args):
        raise RuntimeError("fixture supervisory outage")

    monkeypatch.setattr(runtime.agent_supervisor.perp_crowding, "evaluate", agent_unavailable)
    monkeypatch.setattr(runtime.reference_service, "snapshot", lambda *_args, **_kwargs: insufficient_refs())
    await runtime.refresh_once()
    assert runtime.agent_decision.perp_crowding.health == "ERROR"
    assert not runtime.agent_decision.predictive_adverse_selection.affects_quotes
    assert runtime.risk_decision.state == "HALT"
    assert not runtime.authorization.authorized and not runtime.quotes
    assert not await runtime.paper.get_open_orders()
