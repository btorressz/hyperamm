# Phase 18.5B–D asset-aware AMM acceptance

Phase 18.5B–D builds on PR #96 at
`6325c1e77ce787b937c14486d39df9d863e9a0a8`. The Phase 18.5A contract suite
passed 41 tests on that commit before integration. PR #95 is the economic
compatibility baseline. [PR #96](https://github.com/btorressz/hyperamm/pull/96)
· [Phase 18.4 acceptance](PHASE18_4_FINAL_ACCEPTANCE.md)

## Implementation

- **Reuse.** Both AMM curves, virtual reserves and recentering, the quote compiler,
  inventory and market adaptation, perpetual context, discovery, scenarios,
  Phase 18.3 financial models, the local PAPER worker, accounting, the Risk
  Firewall and final authorization.
- **Enhance.** The existing Generalized PAPER contracts, admission, preflight
  and executable-quote normalization accept an optional policy. The API and
  advisory coordinator resolve published provenance and pass current evidence
  to the existing worker.
- **Add.** `backend/app/amm/asset_policy.py` maps the Phase 18.5A declaration
  into a validated copy of `StrategyConfig`. The Phase 18.5B–D tests cover the
  mapping, existing adaptation policies and PAPER integration.

| Files | Change |
| --- | --- |
| `backend/app/amm/asset_policy.py` | Pure mapping from the immutable declaration and qualified discovery metadata. |
| `backend/app/simulation/generalized_market_profiles.py`, `engine.py` | Optional binding, feasibility, worker revalidation and quote bounds. |
| `backend/app/api/market_universe.py`, `backend/app/agents/advisory_coordinator.py`, `market_eligibility.py` | Resolve server-owned advisory evidence and pass it through existing admission. |
| `backend/tests/test_phase185{b_asset_mapping,c_asset_adaptation,d_asset_paper}.py` | Focused Phase 18.5B–D checks. |
| Architecture, changelog and this record | Behavior, verification and handoff. |

## Mapping and quote feasibility

The mapper checks the canonical market, including network and DEX namespace,
matched metadata and a synthetic PAPER baseline. It maps the declared controls
into the existing strategy while preserving other baseline settings. Reserve
quantities are in base and hypothetical quote units. They define the curve's
invariant, and the existing engine recenters the pool on the synthetic frame
reference. The existing quote compiler validates the level count, distance,
minimum lot, per-side budget and concentration settings.

The discovered `szDecimals` sets the quantity lot and internal decimal grid.
The declared base order size must be a positive whole-lot multiple. Executable
bid prices round down and asks round up at each price's magnitude. Size floors
against both proposed quantity and proposed notional. Asset-aware quotes also
consume a per-side budget floored to whole lots. Sub-lot reductions,
duplicate levels and quotes under the requested minimum notional are retired
during simulation. Flat preflight requires a feasible two-sided ladder across
the scenario. The same precision and minimum-notional checks run before and
after the Firewall transform in the worker.

The existing inventory policy computes skew and suppresses the increasing side
at its target-relative hard limit. The opt-in Firewall caps apply the legacy
absolute limits together with the declared absolute and target-relative bounds.
Preflight checks opening capacity and full-notional reservation. Optional
Phase 18.3 margin runs use the existing hypothetical or source-constrained model
and post-transform headroom check. The existing ledger settles each simulated
fill, fee and scheduled funding event once.

## Research evidence and PAPER admission

The classification is operator-declared and the controls are hypothetical.
Changing the family changes provenance and fingerprints. Numerical settings
come from the explicit declaration. Volatility uses the existing RMS log-return
estimator per accepted observation, including warmup. The existing L2 policy
uses scenario book depth. The perpetual-context policy uses the explicit
funding-shift cap and the scenario's synthetic rates. Funding accounting uses
the scenario interval.

With `asset_amm_policy` present, the existing PAPER assessor verifies the
declaration clock, accounting units, synthetic reference, metadata and active
catalog before strategy and risk preflight. The configuration fingerprint binds
the policy, mapped strategy, market and catalog, synthetic dataset and financial
settings, plus the bound risk model when active. The result fingerprint includes
that configuration binding. The worker repeats admission and checks the
captured generation and deadline immediately before simulation.

An advisory digest must resolve to a matching, current server-published snapshot.
The application retains up to eight snapshots in memory. A missing or stale
snapshot yields a structured rejection. The reference contributes provenance
without supplying prices, funding or recommendations to the simulated strategy.
The Phase 18.5A assessment stays research-only. Local admission and simulation
retain `execution_mode=PAPER`, `authority=NONE` and `execution_eligible=false`
on their applicable contracts. Offline tests guard exchange submission,
cancellation, wallet signing, leverage changes and the TESTNET adapter, and
exercise Firewall HALT, quote retirement and recovery.

## Legacy comparison

The same probe ran against PR #95 and this change. The 39 native dataset
fingerprints, three native 40-frame BTC/ETH/SOL captures, portfolio, 240
supervisor evaluations and 240 final authorizations matched. Duplicate
supervisor and authorization captures excluded their wall-clock timestamps
using the Phase 18.4 comparison convention.

| Native evidence | SHA-256 |
| --- | --- |
| Combined evidence | `22eed4a5c0d67fa94b0e8780e9cbfd3af50276cab4e2b5e2a22e581b449a34ad` |
| Six-agent outputs | `308a110e3245e593cae3a6386d9ed26377be9a66dda8b3f8f55912a812aa6a2b` |
| Final authorizations | `ef990233ca2afd8d2662db40bb3e346908f378fddf43d275ece2ccfb344b65a9` |

Generalized PAPER admission and result JSON matched byte for byte across 38
policy-disabled captures. This covered all 13 standard scenarios on Core DOGE
and HIP-3 `xyz:GOLD`, plus QUIET, HIGH_VOLATILITY and FLASH_MOVE in both
Phase 18.3 risk modes for each market. Fixtures used 40 frames, the same
fixed clock, 7/13 bps fees, two-second funding and the same modeled stress
assumptions on both trees. SHA-256 of the compact comparison capture was
`b7077b26d52a57dd3bd05accb510167793e5f849cf4eb84315d98f62680e3eac`.
The native digest and legacy quote and accounting evidence retain their
accepted values.

## Executed checks

| Check | Result |
| --- | --- |
| Phase 18.5A on the PR #96 baseline | 41 passed in 0.32 s. |
| Focused Phase 18.5A–D | 91 passed in 4.00 s. |
| Phase 18 and targeted AMM, strategy, inventory, adaptation, perpetual context, accounting and risk | 951 passed, four existing warnings in 38.58 s. |
| Full backend `python -m pytest -q -rs --tb=short` | 3,883 passed, zero failures or skips, five existing warnings in 645.32 s. |
| Frontend `npm ci`, `npm run typecheck`, `npm test`, `npm run build` | All passed. 889 tests, zero failures, skips or cancellations. |
| Static checks | Ruff syntax and undefined-name checks and `git diff --check` passed. |
| Extreme-price PAPER probe | Both AMM models completed 12 frames and authorized 48 quotes each at `0.001` with `szDecimals=0` and at `1000000` with `szDecimals=6`. |

Backend warnings came from the existing Starlette TestClient deprecation,
Pydantic instance-field deprecations and deliberate invalid-concentration
serialization test. The frontend install used the workspace npm cache. The production build
reported existing TanStack client-directive and bundle-size warnings.

## Limits and handoff

Admission covers a single market, the captured discovery generation and
synthetic PAPER economics. Advisory references expire with their source
evidence and are transient across process restarts and cache eviction.
The existing generalized profile and financial bounds limit the admissible
scenario and parameter combinations.

Phase 18.5E can expose the explicit controls and provenance in the existing
Simulation UI and TypeScript contracts. Phase 18.5F can expand the asset
matrix, browser workflows, provider validation and final financial reconciliation.
