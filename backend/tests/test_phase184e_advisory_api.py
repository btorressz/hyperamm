"""Advisory acceptance against the real discovery and isolated PAPER worker."""
import asyncio
import json
from datetime import timedelta
from decimal import Decimal
from threading import Event

import pytest
from pydantic import ValidationError

from app import main
from app.agents.advisory_coordinator import RECEIPT_HEADER, AdvisoryCoordinator
from app.agents.advisory_contracts import AdvisorySnapshot
from app.market_data.advisory_market_observations import _epoch_ms
from app.market_data.market_universe_discovery import DiscoveryFailure
from app.market_data.models import utcnow
from app.risk.authorization import FinalQuoteAuthorization
from test_phase182_generalized_paper import URL, proposal_for
from test_phase183c_market_risk_calculations import hypothetical, sourced
from test_phase183d_paper_risk_integration import offline_boundaries  # noqa: F401
from test_phase183ef_risk_api import risk_api  # noqa: F401
from test_phase184d_quote_economics import options

ADVISORY = "/api/v1/market-universe/advisory"


@pytest.fixture
async def advisory_api(risk_api, monkeypatch):
    client, discovery, clock, _ = risk_api
    coordinator = AdvisoryCoordinator(discovery, clock=lambda: max(clock[0], utcnow()))
    monkeypatch.setattr(main.app.state, "advisory_coordinator", coordinator, raising=False)
    catalog = await discovery.catalog()
    records = {record.identity.dex: record for record in catalog.catalog.records}
    calls, provider = [], {}

    def observe(operation, identity, deadline, **kwargs):
        calls.append((operation, identity.stable_key))
        if action := provider.get(identity.dex):
            action()
        coin = identity.exchange_coin
        at = _epoch_ms(clock[0])
        if operation == "metaAndAssetCtxs":
            row = {"coin": coin, "markPx": "100.13", "oraclePx": "100", "funding": "0.0002", "openInterest": "100"}
            financial = discovery.financial_observation(catalog.catalog_fingerprint, identity)
            metadata = {"universe": [{"name": coin, "szDecimals": 3}]}
            if financial is not None and financial.collateral_token_index is not None:
                metadata["collateralToken"] = financial.collateral_token_index
            return [metadata, [row]]
        if operation == "l2Book":
            return {"coin": coin, "time": at - 20,
                    "levels": [[{"px": "100.10", "sz": "1"}], [{"px": "100.14", "sz": "1"}]]}
        assert operation == "fundingHistory"
        return [{"coin": coin, "time": at - 200, "fundingRate": "-0.0002"}]

    monkeypatch.setattr(coordinator._observations._client, "request", observe)

    def request(dex="", operation="DISCOVERY", **kwargs):
        return {"identity": records[dex].identity.model_dump(mode="json"),
                "catalog_fingerprint": catalog.catalog_fingerprint, "operation": operation, **kwargs}

    try:
        yield client, discovery, coordinator, request, records, clock, calls, provider
    finally:
        await coordinator.close()


async def paper_run(client, record, **overrides):
    proposal = proposal_for(record, price="3000", frames=30, scenario="HIGH_VOLATILITY",
                            economics={"model": "HYPOTHETICAL_LINEAR", "funding_interval_seconds": 3},
                            **overrides).model_dump(mode="json")
    eligible = await client.post(URL + "/eligibility", json=proposal)
    assert eligible.status_code == 200, eligible.text
    run = await client.post(URL + "/run", json={**proposal, "expected": eligible.json()["binding"]})
    assert run.status_code == 200, run.text
    return run


def assert_snapshot(wire):
    snapshot = AdvisorySnapshot.model_validate_json(json.dumps(wire["snapshot"]))
    assert wire["snapshot_fingerprint"] == snapshot.fingerprint()
    assert snapshot.validate_at(as_of=snapshot.context.evaluated_at) == snapshot
    assert wire["authority"] == "NONE" and wire["read_only"] is True
    for key in ("affects_quotes", "execution_eligible", "can_override_risk", "can_authorize_paper"):
        assert wire[key] is False
    for key in ("market_eligibility", "funding_basis", "quote_economics"):
        if advice := wire["snapshot"][key]:
            with pytest.raises(ValidationError):
                FinalQuoteAuthorization.model_validate(advice)


async def test_catalog_eligibility_and_qualified_public_funding(advisory_api):
    client, discovery, _, request, records, _, calls, _ = advisory_api
    body = request()
    response = await client.post(ADVISORY, json=body)
    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json()["snapshot"]["market_eligibility"]["status"] == "READY"
    assert calls == []
    assert_snapshot(response.json())

    namespaces = ("xyz", "other", "xyz", "")
    fetched = await asyncio.gather(*(client.post(ADVISORY, json=request(dex, "FUNDING_BASIS")) for dex in namespaces))
    assert len(calls) == 9
    for response, dex in zip(fetched, namespaces, strict=True):
        assert response.status_code == 200, response.text
        wire = response.json()
        assert_snapshot(wire)
        assert wire["identity"]["dex"] == dex
        funding = wire["snapshot"]["funding_basis"]
        assert funding["status"] == "READY" and funding["provenance"] == "EXCHANGE_OBSERVED"
        assert funding["mark_price"] == "100.13" and funding["midpoint_price"] == "100.12"
        assert Decimal(funding["mark_oracle_basis_bps"]) == Decimal(13)
        assert Decimal(funding["mark_mid_basis_bps"]) == Decimal("0.99880144")
        sources = {source["category"]: source for source in wire["snapshot"]["context"]["sources"]}
        assert sources["FUNDING"]["observed_at"] is None
        assert sources["MID_PRICE"]["observed_at"] is not None

    record = records["xyz"]
    financial = discovery.financial_observation(body["catalog_fingerprint"], record.identity)
    for mode, settings in (("STANDARD_PAPER", None), ("HYPOTHETICAL_RISK", hypothetical()),
                           ("SOURCE_CONSTRAINED_RISK", sourced(financial))):
        proposal = proposal_for(record, price="3000", research_risk=settings).model_dump(mode="json")
        response = await client.post(ADVISORY, json=request("xyz", mode, proposal=proposal))
        assert response.status_code == 200, response.text
        assert response.json()["snapshot"]["market_eligibility"]["suitability"] == "SUITABLE"
        assert_snapshot(response.json())


async def test_receipt_and_quote_isolated_from_provider_rate_limit(advisory_api):
    client, _, _, request, records, _, calls, provider = advisory_api
    run = await paper_run(client, records["xyz"], research_risk=hypothetical(capital_paper_quote="10000"))
    receipt, result = run.headers[RECEIPT_HEADER], run.json()
    body = request("xyz", "QUOTE_ECONOMICS", paper_receipt=receipt)
    lookup = await client.post(ADVISORY, json=body)
    assert lookup.status_code == 200, lookup.text
    assert lookup.json()["issues"] == ["QUOTE_COHORT_REQUIRED"]
    assert lookup.json()["quote_cohorts"] == [point["sequence"] for point in result["result"]["trace"]]
    assert lookup.json()["paper_result_fingerprint"] == result["result_fingerprint"]
    assert calls == []

    for sequence in lookup.json()["quote_cohorts"]:
        quote = {"sequence": sequence, "assumptions": options().model_dump(mode="json")}
        response = await client.post(ADVISORY, json={**body, "quote": quote})
        assert response.status_code == 200, response.text
        economics = response.json()["snapshot"]["quote_economics"]
        if economics["status"] == "READY":
            break
    else:
        pytest.fail("deterministic worker did not produce a mature quote cohort")
    assert economics["attributed_fill_count"] == economics["matured_markout_count"] > 0

    synthetic = await client.post(ADVISORY, json={**body, "funding_mode": "PAPER", "quote": quote})
    assert synthetic.status_code == 200, synthetic.text
    assert_snapshot(synthetic.json())
    assert synthetic.json()["snapshot"]["funding_basis"]["provenance"] == "SCENARIO_SYNTHETIC"
    assert not calls

    def rate_limited():
        raise DiscoveryFailure("RATE_LIMITED")

    provider["xyz"] = rate_limited
    for _ in range(2):
        response = await client.post(ADVISORY, json={**body, "funding_mode": "OBSERVED", "quote": quote})
        assert response.status_code == 200, response.text
        wire = response.json()
        assert_snapshot(wire)
        assert wire["issues"] == ["PROVIDER_RATE_LIMITED"]
        assert wire["snapshot"]["funding_basis"]["status"] == "ERROR"
        assert wire["snapshot"]["funding_basis"]["confidence"] == "0"
        assert wire["snapshot"]["quote_economics"] == {**economics,
            "context_fingerprint": wire["snapshot"]["quote_economics"]["context_fingerprint"],
            "evaluated_at": wire["evaluated_at"]}
    assert len(calls) == 1


async def test_forged_selectors_and_unavailable_receipts(advisory_api):
    client, _, coordinator, request, records, _, calls, _ = advisory_api
    body = request("xyz")
    for field, value in [
        ("sources", [{"provenance": "EXCHANGE_OBSERVED"}]), ("snapshot", {"status": "READY"}),
        ("paper_result", {"orders": [], "fills": [], "markouts": []}), ("source_fingerprint", "a" * 64),
        ("execution_eligible", True), ("operation", "SUBMIT"),
    ]:
        response = await client.post(ADVISORY, json={**body, field: value})
        assert response.status_code == 422, response.text
    for identity, error in [
        ({"network": "TESTNET"}, "WRONG_NETWORK"), ({"dex": "absent"}, "WRONG_DEX"),
        ({"instrument_name": "UNKNOWN"}, "UNKNOWN_MARKET"),
    ]:
        response = await client.post(ADVISORY, json={**body, "identity": {**body["identity"], **identity}})
        assert response.json()["detail"]["code"] == error
    run = await paper_run(client, records["xyz"])
    receipt = run.headers[RECEIPT_HEADER]
    response = await client.post(ADVISORY, json=request("other", "QUOTE_ECONOMICS", paper_receipt=receipt))
    assert response.status_code == 409 and response.json()["detail"]["code"] == "PAPER_BINDING_MISMATCH"
    quote = {"sequence": 119, "assumptions": options().model_dump(mode="json")}
    response = await client.post(ADVISORY, json=request("xyz", "QUOTE_ECONOMICS", paper_receipt=receipt, quote=quote))
    assert response.status_code == 200 and response.json()["issues"] == ["INVALID_QUOTE_COHORT"]
    for token in (run.json()["result_fingerprint"], "a" * 64):
        response = await client.post(ADVISORY, json=request("xyz", "QUOTE_ECONOMICS", paper_receipt=token))
        assert response.json()["issues"] == ["PAPER_RESULT_UNAVAILABLE"]
    await coordinator.close()
    response = await client.post(ADVISORY, json=request("xyz", "QUOTE_ECONOMICS", paper_receipt=receipt))
    assert response.json()["issues"] == ["PAPER_RESULT_UNAVAILABLE"]
    assert not calls


async def test_retired_generation_rejected_after_public_await(advisory_api):
    client, discovery, _, request, _, clock, _, provider = advisory_api
    started, release = Event(), Event()

    def wait():
        started.set()
        assert release.wait(5)

    provider["xyz"] = wait
    pending = asyncio.create_task(client.post(ADVISORY, json=request("xyz", "FUNDING_BASIS")))
    try:
        assert await asyncio.to_thread(started.wait, 5)
        clock[0] += timedelta(seconds=1)
        discovery._expires = 0
        current = await discovery.catalog()
        assert current.catalog_fingerprint != request()["catalog_fingerprint"]
    finally:
        release.set()
    response = await pending
    assert response.status_code == 409 and response.json()["detail"]["code"] == "CATALOG_STALE"
