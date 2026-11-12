"""Two sequential PAPER legs inside one existing research admission."""
from decimal import localcontext

from app.simulation.market_profiles import MARKETS
from app.simulation.models import stable_fingerprint
from .aggregation import assemble_analysis
from .metrics import compare_metrics, compare_risk
from .models import (ConcentrationSelection, MarketStressEvidence,
    PortfolioStressRequest, STRESS_LIMITATIONS)
from .orchestration import execute_markets
from .scenarios import baseline_dataset, transform_dataset


def select_concentration(request, baseline, evidence):
    if request.scenario.scenario_type != "CONCENTRATION_STRESS":
        return None
    if baseline.temporal.classification != "MODELED_ALIGNED":
        raise ValueError("complete baseline concentration evidence unavailable")
    markets = tuple(s.market for s in request.config.scenarios)
    chosen = list(evidence)
    sequence = request.scenario.onset_frame  # frame before zero-based onset
    points = tuple(next(p for p in e.observations if p.sequence == sequence) for e in chosen)
    selection = ConcentrationSelection(market=markets[0], sequence=sequence, candidates=points,
        candidate_markets=markets, native_evidence_fingerprints=tuple(e.evidence_fingerprint for e in chosen))
    target = concentration_target(selection)
    if target not in request.scenario.selected_markets:
        raise ValueError("largest portfolio concentration is outside the selected stress markets")
    return selection.model_copy(update={"market": target})


def concentration_target(selection):
    if (len(selection.candidates) != len(selection.candidate_markets) or
            len(selection.candidates) != len(selection.native_evidence_fingerprints) or
            any(p.sequence != selection.sequence for p in selection.candidates)):
        raise ValueError("concentration candidate evidence mismatch")
    with localcontext() as ctx:
        ctx.prec = 80
        pairs = tuple(zip(selection.candidate_markets, selection.candidates))
        market, point = min(pairs, key=lambda v: (-abs(v[1].position_base * v[1].mark_price_quote), MARKETS.index(v[0])))
        if not point.position_base:
            raise ValueError("no nonzero baseline concentration position")
        return market


def prepared_datasets(request, selection):
    target, position = None, None
    if selection:
        target = selection.market
        position = selection.candidates[selection.candidate_markets.index(target)].position_base
    baseline, stressed = {}, {}
    for s in request.config.scenarios:
        baseline[s.market] = baseline_dataset(s)
        stressed[s.market] = transform_dataset(baseline[s.market], s, request.scenario,
            concentration_market=target, concentration_position=position)
    return baseline, stressed


def market_bindings(baseline, stressed):
    return tuple(MarketStressEvidence(market=b.market,
        market_profile_fingerprint=b.provenance.captured.market_profile_fingerprint,
        baseline_dataset_fingerprint=b.provenance.dataset_fingerprint,
        stressed_dataset_fingerprint=s.provenance.dataset_fingerprint,
        baseline_result_fingerprint=b.provenance.result_fingerprint,
        stressed_result_fingerprint=s.provenance.result_fingerprint,
        baseline_run_fingerprint=b.provenance.run_fingerprint,
        stressed_run_fingerprint=s.provenance.run_fingerprint)
        for b, s in zip(baseline.execution.markets, stressed.execution.markets, strict=True))


async def execute_stress(service, *, request, _presentation=None):
    # The worker uses the native 28-digit convention. Keep direct service calls
    # and dataset regeneration independent of an ambient caller context too.
    with localcontext() as ctx:
        ctx.prec = 28
        ctx.rounding = "ROUND_HALF_EVEN"
        return await _execute_stress(service, request=request, _presentation=_presentation)


async def _execute_stress(service, *, request, _presentation=None):
    request = PortfolioStressRequest.model_validate(request)
    config = request.config
    # Native baseline generation/execution remains exactly the existing path.
    receipts, observations = await execute_markets(service, config, collect_accounting=True)
    baseline = assemble_analysis(config, receipts, observations, request.risk_policy)
    selection = select_concentration(request, baseline, observations)
    _, datasets = prepared_datasets(request, selection)
    receipts, stressed_observations = await execute_markets(service, config,
        collect_accounting=True, _datasets=datasets)
    stressed = assemble_analysis(config, receipts, stressed_observations, request.risk_policy)
    if selection:
        # This proves the existing inventory was replayed before the shock;
        # neither positions nor accounting state are injected into the engine.
        for b, s in zip(observations, stressed_observations, strict=True):
            if (tuple(p for p in b.observations if p.sequence <= selection.sequence) !=
                    tuple(p for p in s.observations if p.sequence <= selection.sequence)):
                raise ValueError("concentration replay prefix differs from baseline")
    from .aggregation import assemble_stress
    result = assemble_stress(request, baseline, stressed, selection)
    return _presentation(result, observations, stressed_observations) if _presentation else result


def verify_stress_result(result):
    r, b, s = result.request, result.baseline, result.stressed
    if (result.limitations != STRESS_LIMITATIONS or result.request_fingerprint != stable_fingerprint(r) or
            result.scenario_fingerprint != r.scenario.fingerprint() or
            b.execution.config != r.config or s.execution.config != r.config or
            b.risk.policy != r.risk_policy or s.risk.policy != r.risk_policy):
        raise ValueError("stress configuration/provenance mismatch")
    selection = result.concentration_selection
    if (r.scenario.scenario_type == "CONCENTRATION_STRESS") != (selection is not None):
        raise ValueError("concentration selection missing or unexpected")
    if selection:
        clocks = {c.market: c for c in b.temporal.clocks}
        if (b.temporal.classification != "MODELED_ALIGNED" or s.temporal.classification != "MODELED_ALIGNED" or
                selection.sequence != r.scenario.onset_frame or selection.candidate_markets != tuple(m.market for m in r.config.scenarios) or
                selection.market not in r.scenario.selected_markets or
                selection.native_evidence_fingerprints != tuple(clocks[m].native_evidence_fingerprint for m in selection.candidate_markets) or
                selection.market != concentration_target(selection)):
            raise ValueError("invalid concentration selection")
        from datetime import timedelta
        from app.simulation.scenarios import DEFAULT_START
        if any(p.timestamp != DEFAULT_START + timedelta(seconds=selection.sequence - 1) for p in selection.candidates):
            raise ValueError("concentration observation timestamp mismatch")
        from .exposure import position_notional
        configs = {item.market: item for item in r.config.scenarios}
        for market, point in zip(selection.candidate_markets, selection.candidates):
            inputs = configs[market].captured.inputs()
            position_notional(market=market, base_currency=market, quote_currency="USDC",
                position_base=point.position_base, mark_price_quote=point.mark_price_quote,
                profile=inputs.market_profile)
            if point.equity_quote != inputs.simulation.initial_equity_quote + point.session_pnl_quote:
                raise ValueError("concentration native accounting projection mismatch")
    expected_baseline, expected_stressed = prepared_datasets(r, selection)
    for leg, datasets in ((b, expected_baseline), (s, expected_stressed)):
        for receipt in leg.execution.markets:
            if receipt.provenance.dataset_fingerprint != datasets[receipt.market].fingerprint:
                raise ValueError("stress dataset substitution or assumption mismatch")
    if (result.markets != market_bindings(b, s) or result.metrics != compare_metrics(b, s) or
            result.risk_transition != compare_risk(b, s)):
        raise ValueError("stress comparison projection mismatch")
