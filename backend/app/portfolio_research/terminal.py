"""Minimal terminal projection generated within the existing worker admission."""
from .aggregation import assemble_analysis, bounded_json
from .models import sealed
from .orchestration import execute_markets
from .charts import project_chart
from .terminal_models import TerminalRequest, TerminalResult, TerminalLeg, TerminalMarketSource
from app.simulation.models import stable_fingerprint


def project_leg(config, analysis, evidence, stress=None):
    markets = tuple(TerminalMarketSource(market=m.market,
        market_profile_fingerprint=m.provenance.captured.market_profile_fingerprint,
        dataset_fingerprint=m.provenance.dataset_fingerprint,
        run_fingerprint=m.provenance.run_fingerprint, result_fingerprint=m.provenance.result_fingerprint,
        accounting_fingerprint=m.accounting_fingerprint, receipt_fingerprint=m.receipt_fingerprint,
        execution_assumptions=m.execution_assumptions) for m in analysis.execution.markets)
    return TerminalLeg(analysis_fingerprint=analysis.evidence_fingerprint,
        bundle_fingerprint=analysis.execution.bundle_fingerprint,
        temporal=analysis.temporal, accounting=analysis.accounting, exposure=analysis.exposure,
        risk=analysis.risk, charts=project_chart(config, analysis, evidence, stress=stress), markets=markets)


async def terminal_portfolio_research(service, *, request):
    request = TerminalRequest.model_validate(request)

    def finish(baseline, observations, stressed=None, stressed_observations=None, original=None):
        result = sealed(TerminalResult, mode=request.mode, config_fingerprint=request.config_fingerprint,
            request_fingerprint=stable_fingerprint(request),
            source_result_fingerprint=original.evidence_fingerprint if original else baseline.evidence_fingerprint,
            scenario_fingerprint=request.scenario.fingerprint() if request.scenario else None,
            baseline=project_leg(request.config, baseline, observations, request.scenario),
            stressed=project_leg(request.config, stressed, stressed_observations, request.scenario) if stressed else None,
            metrics=original.metrics if original else None, risk_transition=original.risk_transition if original else None,
            limitations=(original or baseline).limitations + (
                "Charts are bounded observations of complete modeled native evidence, not full-resolution historical series.",
                "Chart fingerprints identify same-job sources, not cryptographic signatures or exchange attestations.",))
        bounded_json(result)
        return result

    if request.mode == "STRESS":
        from .stress import execute_stress
        return await execute_stress(service, request=request.stress_request(),
            _presentation=lambda original, b, s: finish(original.baseline, b, original.stressed, s, original))
    receipts, evidence = await execute_markets(service, request.config, collect_accounting=True)
    analysis = assemble_analysis(request.config, receipts, evidence, request.risk_policy)
    return finish(analysis, evidence)
