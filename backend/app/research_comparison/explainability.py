"""Deterministic completeness, never model confidence or financial advice."""
from .models import ComparisonExplainability

LIMITATIONS = (
    'Different economic contexts and timestamps; descriptive only, not a time-matched historical replay.',
    'Client-supplied research evidence is structurally validated, not independently authenticated; hashes do not prove execution.',
    'One native venue source; no independent reference quorum or consensus.',
    'Native perpetual event time is unknown; L2 and context are independently acquired.',
    'Observed price differences do not establish expected future returns.',
    'Venue spread does not establish executable strategy spread capture or historical slippage.',
    'Native funding observations are not simulated settled funding payments.',
    'Visible depth does not guarantee executable liquidity, fill probability or queue priority.',
    'PAPER PnL is hypothetical; observed data did not generate the completed research fills.',
    'Evidence completeness does not predict profitability or grant trading eligibility.',
)


def explain(metrics):
    available = tuple(x.metric_name for x in metrics if x.comparison_status in ('COMPARABLE', 'PARTIAL'))
    missing = tuple(x.metric_name for x in metrics if x.metric_name not in available)
    complete = all(x.comparison_status in ('COMPARABLE', 'PARTIAL') for x in metrics)
    status = 'COMPLETE_FOR_SUPPORTED_METRICS' if complete else 'PARTIAL' if available else 'UNAVAILABLE'
    if not available and any(x.comparison_status == 'NOT_COMPARABLE' for x in metrics):
        status = 'INSUFFICIENT'
    return ComparisonExplainability(completeness=status, available_metrics=available, missing_metrics=missing,
        statements=tuple(f'{x.metric_name}: {x.reason}' for x in metrics))
