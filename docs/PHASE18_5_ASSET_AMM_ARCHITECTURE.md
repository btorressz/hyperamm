# Phase 18.5 — Asset-Aware AMM Research Policy and Architecture

**Phase 18.5A status:** contract-only foundation on merged Phase 18.4 PR #95,
`8295ba157a3d9659cc4ddde214d395e2bc67c563`. No AMM or strategy
runtime changes, new market-data polling, API, frontend, quote authorization,
TESTNET order capability or new agent.

**Phase 18.5B–D status.** The existing Generalized PAPER routes accept an
optional `asset_amm_policy` using the Phase 18.5A contract. The strategy and
worker use the same AMM, scenario, accounting and Risk Firewall components
described below. See the [Phase 18.5B–D acceptance record](PHASE18_5BCD_ASSET_AMM_ACCEPTANCE.md).

## Engineering allocation

**18.5A:** REUSE ~50% / ENHANCE ~35% / ADD ~15% architecturally; 100%
backend and documentation, 0% frontend. This refers to engineering reuse,
not proportions of changed lines. Whole Phase 18.5 will be revisited after
Codex inventories the actual implementation.

### REUSE

| Existing module | Preserve / use |
| --- | --- |
| `amm/models.py`, `amm/virtual_reserves.py`, `amm/liquidity_curve.py`, `amm/discretizer.py`, `amm/numeric.py` | Current virtual constant-product and concentrated-liquidity models, reserve math, curve sampling, executable price/size normalization and bounded Decimal arithmetic. No replacement curve in 18.5A. |
| `strategy/models.py`, `strategy/quote_engine.py` | Existing `StrategyConfig`, `AmmModel`, quote generation, concentration, virtual reserves, tick and size controls. No changed default settings or quote engine behavior. |
| `strategy/inventory.py`, `strategy/market_adaptation.py`, `strategy/perp_policy.py` | Existing inventory target and hard/soft limits, volatility and L2 adaptation, funding/perp-reference bounds. Advisory signals are not direct operational policy. |
| `simulation/market_profiles.py`, `simulation/generalized_market_profiles.py` | Qualified Core/HIP-3 PAPER precision, synthetic price, scenario ownership and exact existing admission. PAPER quote results stay unmodified. |
| `market_data/market_universe_contracts.py` and discovery | Canonical network/DEX-qualified instrument identity, provider metadata, listed state and freshness. Metadata does not convey asset family or production trading permissions. |
| `risk/market_risk_contracts.py`, `risk/market_risk_engine.py` | Financial-unit and margin evidence; hypothetical budgets and source-constrained research models. No unverified cross-market capital or collateral netting. |
| `agents/advisory_contracts.py`, `agents/advisory_coordinator.py` | Source-bound eligibility, funding/basis and quote-economics **observations only**. These do not directly change quote size, spread or order authority. |
| `simulation/models.py` | Canonical stable SHA-256 deterministic fingerprints. |
| `accounting/config.py`, `market_data/live_models.py` | Existing exact bounded Decimal parsing and frozen, forbid-extra evidence semantics. |

### ENHANCE in 18.5A

Only the **research policy contract layer and architectural documentation**.
Actual `StrategyConfig`, AMM quote generation, Risk Firewall, accounting,
six material/observational agents and generalized PAPER paths are unchanged.

### ADD in 18.5A

- `backend/app/amm/asset_policy_contracts.py` — immutable
  `phase185a-v1` Pydantic declarations and pure discovery assessment.
- `backend/tests/test_phase185a_asset_amm_contracts.py` — focused
  adversarial contracts and legacy-runtime isolation.
- This architecture document and a short changelog entry.

## Versioned research contracts

### AssetResearchClassification

One explicit operator-declared research family:
`CRYPTO`, `EQUITY`, `INDEX`, `COMMODITY`, `ENERGY`, `FX`,
`RATES`, `OTHER` or `UNKNOWN`.

**This is NOT an exchange-certified asset class.** The instrument name,
symbol, HIP-3 DEX label and price are not sufficient evidence of underlying
asset type or exposure to real-world instruments. Neither classification nor
the fact that a perpetual is listed establishes regulatory status.

`exchange_class_verified=false` and `tradability_verified=false`
are permanently locked in v1. Future ingestion of verified product taxonomy
requires an independent authoritative source and a new evidence contract.

### AssetAmmResearchControls

A bounded, hypothetical subset of **existing** `StrategyConfig` parameter
names and `AmmModel` values:

- `CONSTANT_PRODUCT` and `CONCENTRATED` from the existing AMM enum.
- Virtual base/quote reserves.
- Levels per side, maximum quote distance and per-side base liquidity.
- Concentration factor and lower/upper distance bounds.
- Target, soft/hard inventory limits and price skew.
- Volatility-driven spread and size strengths.
- Maximum funding reference shift.
- Fixed `REUSE_GENERALIZED_PRECISION` and
  `REUSE_DISCOVERED_SZ_DECIMALS` declarations.

Size, reserves and inventory quantities have explicitly typed BASE or
hypothetical quote units through their field names; spread, concentration
distance and reference shifts use bps where identified. The underlying
perpetual metadata has no actual settlement verification.

All numeric inputs use the existing `bounded_exact_decimal()` (rejects
float, boolean, NaN, infinity and unbounded exponents). Existing cross-field
constraints cover concentration distance, inventory soft/hard limits and
minimum theoretical liquidity. Phase 18.5B–D validates the full
`StrategyConfig`, discovered `szDecimals`, market-specific price
normalization, minimum notional and actual curve and quote feasibility.

These are declared research parameters, never automatic market-calibrated
defaults. No family-specific numeric preset is represented as observed data.

### AssetAmmResearchPolicy

Binds:

- Exact `MarketUniverseMetadata` and metadata SHA-256.
- One declared research family.
- One `AssetAmmResearchControls`.
- A mandatory same-network `HYPOTHETICAL_QUOTE` accounting unit.
- Explicit user-supplied *synthetic* reference price.
- Declaration timestamp.
- Optional captured catalog, Phase 18.3 risk and Phase 18.4 advisory
  fingerprints, not assertions of validity.
- `execution_mode=PAPER`, research-only scope and fixed no-authority flags.

The policy fingerprint covers the canonical network, Core/HIP-3 namespace,
metadata, classification, controls, hypothetical reference, declarations and
optional dependency fingerprints. Its digest establishes reproducible content,
not exchange authenticity or admission.

### AssetAmmPolicyAssessment

`assess_asset_amm_policy` revalidates the entire captured policy and
invokes the existing `evaluate_discovery` with an explicit evaluation clock
and freshness budget.

- `RESEARCH_DRAFT` + `DISCOVERABLE` = valid research *declaration* only.
- `BLOCKED` + original discovery reason = stale, delisted, invalid or
  missing official discovery evidence.

All assessments retain:

`eligible_for_paper=false`,
`eligible_for_testnet=false`, `eligible_for_live=false`,
`risk_ready=false`, `affects_quotes=false`,
`can_override_risk=false`, `execution_eligible=false`,
`read_only=true` and `authority=NONE`.

**Important:** `RESEARCH_DRAFT` is not PAPER admission and does not
imply that 18.5B asset-specific parameters are economically, precision- or
margin-feasible. Actual PAPER admission remains governed by its existing
server-side assessor and final Risk Firewall.

## Phase 18.5B–D implementation

`apply_asset_research_policy()` takes a synthetic PAPER baseline for the
qualified market and updates only the declared controls and discovered
precision. Virtual reserves define the AMM invariant. The existing quote
compiler recenters that pool to the synthetic reference for each frame.
The market's `szDecimals` determines size lots and the compiler's internal
decimal grid. The generalized normalizer rounds outward at each quote's
price magnitude and floors size and notional. Opt-in quotes also consume a
whole-lot per-side budget and meet the requested minimum notional.

The server binds the declaration to current metadata, the active catalog
and the proposal's synthetic reference. The configuration digest includes
the policy, mapped strategy, scenario, capital and risk inputs. The worker
revalidates these inputs and checks the captured catalog guard before engine
entry. Absent policies and bindings are omitted from serialized responses
and fingerprint inputs. The Phase 18.5A assessment keeps research-draft authority.

The application can resolve a supplied advisory fingerprint against its
bounded cache of eight published snapshots. The market, catalog, clock,
expiry and applicable risk evidence are checked. The advisory reference
contributes provenance. Synthetic frames continue to provide the book,
funding and price inputs for strategy and accounting.

## Phase 18.5E–F handoff

| Phase | Ownership | Implementation / acceptance |
| --- | --- | --- |
| **18.5E** | ChatGPT + Codex | Minimal read-only asset-policy evidence API and existing Simulation/Generalized PAPER UI. Expose explicitly hypothetical research class, controls, fingerprints, disabled/unsupported status, and modeled results; no full Market Explorer. |
| **18.5F** | Codex | Expand the adversarial and asset-family scenario matrix, browser workflows, financial reconciliation and provider/metadata verification. Reproduce the legacy compatibility checks after Phase E. |

No parallel AMM engine, second accounting runtime, persistent new market
classifier, wallet connection, new operational strategy mode or API in 18.5A.

## Focused tests and independent acceptance

`backend/tests/test_phase185a_asset_amm_contracts.py` covers:

- Core/HIP-3 Mainnet/Testnet market identity and deterministic fingerprints.
- Exact existing AMM enum, curve and inventory parameter names.
- Strict numeric ranges, finite Decimal and cross-field bounds.
- Operator-declared asset classes never upgraded to verified.
- Synthetic reference versus exchange observed price and financial units.
- Forged authority, margin, live trading and PAPER-admission flags.
- Stale/delisted/unavailable metadata and immutable blocked assessment.
- Nested `model_copy(update=...)` revalidation and legacy StrategyConfig isolation.

The original Phase 18.5A PR authored this suite. Independent execution on its
merge commit passed all 41 tests before B–D integration. The B–D acceptance
record contains the subsequent regression and financial compatibility results.
