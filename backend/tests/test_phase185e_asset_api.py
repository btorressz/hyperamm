from copy import deepcopy
from datetime import timedelta

import pytest

from app.api.market_universe import AssetPolicyPreview
from app.market_data.models import utcnow
from app.simulation import generalized_market_profiles as paper
from app.simulation.engine import SimulationEngine
from app.simulation.models import stable_fingerprint
from test_phase182_generalized_paper import URL, proposal_for
from test_phase183c_market_risk_calculations import hypothetical, sourced
from test_phase183d_paper_risk_integration import offline_boundaries  # noqa: F401
from test_phase183ef_risk_api import risk_api  # noqa: F401
from test_phase184e_advisory_api import ADVISORY, advisory_api  # noqa: F401

PREVIEW = URL + "/asset-policy/preview"


def preview_request(catalog, record, **overrides):
    return {
        "profile_version": paper.PROFILE_VERSION, "identity": record.identity.model_dump(mode="json"),
        "catalog_fingerprint": catalog.catalog_fingerprint, "simulated_reference_price": "100",
        "minimum_order_notional": "20", "family": "UNKNOWN", **overrides,
    }


@pytest.mark.parametrize(("dex", "model", "risk"), [
    ("", "CONSTANT_PRODUCT", "none"),
    ("xyz", "CONCENTRATED", "hypothetical"),
    ("xyz", "CONCENTRATED", "source"),
])
async def test_preview_constructs_bound_draft_then_existing_routes_admit_and_run(advisory_api, dex, model, risk):
    client, discovery, _, _, records, clock, *_ = advisory_api
    catalog = await discovery.catalog()
    record = records[dex]
    observed = discovery.financial_observation(catalog.catalog_fingerprint, record.identity)
    settings = {"none": None, "hypothetical": hypothetical(), "source": sourced(observed)}[risk]
    controls = {"amm_model": model, "levels_per_side": 2, "volatility_spread_strength": "1.2"}
    request = preview_request(catalog, record, controls=controls)
    if settings is not None:
        request["research_risk"] = settings.model_dump(mode="json")
    response = await client.post(PREVIEW, json=request)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    draft = response.json()
    policy = AssetPolicyPreview.model_validate_json(response.content).policy
    assert draft["assessment"]["policy_fingerprint"] == policy.fingerprint()
    assert draft["assessment"]["status"] == "RESEARCH_DRAFT"
    assert draft["assessment"]["eligible_for_paper"] is draft["assessment"]["execution_eligible"] is False
    assert policy.declared_at == clock[0] and policy.metadata == record
    assert policy.authority == draft["assessment"]["authority"] == "NONE"
    assert (policy.research_risk_fingerprint is None) == (settings is None)
    proposal = proposal_for(record, price="100", minimum_order_notional="20", frames=12,
                            research_risk=settings, asset_amm_policy=policy)
    payload = proposal.model_dump(mode="json")
    response = await client.post(URL + "/eligibility", json=payload)
    assert response.status_code == 200, response.text
    expected = response.json()["binding"]
    assert expected["asset_policy_fingerprint"] == policy.fingerprint()
    assert expected.get("research_risk_fingerprint") == policy.research_risk_fingerprint
    reference, prepared = paper.assess(
        proposal, record, network=record.identity.network, evaluated_at=clock[0], max_age_seconds=60,
        catalog_fingerprint=catalog.catalog_fingerprint, catalog_valid_until=discovery.paper_generation(catalog.catalog_fingerprint)[0],
        risk_source=observed if settings is not None else None,
    )
    assert expected == reference.binding.model_dump(mode="json")
    direct = await paper.execute_paper(
        SimulationEngine(), proposal=proposal, metadata=record, network=record.identity.network,
        expected=reference.binding, max_age_seconds=60, risk_source=observed if settings is not None else None,
        catalog_valid_until=reference.valid_until, catalog_guard=lambda: True,
    )
    result = await client.post(URL + "/run", json={**payload, "expected": expected})
    assert result.status_code == 200, result.text
    wire = result.json()
    assert wire["execution_mode"] == "PAPER" and wire["admission"]["execution_eligible"] is False
    assert wire["proposal"]["asset_amm_policy"] == draft["policy"]
    assert wire["result"]["strategy_fingerprint"] == stable_fingerprint(prepared.strategy)
    assert wire["result_fingerprint"] == direct.result_fingerprint
    assert wire["result"] == direct.result.model_dump(mode="json")


async def test_preview_keeps_all_classifications_numeric_and_never_enters_scenario(advisory_api, monkeypatch):
    client, discovery, _, _, records, *_ = advisory_api
    catalog = await discovery.catalog()

    def unexpected(*args, **kwargs):
        pytest.fail("preview entered scenario construction or the simulation worker")

    monkeypatch.setattr(paper, "_build_scenario", unexpected)
    monkeypatch.setattr(SimulationEngine, "run", unexpected)
    controls, fingerprints = [], set()
    for family in ("CRYPTO", "EQUITY", "INDEX", "COMMODITY", "ENERGY", "FX", "RATES", "OTHER", "UNKNOWN"):
        response = await client.post(PREVIEW, json=preview_request(catalog, records["xyz"], family=family))
        assert response.status_code == 200, response.text
        draft = response.json()
        assert draft["policy"]["classification"] == {
            "contract_version": "phase185a-v1", "family": family, "provenance": "OPERATOR_DECLARED_RESEARCH",
            "exchange_class_verified": False, "tradability_verified": False,
        }
        controls.append(draft["policy"]["controls"])
        fingerprints.add(draft["assessment"]["policy_fingerprint"])
    assert all(control == controls[0] for control in controls)
    assert len(fingerprints) == 9


async def test_preview_and_admission_reject_forged_invalid_or_expired_inputs(advisory_api, monkeypatch):
    client, discovery, coordinator, _, records, clock, *_ = advisory_api
    catalog = await discovery.catalog()
    record = records["xyz"]
    base = preview_request(catalog, record)
    for override, status, reason in (
        ({"identity": {**base["identity"], "network": "TESTNET"}}, 422, "NETWORK_MISMATCH"),
        ({"identity": {**base["identity"], "dex": "unlisted"}}, 422, "IDENTITY_MISMATCH"),
        ({"identity": {**base["identity"], "instrument_name": "other:GOLD"}}, 422, "CONFIGURATION_INVALID"),
        ({"catalog_fingerprint": "3" * 64}, 409, "CATALOG_FINGERPRINT_MISMATCH"),
        ({"advisory_snapshot_fingerprint": "4" * 64}, 503, "ADVISORY_UNAVAILABLE"),
        ({"family": "VERIFIED_COMMODITY"}, 422, "CONFIGURATION_INVALID"),
        ({"controls": {"amm_model": "UNSUPPORTED"}}, 422, "CONFIGURATION_INVALID"),
        ({"controls": {"controls_authority": "TESTNET"}}, 422, "CONFIGURATION_INVALID"),
        ({"controls": {"base_order_size": "NaN"}}, 422, "CONFIGURATION_INVALID"),
        ({"controls": {"base_order_size": "Infinity"}}, 422, "CONFIGURATION_INVALID"),
        ({"controls": {"base_order_size": 1}}, 422, "CONFIGURATION_INVALID"),
        ({"controls": {"levels_per_side": "2"}}, 422, "CONFIGURATION_INVALID"),
        ({"controls": {"concentration_upper_bps": "1"}}, 422, "CONFIGURATION_INVALID"),
        ({"controls": {"hard_inventory_limit_base": "1"}}, 422, "CONFIGURATION_INVALID"),
        ({"controls": {"total_liquidity": "0.01"}}, 422, "CONFIGURATION_INVALID"),
        ({"minimum_order_notional": "0"}, 422, "CONFIGURATION_INVALID"),
        ({"authority": "TESTNET"}, 422, "CONFIGURATION_INVALID"),
    ):
        response = await client.post(PREVIEW, json=base | override)
        assert (response.status_code, response.json()["reason"]) == (status, reason), response.text
        assert response.json()["binding"] is None

    clock[0] = utcnow() + timedelta(seconds=1)
    advisory = await client.post(ADVISORY, json={key: base[key] for key in ("identity", "catalog_fingerprint")} |
                                 {"operation": "DISCOVERY"})
    assert advisory.status_code == 200, advisory.text
    request = base | {"advisory_snapshot_fingerprint": advisory.json()["snapshot_fingerprint"]}
    draft = await client.post(PREVIEW, json=request)
    assert draft.status_code == 200, draft.text
    wire = draft.json()["policy"]
    payload = proposal_for(record, price="100", minimum_order_notional="20").model_dump(mode="json")
    for field, value in (("metadata_fingerprint", "5" * 64), ("execution_eligible", True),
                         ("authority", "TESTNET"), ("declared_at", "2031-01-01T00:00:00Z"),
                         ("simulated_reference_price", "101"), ("research_risk_fingerprint", "6" * 64)):
        changed = deepcopy(wire)
        changed[field] = value
        response = await client.post(URL + "/eligibility", json=payload | {"asset_amm_policy": changed})
        assert response.status_code in {409, 422} and response.json()["binding"] is None, response.text
    changed = deepcopy(wire)
    changed["hypothetical_accounting_unit"]["symbol"] = "USDC"
    invalid_unit = await client.post(URL + "/eligibility", json=payload | {"asset_amm_policy": changed})
    assert invalid_unit.status_code == 422 and invalid_unit.json()["binding"] is None

    snapshot, _ = coordinator.resolve_snapshot(request["advisory_snapshot_fingerprint"])
    monkeypatch.setattr(coordinator, "resolve_snapshot", lambda _: (snapshot, clock[0]))
    stale_advisory = await client.post(PREVIEW, json=request)
    assert stale_advisory.status_code == 503 and stale_advisory.json()["reason"] == "ADVISORY_STALE"
    clock[0] += timedelta(seconds=61)
    expired = await client.post(PREVIEW, json=request)
    assert expired.status_code == 503 and expired.json()["reason"] == "METADATA_STALE"
    discovery._expires = 0
    refresh = await discovery.catalog()
    assert refresh.catalog_fingerprint != catalog.catalog_fingerprint
    changed_catalog = await client.post(PREVIEW, json=request)
    assert changed_catalog.status_code == 409 and changed_catalog.json()["reason"] == "CATALOG_FINGERPRINT_MISMATCH"
