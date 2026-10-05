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

Let signed inventory deviation be

[
d = position_{base} - target_{base}
]

and define the monitoring ratio

[
q = d / soft_limit.
]

Normal skew uses the bounded ratio

[
r = clamp(q,-1,1).
]

The bounded reservation-price shift is

[
shift_{bps} = -r \cdot max_inventory_price_skew_{bps}
]

and

[
reservation = fair \cdot (1 + shift_{bps}/10000).
]

Positive/long inventory therefore lowers the strategy reservation price; negative/short inventory raises it. Fair value remains market state and is never replaced by reservation price.

Side-size scaling is

[
m_{bid}=clamp(1-strength\cdot r,m_{min},m_{max})
]

[
m_{ask}=clamp(1+strength\cdot r,m_{min},m_{max}).
]

The multiplier applies to the AMM-derived excess above the existing baseline:

[
size_{final}=b+(size_{neutral}-b)m_{side}
]

where (b) is `base_order_size`. This preserves the reserve-delta-derived variable profile while keeping the Phase 4.1 baseline floor, up to deterministic size normalization. Prices are tick-normalized and constrained so bids remain below fair and asks above fair; final bid/ask ordering must remain uncrossed.

Hard inventory limits are separate from the normal skew clamp. At or beyond the long hard bound the desired BID side is absent; at or beyond the short hard bound the desired ASK side is absent. This suppression remains safety-authoritative even if normal inventory skew is disabled.


## Phase 6 market adaptation math

Phase 6 does not change the constant-product invariant, reserve-delta liquidity, concentration policy, or Phase 5 inventory formulas.

### Realized volatility

The input is the normalized mid price only. For the last `N` accepted unique observations:

[
r_t = ln(P_t/P_{t-1})
]

and HyperAMM uses per-observation RMS log-return volatility:

[
sigma = sqrt{rac{1}{n}sum_{t=1}^{n}r_t^2}.
]

Prices enter as validated positive finite `Decimal` values. The logarithm is isolated through Python floating-point `math.log`; the finite result is converted back with `Decimal(str(value))`. The statistic is not annualized. Therefore the configured default thresholds are per-observation log-return units: `0.0002` (0.02%) low and `0.0020` (0.20%) high.

For (sigma) between configured `low` and `high`:

[
volatilityScore = rac{sigma-low}{high-low}
]

with values below/above the thresholds clamped to 0/1.

### L2 imbalance

Using the top configured (N) normalized levels, or all available valid levels if fewer exist:

[
bidDepth=sum size_{bid}
]

[
askDepth=sum size_{ask}
]

[
imbalance=rac{bidDepth-askDepth}{bidDepth+askDepth}.
]

Depth is base-asset size, not price/notional weighted. Empty/crossed/invalid books and zero selected depth are invalid state.

### Spread multiplier

Phase 6 is widening-only:

[
m_{spread}=clamp(
1+s_v,volatilityScore+s_i,|imbalance|,
m_{spread,min},
m_{spread,max}
).
]

The default minimum is 1.0. Final distances are expanded around the Phase 5 reservation center, then price tick normalization is reapplied. Quote `distance_bps` is recomputed from the actual final price versus market fair value so downstream risk sees the true exposure.

### Size/depth multipliers

Global volatility reduction is:

[
m_{global}=clamp(1-z_v,volatilityScore,m_{size,min},1).
]

Conservative side imbalance reductions are:

[
m_{bid,imb}=clamp(1-z_imax(imbalance,0),m_{size,min},1)
]

[
m_{ask,imb}=clamp(1-z_imax(-imbalance,0),m_{size,min},1).
]

The final side market multipliers are (m_{global}m_{side,imb}).

As in Phase 5, `base_order_size` remains the baseline floor. Phase 6 scales only variable liquidity above it:

[
size_{final}=b+(size_{phase5}-b)m_{market}.
]

A Phase 5 hard-limit-suppressed side has no quotes to transform and remains absent.
