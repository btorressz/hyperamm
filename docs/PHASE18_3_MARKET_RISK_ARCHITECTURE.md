# Phase 18.3 — Market-Specific Collateral, Margin & PAPER Risk

**18.3A baseline:** additive risk contracts from merged PR #90. The
foundation was implemented on top of Phase 18.2G PR #89, commit
`4d57eaf8a0ce8a19c36fe436d8a62ca7e46adfa9`.

## Scope and ownership

ChatGPT 18.3A supplies an independent versioned Pydantic foundation for collateral
identities, margin policy declarations and fail-closed risk-readiness evidence.
Codex 18.3B–F owns real provider-evidence validation, supported mathematics,
simulation/risk wiring, minimal frontend and full native acceptance.

**Architectural target:** reuse 50%, enhance 40%, add 10%, reflecting design
dependence, not changed lines. The Phase 18.3 overall target is 90% backend /
10% frontend.

## Existing modules to REUSE, not replace

| Component | 18.3A usage |
| --- | --- |
| `market_data/market_universe_contracts.py` | Stable network-qualified Core/HIP-3 instrument identity, official metadata source, observation, discovery freshness; no inferred collateral from market symbol |
| `simulation/generalized_market_profiles.py` | Phase 18.2G explicit synthetic reference, hypothetical quote units, full-notional reservation, unverified venue economics, single-market research-only boundary; not an exchange collateral policy |
| `market_data/live_models.py` | Immutable evidence conventions, frozen models; no live mark/oracle/funding calls |
| `accounting/config.py` | Existing exact bounded Decimal parser, avoids float and exponent abuse; no change to ledger |
| `simulation/models.py` | Canonical stable financial fingerprint implementation |
| `risk/firewall.py`, `risk/authorization.py`, `risk/limits.py` | Existing state machine, risk authorization and exposure guardrails; untouched in 18.3A |
| `accounting/service.py`, `accounting/models.py` | Local PAPER ledger, capital reservation, fees and P&L; untouched |
| `portfolio_research/models.py` | Native BTC/ETH/SOL, USDC-only capital budget and restrictive shared-capital research; untouched |
| Existing tests, browser and Audit 3.0 acceptance | Preserve history; independent execution still required |

## New contracts

Implementation: `backend/app/risk/market_risk_contracts.py`.

### 1. RiskFinancialUnit

A strict, frozen network-scoped reference. Distinguishes:

- `EXCHANGE_ASSET`: an *explicitly declared, unverified* asset identifier,
  with a bounded symbol, namespace and reference. A declaration does not prove
  exchange listing, collateral eligibility, settlement support or value.
- `HYPOTHETICAL_QUOTE`: the sentinel accounting unit from Phase 18.2G.
  Must have `RESEARCH_ASSUMPTION` provenance and no exchange asset reference.

**No automated quote→collateral equivalence or FX conversion.** Network
mismatch is rejected. Even if two declarations display the same symbol, a
consumer cannot establish fungibility from labels alone.

### 2. MarketCollateralIdentity

Ties the existing `MarketUniverseMetadata` and its fingerprint to separately
declared `price_quote_unit`, `collateral_unit`, `settlement_unit` and mandatory
`paper_accounting_unit`.

All declared exchange units must share the market network. Missing collateral
or settlement is represented by `None`; it is never defaulted to USDC. The
exchange evidence flags `verified_collateral` and `verified_settlement` are
literal `False`; `read_only=True` and `authority=NONE` are fixed.

No asset-specific source evidence is added here: Phase 18.3B must validate
the actual asset/DEX/account configuration and introduce distinct, non-inferred
exchange observations if available.

### 3. MarketMarginPolicy

A strict immutable policy declaration with explicit account and margin mode.
These modes are **labels for possible future evidence**, not asserted
availability for a particular HIP-3 DEX or account.

- `UNVERIFIED`: no numeric margin fractions or leverage may be asserted.
- `HYPOTHETICAL`: can carry explicit, bounded initial/maintenance fractions,
  an optional modeled leverage ceiling and a selected mode. These are *scenario
  assumptions* only, never verified exchange rules.
- Initial and maintenance fractions are Decimal and range (0,1]; maintenance
  cannot exceed initial. No float values, nonfinite input or exponent bombs.
- Liquidation price remains `None`; verified-margin, shared-capital,
  netting and execution flags are fixed `False`.

The contracts do not calculate margin, liquidation, FX, gross exposure,
netting or collateral haircuts.

### 4. MarketRiskReadiness and assess_market_risk_readiness

Pure blocked-readiness projection from a fully revalidated, captured policy.
Explicit reasons include missing/stale/delisted market evidence, absent
collateral declaration, unverified collateral and margin, or hypothetical-only
research policy.

The decision binds canonical market identity, metadata, collateral and policy
fingerprints and evaluation time. All 18.3A decisions are `BLOCKED` with
`SINGLE_MARKET_RESEARCH_ONLY` and hard-coded false flags for exchange margin,
shared capital, leverage, netting, trading authorization and risk readiness.

There is intentionally **no READY state in Phase 18.3A**. Neither official
perpetual metadata nor a hypothetical fraction proves what collateral is
accepted for a specific DEX, market, account or margin mode.

## Compatibility and authority invariants

- Legacy `ResearchPerpMarketId` stays `Literal["BTC","ETH","SOL"]`.
- Existing native `PortfolioCapitalBudget.quote_currency="USDC"` and
  restricted market allocations remain as-is.
- Phase 18.2G retains `HYPOTHETICAL_QUOTE`, `SIMULATED_FULL_NOTIONAL`,
  `HYPOTHETICAL_MAKER_TAKER`, `HYPOTHETICAL_SCHEDULED`,
  `exchange_economics="UNVERIFIED"` and
  `risk_readiness="SINGLE_MARKET_RESEARCH_ONLY"`.
- The new models are **not** accepted as direct input to Risk Firewall
  authorization, order routing, operational portfolio equity, or SDK signing.
- Market metadata, price quotes, collateral assets, settlement assets and
  hypothetical units are distinct; never silently net unlike units.
- An exchange asset *declaration* is not a verified exchange *observation*.
- A model hash proves deterministic input identity, not provider authenticity.
- No dynamic discovery of verified margin fields, no live market price adapter,
  no new provider calls or public routes, no cross-market calculations and
  no new execution permissions.

## Phase 18.3 handoff plan

| Milestone | Owner | Required implementation and acceptance |
| --- | --- | --- |
| **18.3B** | Codex | Read-only source-backed per-DEX product collateral and independently documented financial units. Validate provenance, timestamps, market/network/DEX association, provider capabilities, unavailable states and model version. No default USDC inference. |
| **18.3C** | Codex | Separate hypothetical vs independently supported margin calculations. Exact Decimal notional, currency-aware base/quote units, bounded leverage and margin stress, FX/haircut provenance. Refuse unsupported currencies and missing evidence. |
| **18.3D** | Codex | Integrate optional risk evidence into single-market local PAPER preflight and Risk Firewall using existing authorization; never let a research decision reach exchange orders. Do not automatically enable cross-market portfolio allocation. |
| **18.3E** | ChatGPT + Codex | Minimal bounded read-only research API evidence and existing Simulation UI: source, freshness, margin mode, collateral and hypothetical/unverified labels. Keep the full Market Explorer for 18.6. |
| **18.3F** | Codex | Adversarial cases (identity, wrong network, stale data, cross-currency arithmetic, collateral price shocks, insufficient capital, notional/rounding, race/expiry), full regression, fingerprint comparison, zero signed calls and acceptance report. |

**Critical gates for 18.3B–F:** never upgrade `exchange_margin_verified`
or `risk_ready` by simply changing the v1 contract literals. Require new
source-backed and independently verified evidence/contracts, checked against
real SDK behavior and supported product/account modes. Treat hypothetical
calculations as hypothetical and preserve PAPER-only authorization.

## 18.3B–D implementation

- Discovery keeps one bounded public SDK refresh. The financial supplement
  resolves `meta.collateralToken` to the same network's `spotMeta` token ID,
  records market modes and tier policy, and preserves source timestamps,
  status and fingerprints. Independently documented price denomination and
  P&L use separate fields. Account mode remains unknown.
- The optional `phase183c-v1` model uses strict Decimal assumptions and
  the existing exposure overlap rules. Source-constrained assessments require
  a supported observed policy, an exact asset match, and an explicit fixed
  hypothetical valuation. Source and modeled formulas have distinct evidence.
- Existing PAPER eligibility and dispatch bind the source generation and the
  model fingerprint. The existing Firewall can tighten local quote decisions,
  and the existing ledger retains full-notional reservation. The
  `phase183d-v1` result includes only local research control and margin evidence.
  The runtime and guarded TESTNET adapter retain their existing authorization.
- Phase 18.3E owns the risk API and UI expansion. Phase 18.3F owns extended
  financial and cross-market verification.

See the [implementation acceptance report](PHASE18_3BCD_RISK_IMPLEMENTATION_ACCEPTANCE.md)
for provider details, formulas, test evidence, and unsupported cases.

## Focused verification

`backend/tests/test_phase183a_market_risk_contracts.py` verifies:

- Core/HIP-3 and Mainnet/Testnet canonical identity independence.
- Separate quote, collateral, settlement and hypothetical account units.
- No implied USDC, unsupported/cross-network units and missing collateral.
- Rejection of privilege escalation, fake exchange identity and invalid flags.
- Explicit unverified versus hypothetical margin and strict Decimal bounds.
- Fail-closed stale/future/delisted/unavailable discovery evidence.
- Stable fingerprints, nested mutated-copy revalidation and unchanged legacy
  three-market research admission.

### Independent acceptance required

The new files are authored through the GitHub connector. **Full repository
pytest, typechecking, npm, browser and live SDK validation have not been
executed in this PR.** Phase 18.3A must receive an independent native
contract test run and relevant backend regression before merge; Codex may
repair demonstrated contract defects in a small acceptance follow-up.

No new financial arithmetic or runtime integration is claimed.
