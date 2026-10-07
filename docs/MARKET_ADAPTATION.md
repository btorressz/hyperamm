# HyperAMM Phase 6 — Market Adaptation

Phase 6 adds deterministic volatility and L2 order-book-imbalance adaptation after the accepted Phase 5 inventory policy and before deterministic risk/reconciliation.

## Inputs

Phase 6 uses only normalized market data already present in HyperAMM:

- normalized mid price for realized volatility;
- normalized Hyperliquid/demo L2 base sizes for imbalance;
- exchange timestamp and book sequence for observation identity.

It does not use funding, mark/oracle basis, open interest, liquidation feeds, external oracle providers, cross-venue prices, ML, randomness, or AI agents.

## Rolling history

`MarketPriceHistory` stores at most 1,000 observations in memory. Strategy configuration selects the trailing `volatility_window_samples` used by the estimator.

An observation is accepted only when the snapshot is fresh, has a normalized book, and has a positive finite mid price. Repeated sequence numbers or repeated exchange timestamps are ignored. Older timestamps are ignored. History is cleared when the configured market or feed mode changes.

Default strategy window:

```text
volatility_window_samples = 60
volatility_min_samples = 10
```

The sample count is the number of price observations. Ten observations produce nine log returns.

## Realized volatility

For consecutive normalized mid prices:

```text
r_t = ln(P_t / P_(t-1))
sigma = sqrt(mean(r_t^2))
```

This is RMS log return **per accepted normalized price observation**. It is not
annualized and is not inherently time-normalized: timestamps control acceptance,
ordering and deduplication, but do not weight returns or divide by elapsed time.
There is no fixed-time resampling or interpolation. Regular, irregular, bursty
and sparse timestamps yield the same sigma for the same accepted price sequence.
Distinct timestamps/sequences with unchanged prices count as observations with
zero returns. Repeated identities do not count, even during a burst.

Feed cadence therefore changes economic interpretation: a 60-observation window
can span milliseconds or hours. Thresholds must be calibrated against the intended
feed's accepted observation cadence and market; these defaults are heuristic
settings, not empirically calibrated estimates of volatility per second/hour/day.

Input prices and ratios must be finite and positive. Ratios are computed in
Decimal using the caller's context (normally 28 significant digits). Decimal
arithmetic failures/underflow and ratios outside the normal finite binary64
range (`sys.float_info.min` through `sys.float_info.max`, approximately
2.225e-308 through 1.798e308) are rejected before conversion. This deliberately
rejects subnormal ratios rather than allowing conversion underflow or lost range.
Absolute positive Decimal prices may be much larger/smaller than float can hold
when their ratio remains representable; prices themselves are never converted.

Only this descriptive estimator uses float for `math.log`, squared returns,
`math.fsum`/mean and `math.sqrt`. Each stage checks finite/nonnegative results and
underflow; failures raise `ValueError` into the existing fail-closed quote path.
The result returns through `Decimal(str(sigma))`. Financial authority arithmetic
(prices, sizes, scores, quotes, risk and accounting) remains Decimal.

Binary64 provides about 15–16 significant digits, not exact Decimal logarithms.
Returns from ratios sufficiently close to 1 (roughly machine epsilon, 2.22e-16)
may round to zero. Tests compare ordinary numerical results with 1e-12 relative /
1e-15 absolute tolerance; this is a verification tolerance, not a score epsilon.
Threshold comparisons use the computed Decimal exactly, without rounding bands.
Inputs closer to a threshold than estimator precision are not promised the same
classification across math-library implementations; identical inputs in the same
runtime remain deterministic.

Default thresholds are in the same per-observation units:

```text
low  = 0.0002  # RMS log return per observation: about 0.02% / 2 bps
high = 0.0020  # RMS log return per observation: about 0.20% / 20 bps
```

The bounded score is:

```text
sigma <= low  -> 0
sigma >= high -> 1
otherwise     -> (sigma - low) / (high - low)
```

These percentages are small-return approximations, not simple-return standard
deviation. For a constant upward step, the exact simple return is `exp(sigma)-1`.
The RMS is uncentered: steady drift contributes rather than being subtracted.
Low is inclusive (QUIET); just above low is NORMAL. High is inclusive (score 1,
HIGH_VOLATILITY), and above high remains saturated. HIGH_VOLATILITY already starts
at score 0.85, not only at the high threshold.

## Warmup

Before `volatility_min_samples` observations exist:

```text
volatility_ready = false
realized_volatility = null
volatility_score = 0
spread_multiplier = 1
global_size_multiplier = 1
bid/ask imbalance multipliers = 1
regime = WARMING_UP
```

The measured L2 depths and imbalance remain visible for explainability, but they do not alter quotes during volatility warmup. Warmup is not a fail-closed condition when market data itself is otherwise valid.

## Top-N L2 imbalance

For the configured number of levels, using fewer valid levels when the book is shallower:

```text
bid_depth = sum(top N bid base sizes)
ask_depth = sum(top N ask base sizes)

book_imbalance =
    (bid_depth - ask_depth)
    / (bid_depth + ask_depth)
```

The result is bounded to `[-1,+1]` by construction.

Interpretation:

```text
positive -> BID_HEAVY
near zero -> BALANCED
negative -> ASK_HEAVY
```

Phase 6 uses base-size depth only. It does not use dollar-weighted or price-weighted imbalance.

An empty/crossed/malformed book, invalid/non-finite level data, or zero selected depth is invalid Phase 6 state and follows existing fail-closed quote invalidation.

## Spread adaptation

When enabled and volatility is ready:

```text
spread_multiplier =
    1
    + volatility_spread_strength * volatility_score
    + imbalance_spread_strength * abs(book_imbalance)

spread_multiplier =
    clamp(
        spread_multiplier,
        min_spread_multiplier,
        max_spread_multiplier,
    )
```

Phase 6 requires `min_spread_multiplier >= 1`, so the first implementation is widening-only.

The center is the Phase 5 reservation price. Fair value and reservation price remain separate state. Each surviving Phase 5 quote's distance from the reservation center is multiplied by `spread_multiplier`, then normal tick normalization is reapplied.

The final `distance_bps` is recomputed from the actual final quote price versus fair value so deterministic risk validates the real result.

## Size/depth adaptation

Global volatility size reduction:

```text
global_size_multiplier =
    clamp(
        1 - volatility_size_strength * volatility_score,
        min_market_size_multiplier,
        1,
    )
```

Side-specific conservative imbalance reductions:

```text
bid_imbalance_multiplier =
    clamp(
        1 - imbalance_size_strength * max(book_imbalance, 0),
        min_market_size_multiplier,
        1,
    )

ask_imbalance_multiplier =
    clamp(
        1 - imbalance_size_strength * max(-book_imbalance, 0),
        min_market_size_multiplier,
        1,
    )
```

Final market side multipliers are the global multiplier times the side-specific imbalance multiplier, then clamped no lower than `min_market_size_multiplier` so combined reductions cannot bypass the configured Phase 6 floor.

Phase 6 preserves the Phase 5 baseline:

```text
final_size =
    base_order_size
    + (phase5_size - base_order_size) * market_side_multiplier
```

Only variable liquidity above the baseline is reduced. A side removed by Phase 5 hard inventory authority is not present and cannot be restored by Phase 6.

## Deterministic labels

After warmup, volatility labels depend only on the bounded score:

```text
QUIET           score = 0
NORMAL          0 < score < 0.50
ELEVATED        0.50 <= score < 0.85
HIGH_VOLATILITY 0.85 <= score <= 1
```

Imbalance labels depend only on normalized imbalance:

```text
BALANCED
BID_HEAVY
ASK_HEAVY
```

These labels are explainability state, not AI predictions or confidence scores.

## Versioning and authority

Every unique accepted market observation increments the bounded history version.

Generated adaptive quotes bind to:

- the current Phase 5 inventory version;
- the current Phase 6 market/adaptation version.

Before order transmission, final execution authority revalidates the normalized market snapshot and ensures neither dependency version changed. If either changed, transmission is rejected and the existing strategy loop recomputes.

The shared execution lock, kill switch, risk checks, and KEEP / CREATE / REPLACE / CANCEL reconciler remain authoritative.

## API and terminal

`GET /api/v1/market-adaptation` exposes normalized Phase 6 decision state.

The decision includes `volatility_sampling = PER_ACCEPTED_OBSERVATION` and the
configuration schema describes thresholds in the same per-observation RMS units.
Phase 9 copies this sigma/score/regime into agent evidence; its Regime Agent
does not recalculate volatility. Phase 10 uses the same QuoteEngine /
MarketAdaptationPolicy and evidence builder for accepted simulation frames.

`/ws/terminal` includes the same `market_adaptation` block.

Quote metadata preserves:

```text
neutral AMM
-> inventory-adjusted price/size
-> pre-market-adaptation price/size
-> final market-adapted price/size
```

The React terminal displays volatility/warmup, score/regime, bid/ask depth, book imbalance/state, spread multiplier, global size multiplier, and final bid/ask market multipliers.

## Failure behavior

Volatility warmup is neutral rather than fail-closed.

Invalid Phase 6 mathematics or market state after normal validation follows the existing Phase 4.1 failure path: clear desired quotes, cancel strategy orders under the shared execution lock, surface degraded/halted state, and never silently reuse a previous adaptive decision.

## Scope boundary

Phase 6 does not implement Phase 7 perpetual/funding context, Phase 8 oracle protection/risk quorum, external oracle providers, mainnet execution, optimization solvers, or AI/LLM agents.
