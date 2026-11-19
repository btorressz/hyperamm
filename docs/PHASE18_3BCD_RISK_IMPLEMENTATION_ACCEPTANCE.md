# Phase 18.3B–D market risk acceptance

The implementation is based on merged PR #90 at `3752b716f724941f1f89539e03e3a9706675491d`. Review covered Audit 3.0 remediation and the identity, discovery, PAPER, and provenance changes from PRs #84–#89. The 18.3A readiness contract still reports `BLOCKED` and all of its authority flags remain literal false. Its focused baseline passed 22 tests before implementation. [PR #90](https://github.com/btorressz/hyperamm/pull/90) · [Audit 3.0 acceptance](AUDIT3_FINAL_REMEDIATION_ACCEPTANCE.md) · [18.2G acceptance](PHASE18_2G_FINAL_HARDENING_ACCEPTANCE.md)

## Findings and allocation

The public perpetual payload carries financial fields that discovery previously discarded. The matching token registry is network-scoped. Current responses omit `marginMode` for some listed markets and omit explicit table rows for documented short-form IDs. PAPER already ties admission to a single complete catalog generation. Its full-notional reservation already accounts for resting and replacement overlap, and its Risk Firewall already supplies severity ordering, recovery, quote transforms, and final authorization.

| Classification | Files and responsibilities |
| --- | --- |
| REUSE | Phase 18.3A `RiskFinancialUnit`, `MarketCollateralIdentity`, `MarketMarginPolicy`, `assess_market_risk_readiness()`, canonical identities and fingerprints, exact Decimal validation, existing exposure arithmetic, matcher, ledger, research executor, agents and authorization. |
| ENHANCE | `market_data/market_universe_discovery.py` for one token-registry request within the existing refresh. `api/market_universe.py` and `simulation/generalized_market_profiles.py` for opt-in admission, source and model binding. `simulation/engine.py` and `risk/firewall.py` for local risk controls and an additive evidence envelope. |
| ADD | `market_data/market_risk_metadata.py`, `risk/market_risk_engine.py`, the three `test_phase183[bcd]*` suites, and this acceptance report. The architecture and changelog record the rollout. |

The allocation targets apply to architectural dependence. Frontend compatibility was checked through the current workflow and build.

## 18.3B public financial evidence

SDK 0.24.0 exposes `Info.perp_dexs()`, `Info.meta(dex=…)`, and `Info.spot_meta()`. The discovery transport sends these read-only requests to the configured network's official `/info` endpoint. It skips SDK constructor requests and WebSockets and closes each SDK session. It shares the 15-second refresh deadline, three-provider-call concurrency limit, 1 MiB per-response limit, generation TTL, and rate-limit backoff. The token registry is collected once per refresh when a namespace returns a bounded collateral index. A token-registry failure leaves an otherwise complete discovery generation usable, with collateral marked unavailable. A partial DEX refresh publishes no new complete generation. Prior evidence is retired for admission. [Perpetual Info](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals) · [Spot Info](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/spot)

`phase183b-v1` observations bind the exact market, venue, network, DEX, universe fingerprint, `meta` and `spotMeta` provenance, and both receipt times. `meta.collateralToken` resolves against `spotMeta.tokens[].index`. The original index and stable token ID are retained in the `hyperliquid.spot` namespace. Duplicate indexes or IDs invalidate resolution. The display symbol supplies a label. A market can have observed collateral with an unavailable margin policy. The overall observation reports `SOURCE_OBSERVED`, `STALE`, `UNAVAILABLE`, or `UNSUPPORTED` with component statuses and bounded reasons. [Account abstraction modes](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/account-abstraction-modes) · [HIP-3 specification](https://hyperliquid.gitbook.io/hyperliquid-docs/hyperliquid-improvement-proposals-hips/hip-3-builder-deployed-perpetuals)

The derivative base identity, price denomination, collateral, P&L, and PAPER accounting unit have separate evidence. For reviewed Mainnet BTC/ETH/SOL with matching canonical USDC collateral, published contract specifications establish a USDT oracle denomination and USDC P&L under the documented quanto convention. That evidence is labeled as documentation and does not establish a native spot token for the oracle quote. The public endpoints do not independently establish a settlement asset for arbitrary Core markets or HIP-3 products. Their source settlement remains unknown. Source observations never establish an account's abstraction mode, available margin, leverage, collateral balances, P&L, portfolio-margin eligibility, or cross-DEX credit. [Contract specifications](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/contract-specifications) · [HIP-3 specification](https://hyperliquid.gitbook.io/hyperliquid-docs/hyperliquid-improvement-proposals-hips/hip-3-builder-deployed-perpetuals)

The schema preserves `strictIsolated` (margin removal restricted), `noCross` (isolated with margin removal), and explicit `normal` (cross eligible). Deprecated `onlyIsolated=true` alone indicates isolated eligibility with an unspecified restriction. Absent or unfamiliar modes stay unknown. An explicit current mode takes precedence over the deprecated field. Tables resolve only inside their own DEX using the market's explicit `marginTableId`. IDs below 50 follow the published single-tier rule. Explicit bounds start at zero, increase strictly, and select the later tier at its inclusive lower bound. Leverage cannot increase in a higher tier. Contradictions with the market's reported maximum or the single-tier rule invalidate the table. [HIP-3 deployer actions](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/hip-3-deployer-actions) · [Margining](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/margining) · [Margin tiers](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/margin-tiers)

## 18.3C modeled financial calculations

| Mode | Model inputs and limits |
| --- | --- |
| `HYPOTHETICAL` | Explicit initial and maintenance fractions and separate capital in `HYPOTHETICAL_QUOTE`. Optional leverage requires a declared maximum and an initial fraction at least as conservative as its reciprocal. A fresh observed leverage cap constrains research leverage when available. Without a source-unit valuation in this mode, the lowest observed tier cap is the conservative ceiling. |
| `SOURCE_CONSTRAINED` | Fresh collateral mapping, explicit supported margin mode, valid documented tier schedule, integer research leverage, and a user-declared fixed valuation to the exact observed asset. Single-tier HIP-3 schedules and Core multi-tier schedules with canonical USDC are supported. HIP-3 multi-tier schedules with unestablished threshold denomination fail closed. |
| Both | Single-market isolated research with a local budget. Cross margin sharing, live FX, funding forecasts, account equity, venue transfer rules, and liquidation are outside the model. |

The fixed conversion rate explicitly specifies units of the observed collateral per PAPER quote. The model values the mark, capital, and costs at the same simulation frame time. Each snapshot records this time and the model fingerprint. The fixed rate and all stress transformations are research assumptions. The provider receipt times remain in the captured observation.

The existing Firewall exposure function computes signed base position, absolute marked notional, limiting one-sided projected positions, and inventory utilization. The research snapshot also reports long and short gross exposure, separate proposed and resting order notionals, effective quote notionals, and concentration against declared capital. The overlap rule takes the larger desired or resting quantity at each side and level, and independently takes the larger notional. Surplus resting orders at one level sum first. No other market participates.

Hypothetical initial and maintenance requirements multiply the relevant marked notional by the declared fractions. Source-constrained initial requirements divide by research leverage when it fits the tier. Above the tier's maximum the snapshot marks leverage unsupported and shows the requirement at the tier cap as a conservative estimate. Source maintenance applies a marginal rate of `1 / (2 × tier leverage)` across each traversed segment. This is the continuous deduction formula written as a sum of segments. Projected requirements take the maximum across current holdings and either side filling independently.

Financial inputs use the existing bounded Decimal parser and reject binary floats and nonfinite values. Research arithmetic uses a local 120-digit Decimal context. Requirements round up to eight fractional places in the modeled margin denomination. Headroom is modeled capital less the respective requirement. The budget starts at declared research capital and incorporates simulated net P&L once. Actual PAPER equity, fees, funding, and reserved capital remain in the existing ledger. Ratios have no unit and utilization is unavailable when its denominator is nonpositive.

Up to eight named stresses apply a price rally or decline, collateral-value haircut, capital reduction, and funding/fee surcharges. The stress uses the least favorable P&L among the current position and the two one-sided projected positions, reprices requirements at the shocked mark, and reports headroom deterioration and tier changes. Positive capital is the only amount haircut. Stress results are scenario evidence and do not alter the ledger or simulate an exchange liquidation.

## 18.3D PAPER worker and Firewall

Opt in by including `research_risk` in the existing generalized PAPER eligibility request. Submit the same proposal and returned `expected` binding to the existing run endpoint. Clients can send assumptions and fingerprint expectations. The server resolves financial observations from the current discovery generation. The model digest binds the market, source observation, assumptions and formula version. Admission verifies identity, network, source freshness, units, mode, leverage and the capital feasibility of the smallest generated opening quote. The API and worker check expiry and the generation guard before dispatch and engine start respectively. The running scenario retains its captured inputs.

An example `research_risk` member for a generalized PAPER proposal:

```json
{
  "mode": "HYPOTHETICAL",
  "margin_mode": "ISOLATED",
  "capital_paper_quote": "10000",
  "initial_margin_fraction": "0.2",
  "maintenance_margin_fraction": "0.1",
  "stresses": [{"name": "decline", "price_shock_bps": "-1000"}]
}
```

For source-constrained use, supply `leverage` and `valuation` in place of the margin fractions. Eligibility can return `RISK_UNIT_MISMATCH` with the observed collateral when valuation is omitted. Use its network, symbol, namespace and token ID in `valuation.collateral_unit` as fields `network`, `symbol`, `asset_namespace` and `asset_reference`. The declared unit has `kind="EXCHANGE_ASSET"` and `provenance="DECLARED_UNVERIFIED"`. Supply the fixed research assumption as `valuation.collateral_per_paper_quote`.

The existing Firewall combines modeled margin with its mandatory controls using the stricter severity. At 80% projected utilization it can widen. Infeasible projected initial margin or leverage can reduce. Exhausted maintenance headroom and invalid exposure halt the local ladder. The transformed, rounded ladder is checked again before final authorization and can be retired in full if still infeasible. The same recovery conditions, PAPER matcher, outstanding orders, and `FinalQuoteAuthorization` remain in the execution path. The versioned `phase183d-v1` result records effective states, reasons, quote counts, retirements, and a final post-reconciliation exposure/margin/stress snapshot.

Risk-disabled API serialization, run fingerprints, and financial data follow the Phase 18.2G path. The optional path stays under `PAPER` with `authority="NONE"` and `execution_eligible=false`. Its model assumptions grant no account permissions. The focused integration instruments the exchange constructor and order, cancellation, leverage and signing boundaries, as well as the guarded TESTNET adapter. Every recorded operational call count was zero.

## Public provider observation and modeling results

The bounded SDK check on November 18, 2026 around 8:51 p.m. Pacific produced a complete Mainnet discovery with 567 records over 11 namespaces. These selected observations preserve the exact DEX and token registry identity.

| Market | Collateral token | Observed margin | Outcome |
| --- | --- | --- | --- |
| `MAINNET / Core / BTC` | Index 0, USDC, `0x6d1e7cde53ba9467b783cb7c530ce054` | Table 56, 40× from zero and 20× from 150,000,000. Mode omitted. | Partial financial evidence. Source-constrained admission treats the mode as unknown. |
| `MAINNET / Core / XTEN` | Index 0, same Mainnet USDC asset | `strictIsolated`, table 3, single 3× tier. | Five local PAPER frames completed with source-constrained research and synthetic price and capital. |
| `MAINNET / xyz / HOOD` | Index 0, same Mainnet USDC asset | `noCross`, table 10, single 10× tier. | Five local PAPER frames completed with source-constrained research and synthetic price and capital. |
| `MAINNET / cash / USA500` | Index 268, USDT0, `0x25faedc3f054130dbb4e4203aca63567` | Table 20. Mode omitted. | Delisted. Collateral identity still distinct from Core. |
| `TESTNET / Core / BTC` | Index 0, Testnet USDC, `0xeb62eee3685fc4c43992febcd9e75443` | Table 54 with separate thresholds and leverage. Mode omitted. | Direct bounded normalization succeeded. The full Testnet inventory exceeded the existing 64-namespace limit. |

The captured observation digests for Mainnet BTC, XTEN, and xyz:HOOD were `46a8ec2673dc3b1de0880142d70a6653d5d79a0ad2345b80a500581a35b3f10e`, `9a929956cc34dbd7ea487e3433d5fe0bc4822b415a93dfadfe891ff228439abd`, and `d182f953a9a3f641efce4955438d95eeaedbe6c168747ac54ab9a1185cea441f` respectively. The two successful local results had authority `NONE`. The run inputs deliberately used a synthetic reference price, fixed hypothetical conversion, and hypothetical capital.

## Financial compatibility and regression

The PR #90 comparison used separate worktrees and identical dependencies. It matched 39 native scenario dataset fingerprints and the BTC, ETH and SOL profiles, strategies, AMM outputs, fees, funding, fills, inventory, ledger, risk decisions, final quote authorizations and portfolio reconciliation. Native dataset and portfolio digests match the accepted Phase 18.2G figures. The native comparison including `FinalQuoteAuthorization` is `dc7279cf41076f1994d06b33e20dc7807a8d6baa488d190964f6a1908182bbcb`. Nonfinancial wall-clock creation times were excluded from the risk and authorization comparison.

The complete risk-disabled output comparison also matched 26 generalized Core/HIP-3 results, covering all 13 existing scenarios on both fixtures at 40 frames with fees and scheduled funding. The combined digest is `c9d5683eee8192599440333a3dbc7e5f1a7540ed799a78222f3e2d30baf1a29e`. The comparison fixes the admission clock so metadata and receipt times are reproducible.

| Check | Executed result |
| --- | --- |
| Phase 18.3A before edits | 22 passed. |
| New Phase 18.3B–D suites | 63 passed (26 metadata, 26 calculations, 11 integration). Includes invalid and stale metadata, ambiguous identity, Decimal and tier-boundary tests, resting order overlap, stress, account and signer isolation, deterministic fills and ledgers, retirement, HALT, recovery, and worker cancellation. |
| Phase 18.3 on Pydantic 2.10.6 | 85 passed with the supported minimum minor series. |
| Selected existing and new regressions | 795 passed, zero failed or skipped, one existing warning. Covers Phase 18, AMM, Risk Firewall, worker coordination, scenarios, accounting, risk, and Audit 3.0. |
| Full backend regression | 3,684 passed in 641.88 s, zero failed or skipped, two existing warnings (Starlette TestClient deprecation and Pydantic serialization in the Phase 17.4 tampering fixture). |
| Frontend | Locked `npm ci`, typecheck, tests, and Vite build passed. 836 tests passed with zero failed, skipped or cancelled. Vite reported dependency directive and bundle-size warnings. |
| Chromium generalized PAPER | 10 workflows passed. Covers the existing Core and HIP-3 API paths, expiry, refresh failure, narrow layout, native selector, and PAPER-only write requests. |
| Capacity | 120 frames and eight stress results on Core BTC and HIP-3 xyz:GOLD produced 903,893 and 911,263 bytes respectively, below the 2 MB transport cap. |

The backend used CPython 3.12.14, Pydantic 2.14.3, FastAPI 0.165.0 and SDK 0.24.0 with the test, Redis, ML and Yahoo extras. Frontend checks used Node 24.19.0 and npm 11.9.0. Browser acceptance used the repository Playwright harness and system Chromium. Exchange order, signer and guarded execution behavior was verified with local instrumentation. Public provider acceptance was limited to read-only metadata and the separately labeled local research runs above.

## 18.3E/F handoff

18.3E owns the typed read-only risk API and substantive React affordances. The current PAPER response carries the bounded source status, model digest and evidence envelope for that work. 18.3F owns broader cross-market acceptance, provider lifecycle soak, and validation of any further independently supported units and formulas. Re-evaluate convention and tier denomination evidence before enabling wider models. The existing account, liquidation, signed execution, and shared capital boundaries remain outside this scope.
