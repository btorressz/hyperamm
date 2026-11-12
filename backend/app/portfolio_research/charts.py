"""Same-job native projection; bounded sampling never supplies missing history."""
from decimal import Decimal, localcontext
from app.simulation.models import stable_fingerprint
from .config import portfolio_ratio
from .models import sealed
from .terminal_models import ChartPoint, ChartEvidence
from .temporal import evaluate_temporal


def sample_indices(points, *, context=(), thresholds=(), limit=120):
    """Keep endpoints, global extrema, shock context and drawdown risk crossings.

    Local extrema are retained per deterministic bucket. If mandatory context
    alone cannot fit, reject chart eligibility instead of dropping evidence.
    """
    n = len(points)
    required = {0, n - 1} | {i for i in context if 0 <= i < n}
    fields = ("equity_quote", "pnl_quote", "drawdown_fraction")
    for field in fields:
        required.add(min(range(n), key=lambda i: getattr(points[i], field)))
        required.add(max(range(n), key=lambda i: getattr(points[i], field)))
    for threshold in thresholds:
        for i in range(1, n):
            if (points[i - 1].drawdown_fraction >= threshold) != (points[i].drawdown_fraction >= threshold):
                required.update((i - 1, i))
    if len(required) > limit:
        raise ValueError("MATERIAL_CONTEXT_EXCEEDS_CHART_BOUND")
    if n <= limit:
        return tuple(range(n))
    buckets = max(0, (limit - len(required)) // 6)
    selected = set(required)
    for b in range(buckets):
        indices = range(b * n // buckets, (b + 1) * n // buckets)
        for field in fields:
            selected.add(min(indices, key=lambda i: getattr(points[i], field)))
            selected.add(max(indices, key=lambda i: getattr(points[i], field)))
    # Spend spare slots on evenly spaced observations; no interpolation.
    for i in (i * (n - 1) // (limit - 1) for i in range(limit)):
        if len(selected) >= limit:
            break
        selected.add(i)
    return tuple(sorted(selected))


def project_chart(config, analysis, evidence, *, stress=None):
    temporal = evaluate_temporal(analysis.execution.markets, evidence)
    if temporal != analysis.temporal:
        raise ValueError("chart native timeline differs from analysis")
    bindings = dict(analysis_fingerprint=analysis.evidence_fingerprint,
        accounting_fingerprint=analysis.accounting.evidence_fingerprint,
        temporal_fingerprint=temporal.evidence_fingerprint,
        native_evidence_fingerprints=tuple(e.evidence_fingerprint for e in evidence))
    if temporal.classification != "MODELED_ALIGNED":
        return sealed(ChartEvidence, **bindings, status="UNAVAILABLE", reason=temporal.classification,
            source_count=0, sampled=False, equity_series_fingerprint=None, points=())
    with localcontext() as ctx:
        ctx.prec = 80
        initial = config.budget.total_equity_quote
        peak = initial
        points, curve = [], []
        for rows in zip(*(e.observations for e in evidence), strict=True):
            if len({(p.sequence, p.timestamp) for p in rows}) != 1:
                raise ValueError("chart sequence or timestamp mismatch")
            equity = config.unallocated_reserve_quote + sum((p.equity_quote for p in rows), Decimal(0))
            peak = max(peak, equity)
            point = ChartPoint(sequence=rows[0].sequence, timestamp=rows[0].timestamp,
                equity_quote=equity, pnl_quote=equity-initial,
                drawdown_fraction=portfolio_ratio(max(Decimal(0), peak-equity), peak))
            points.append(point)
            curve.append((point.timestamp, equity))
        identity = stable_fingerprint({"initial_equity": initial, "curve": curve})
        if (analysis.accounting.drawdown is None or identity != analysis.accounting.drawdown.equity_series_fingerprint or
                points[-1].equity_quote != analysis.accounting.equity_quote or
                points[-1].pnl_quote != analysis.accounting.pnl_quote):
            raise ValueError("chart accounting fingerprint or endpoint mismatch")
        context = set()
        if stress:
            lag = stress.assumptions.propagation_lag_frames or 0
            for offset in (0, lag):
                for event in (stress.onset_frame + offset, stress.onset_frame + offset + stress.duration_frames):
                    context.update((event - 1, event, event + 1))
        ceiling = config.risk_limits.max_drawdown_fraction
        policy = analysis.risk.policy
        try:
            indices = sample_indices(points, context=context,
                thresholds=(ceiling * policy.warning_ratio, ceiling * policy.reduction_ratio, ceiling))
        except ValueError:
            return sealed(ChartEvidence, **bindings, status="UNAVAILABLE", reason="MATERIAL_CONTEXT_EXCEEDS_CHART_BOUND",
                source_count=len(points), sampled=False, equity_series_fingerprint=identity, points=())
        return sealed(ChartEvidence, **bindings, status="AVAILABLE", reason="COMPLETE_NATIVE_MODELED_EVIDENCE",
            source_count=len(points), sampled=len(indices) < len(points), equity_series_fingerprint=identity,
            points=tuple(points[i] for i in indices))
