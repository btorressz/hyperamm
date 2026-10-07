# Reference Integrity Domain

The `references` package implements Phase 8 multi-source price evidence and consensus. Its job is to normalize independent/reference prices, track health/freshness/provenance, identify outliers, and produce the consensus consumed by the deterministic risk firewall.

## Provider hierarchy

```text
RedStone
    primary external oracle
    Live transport preferred
    public HTTP is fallback transport for the SAME provider vote

Hyperliquid oraclePx
    native oracle evidence

Kraken
    independent exchange reference

CoinGecko
    tertiary aggregate evidence

Hyperliquid mid / mark
    venue/perpetual evidence used in downstream deviation checks
```

CoinGecko does not become a core institutional quorum source, and RedStone HTTP does not count as a second RedStone vote.

## Files

| File | Responsibility |
|---|---|
| `models.py` | Provider IDs, transports, provider status, normalized evidence, consensus and deviation contracts. |
| `providers.py` | RedStone Live + HTTP fallback, Kraken, CoinGecko and supporting provider adapters/normalization. |
| `consensus.py` | Deterministic median/outlier/quorum policy and confidence classification. |
| `service.py` | Owns provider lifecycles, combines native Hyperliquid evidence with external evidence, versions snapshots and wakes strategy recomputation. |
| `__init__.py` | Public exports. |

## Consensus states

Typical confidence states are:

- `VERIFIED`
- `DEGRADED`
- `CONFLICTED`
- `INSUFFICIENT`

The core consensus uses RedStone, Hyperliquid native oracle and Kraken. Outliers and transport degradation affect confidence. RedStone public HTTP fallback conservatively prevents fully verified confidence.

## Connections

- Consumes normalized market/perp evidence from `market_data`.
- Supplies `ReferenceSnapshot` to Phase 9 agent evidence and Phase 8 `RiskFirewall`.
- Reference version/fingerprint are bound into `FinalQuoteAuthorization`.
- Phase 12 exposes provider state read-only.

## Authority boundary

Reference consensus is evidence authority, not order authority. It cannot submit/cancel orders; the risk firewall and final authorization decide whether strategy quotes may continue.
