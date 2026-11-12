import itertools
from decimal import Decimal

import pytest

from app.portfolio_research.models import PortfolioAnalysisResult, PortfolioAnalysisRequest, sealed
from app.simulation.service import SimulationService
from app.simulation.models import stable_fingerprint
from phase173_fixtures import native173, request_for, reseal
from phase172_fixtures import portfolio, request_for as run_request


async def test_original_run_receipts_and_full_result_fingerprints_preserved():
    p = portfolio(frames=8, scenario="FLASH_MOVE")
    service = SimulationService()
    original = await service.run_portfolio_research(request=run_request(p))
    result = await service.analyze_portfolio_research(request=request_for(p))
    assert original == result.execution
    assert [r.provenance.result_fingerprint for r in original.markets] == [r.provenance.result_fingerprint for r in result.execution.markets]


async def test_all_request_permutations_exact_reproducibility():
    results = []
    for markets in itertools.permutations(("BTC", "ETH", "SOL")):
        results.append(await SimulationService().analyze_portfolio_research(request=request_for(portfolio(markets))))
    assert all(r == results[0] for r in results)


@pytest.mark.parametrize("domain,field,value", [
    ("accounting", "equity_quote", "12345"), ("accounting", "reserve_quote", "0"),
    ("exposure", "gross_exposure_quote", "0"), ("risk", "decision", "NORMAL"),
    ("temporal", "classification", "FINAL_ONLY"),
    ("temporal", "historical_market_synchronization_verified", True)])
def test_tampered_analysis_projections_rejected_even_with_new_envelope_hash(native173, domain, field, value):
    *_, r = native173
    raw = r.model_dump(mode="json")
    raw[domain][field] = value
    raw[domain]["evidence_fingerprint"] = stable_fingerprint({k: v for k, v in raw[domain].items() if k != "evidence_fingerprint"})
    raw["evidence_fingerprint"] = stable_fingerprint({k: v for k, v in raw.items() if k != "evidence_fingerprint"})
    with pytest.raises(ValueError): PortfolioAnalysisResult.model_validate(raw)


@pytest.mark.parametrize("field,value", [("mark_price_quote", Decimal("60001")),
    ("position_base", Decimal("123")), ("source_run_fingerprint", "0" * 64),
    ("market_profile_fingerprint", "0" * 64), ("base_currency", "ETH")])
def test_rehashed_modified_exposure_still_rejected(native173, field, value):
    *_, r = native173
    ps = list(r.exposure.positions)
    ps[0] = ps[0].model_copy(update={field: value})
    x = reseal(r.exposure, positions=tuple(ps))
    with pytest.raises(ValueError): reseal(r, exposure=x)


def test_nested_copied_models_and_swapped_receipts_revalidate(native173):
    *_, r = native173
    for bad in (r.model_copy(update={"authority": "LIVE"}),
                r.model_copy(update={"risk": r.risk.model_copy(update={"decision": "NORMAL"})}),
                r.model_copy(update={"execution": r.execution.model_copy(update={"markets": r.execution.markets[::-1]})})):
        with pytest.raises(ValueError): PortfolioAnalysisResult.model_validate(bad)


def test_client_cannot_supply_results_or_forged_configuration_fingerprints(native173):
    p, _, _, r = native173
    body = request_for(p).model_dump(mode="json")
    for extra in ({"execution": r.execution.model_dump(mode="json")}, {"accounting": r.accounting.model_dump(mode="json")},
                  {"config_fingerprint": "0" * 64}):
        with pytest.raises(ValueError): PortfolioAnalysisRequest.model_validate({**body, **extra})


def test_rehashed_source_timestamp_and_risk_configuration_tampering_rejected(native173):
    *_, r = native173
    from datetime import timedelta
    clocks = list(r.temporal.clocks)
    clocks[0] = reseal(clocks[0], final_at=clocks[0].final_at + timedelta(seconds=1))
    changed = reseal(r.temporal, clocks=tuple(clocks))
    with pytest.raises(ValueError): reseal(r, temporal=changed)
    changed_risk = reseal(r.risk, risk_configuration_fingerprint="0" * 64)
    with pytest.raises(ValueError): reseal(r, risk=changed_risk)


async def test_changed_allocations_and_limits_change_identity():
    from phase171a_fixtures import config
    from app.portfolio_research.models import PortfolioResearchConfig
    p = config()
    first = await SimulationService().analyze_portfolio_research(request=request_for(p))
    allocation = config(amounts=("41000", "34000", "20000"))
    changed = await SimulationService().analyze_portfolio_research(request=request_for(allocation))
    assert first.evidence_fingerprint != changed.evidence_fingerprint
    raw = p.model_dump()
    raw["risk_limits"]["max_session_loss_quote"] = "9000"
    changed = await SimulationService().analyze_portfolio_research(request=request_for(PortfolioResearchConfig.model_validate(raw)))
    assert first.risk.risk_configuration_fingerprint != changed.risk.risk_configuration_fingerprint
    assert first.execution.markets[0].provenance.result_fingerprint == changed.execution.markets[0].provenance.result_fingerprint


async def test_changed_execution_and_source_assumptions_change_analysis_identity():
    from app.research_replay.comparison import ComparisonConfigSnapshot
    from app.portfolio_research.models import PortfolioResearchConfig
    p = portfolio(("BTC",))
    r = await SimulationService().analyze_portfolio_research(request=request_for(p))
    for kind in ("execution", "source"):
        raw = p.model_dump()
        s = raw["scenarios"][0]
        payload = ComparisonConfigSnapshot.model_validate(s["captured"]).inputs().model_dump(mode="json")
        if kind == "execution": payload["simulation"]["execution"]["mode"] = "MODELED_CROSSING"
        else:
            from app.simulation.market_profiles import ResearchPerpMarketMetadata, profile
            original = payload["market_profile"]
            payload["market_profile"] = profile(ResearchPerpMarketMetadata(market="BTC", sz_decimals=original["sz_decimals"],
                metadata_status="DEMO_PROFILE", metadata_source="CHANGED_FIXTURE_SOURCE")).model_dump(mode="json")
        s["captured"] = ComparisonConfigSnapshot.from_payload(payload)
        changed = await SimulationService().analyze_portfolio_research(request=request_for(PortfolioResearchConfig.model_validate(raw)))
        assert changed.evidence_fingerprint != r.evidence_fingerprint
        assert changed.execution.markets[0].provenance.run_fingerprint != r.execution.markets[0].provenance.run_fingerprint
