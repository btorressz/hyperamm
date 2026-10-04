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
w_i=\frac{w_i^{raw}}{\sum_j w_j^{raw}}.
\]

Increasing `c` therefore shifts a larger share of fixed total liquidity toward levels nearest fair value. Unit tests assert this behavior and that weights sum to one.
