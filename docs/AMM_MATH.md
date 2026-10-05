# HyperAMM AMM Mathematics

## Constant-product invariant

The virtual pool uses

\[
x y = k
\]

where `x` is virtual base reserve, `y` is virtual quote reserve, and `k` remains constant during a fee-free virtual swap. The marginal quote-per-base price is

\[
p = \frac{y}{x} = \frac{k}{x^2}.
\]

The reserves are mathematical state only. HyperAMM uses AMM mathematics to generate CLOB liquidity rather than settling swaps through an on-chain liquidity pool.

## Virtual swaps

For base input `Δx`,

\[
x' = x + \Delta x,\qquad y' = \frac{k}{x'},\qquad \Delta y_{out}=y-y'.
\]

For quote input `Δy`,

\[
y' = y + \Delta y,\qquad x' = \frac{k}{y'},\qquad \Delta x_{out}=x-x'.
\]

Zero, negative or non-finite reserves/trade quantities are rejected.

## Recentering

The live fair-value anchor for Phases 1–4 is

\[
f = \frac{bid + ask}{2}.
\]

To recenter while preserving `k`, HyperAMM solves

\[
x_f=\sqrt{\frac{k}{f}},\qquad y_f=\sqrt{k f}.
\]

Thus `y_f / x_f = f` and `x_f y_f = k`.

## Curve sampling and discretization

For `N` levels and a maximum distance `D` bps, level `i` uses deterministic distance

\[
d_i = D\frac{i+1}{N}.
\]

Target prices are `f(1-d/10000)` on the bid side and `f(1+d/10000)` on the ask side. The corresponding constant-product reserve point is recovered with `sqrt(k / p)`. Prices are then normalized to executable ticks: bids round down, asks round up. Sizes round down to configured size precision so normalization never creates extra exposure.

## Concentrated liquidity

Concentrated mode is a policy over the same virtual curve. A normalized distance `z` inside the configured lower/upper range receives raw weight

\[
w_i^{raw}=\frac{1}{1+c z_i^2}
\]

where `c` is the concentration factor. Final weights are

\[
w_i=\frac{\Delta x_i w_i^{raw}}{\sum_j \Delta x_j w_j^{raw}}.
\]

Increasing `c` therefore shifts a larger share of fixed total liquidity toward levels nearest fair value. Unit tests assert this behavior and that weights sum to one.

## Phase 4.1: reserve movement determines CLOB size

Each side independently starts at the fair-value reserve `x0 = sqrt(k/f)`.
For successive target prices, `xi = sqrt(k/pi)`, the typed curve point retains
`price`, `target_base`, `distance_bps`, `cumulative_base = |xi-x0|`, and
`incremental_base = cumulative_i - cumulative_(i-1) = |xi-x_(i-1)|`.
Sampling rejects non-finite, non-positive or non-monotonic movement. Cumulative
movement increases outward on both sides; incremental sizes need not increase
on both sides (ask increments decrease for equally spaced prices).

CONSTANT_PRODUCT uses `wi = incremental_i / sum(incremental)` independently
for bids and asks. CONCENTRATED multiplies each incremental movement by the
existing concentration factor `1/(1+c*z_i^2)`, then normalizes the products.
Thus concentration modifies the natural AMM profile instead of replacing it.
A zero concentration factor recovers the constant-product distribution.

`total_liquidity` remains a **per-side base-asset budget**, including the baseline
order sizes, not an aggregate bid+ask budget. With `N` levels and normalized
baseline `b`, each raw order size is `b + (total_liquidity - N*b)*wi`.
The minimum baseline is rounded **up** to size precision before subtracting its
allocation; an insufficient budget is rejected. Final sizes round **down**.
No emitted size is zero, the baseline remains enforced, and neither side
exceeds its budget; rounding dust is left unallocated. Bids round down and asks
round up to ticks, preserving an uncrossed ladder.

Changing only `k` may scale every raw reserve delta by the same `sqrt(k)` factor.
Normalizing to a fixed per-side budget cancels that common factor. Acceptance
therefore verifies successive reserve deltas and their sizing weights directly,
not an incorrect requirement that changing `k` must change relative sizes.


## Phase 5 inventory policy

The Phase 4.1 AMM curve remains the neutral mathematical ladder. Phase 5 does not change the constant-product invariant or reserve-delta weights.

Signed inventory deviation and normal-skew ratio:

```text
d = position_base - target_base
q = d / soft_limit
r = clamp(q, -1, 1)
```

Reservation-price shift:

```text
shift_bps = -r * max_inventory_price_skew_bps
reservation = fair * (1 + shift_bps / 10000)
```

Positive/long inventory lowers the strategy reservation price; negative/short inventory raises it. Fair value remains market state and is never replaced by reservation price.

Side-size scaling:

```text
m_bid = clamp(1 - strength * r, m_min, m_max)
m_ask = clamp(1 + strength * r, m_min, m_max)
```

The multiplier applies to the AMM-derived excess above the existing baseline:

```text
size_final = base_order_size
           + (size_neutral - base_order_size) * m_side
```

This preserves the reserve-delta-derived variable profile while keeping the Phase 4.1 baseline floor, up to deterministic size normalization. Hard inventory limits are separate from the normal skew clamp. At or beyond the long hard bound the desired BID side is absent; at or beyond the short hard bound the desired ASK side is absent.

## Phase 6 market adaptation math

Phase 6 does not change the constant-product invariant, reserve-delta liquidity, concentration policy, or Phase 5 inventory formulas.

### Realized volatility

The input is the normalized mid price only. For the trailing accepted unique observations:

```text
r_t = ln(P_t / P_(t-1))
sigma = sqrt(mean(r_t^2))
```

Prices enter as validated positive finite `Decimal` values. The logarithm is isolated through Python `math.log`; the finite result is converted back with `Decimal(str(result))`. The statistic is per observation and is not annualized.

Default thresholds are in the same units:

```text
volatility_low_threshold  = 0.0002  # 0.02%
volatility_high_threshold = 0.0020  # 0.20%
```

Bounded score:

```text
sigma <= low  -> score = 0
sigma >= high -> score = 1
otherwise     -> score = (sigma - low) / (high - low)
```

### L2 imbalance

Using the configured top N normalized levels, or all valid available levels if fewer exist:

```text
bid_depth = sum(top-N bid base sizes)
ask_depth = sum(top-N ask base sizes)

imbalance = (bid_depth - ask_depth)
            / (bid_depth + ask_depth)
```

Depth is base-asset size, not price/notional weighted. Empty/crossed/invalid books and zero selected depth are invalid state.

### Spread multiplier

Phase 6 is widening-only:

```text
spread_multiplier =
    1
    + volatility_spread_strength * volatility_score
    + imbalance_spread_strength * abs(book_imbalance)

spread_multiplier =
    clamp(spread_multiplier, min_spread_multiplier, max_spread_multiplier)
```

The default minimum is 1.0. Final distances are expanded around the Phase 5 reservation center, then price tick normalization is reapplied. `distance_bps` is recomputed from the actual final price versus fair value so downstream risk sees the true exposure.

### Size/depth multipliers

```text
global_size_multiplier =
    clamp(
        1 - volatility_size_strength * volatility_score,
        min_market_size_multiplier,
        1,
    )

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

bid_market_multiplier = max(min_market_size_multiplier, global_size_multiplier * bid_imbalance_multiplier)
ask_market_multiplier = max(min_market_size_multiplier, global_size_multiplier * ask_imbalance_multiplier)
```

As in Phase 5, `base_order_size` remains the baseline floor:

```text
size_final =
    base_order_size
    + (size_phase5 - base_order_size) * market_side_multiplier
```

A Phase 5 hard-limit-suppressed side has no quotes to transform and remains absent.
