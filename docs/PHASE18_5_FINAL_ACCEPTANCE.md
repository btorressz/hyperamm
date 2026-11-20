# Phase 18.5 final local PAPER acceptance

Phases 18.5E–F build on merged PR #97 at
`d6aa1c1907e9b03763c66e49ad001d2487530448`. The review also covered the
merged advisory integration in PR #95, the research contracts in PR #96,
and the prior PAPER and margin acceptance records. [PR #95](https://github.com/btorressz/hyperamm/pull/95) · [PR #96](https://github.com/btorressz/hyperamm/pull/96) · [PR #97](https://github.com/btorressz/hyperamm/pull/97) · [Phase 18.2G](PHASE18_2G_FINAL_HARDENING_ACCEPTANCE.md) · [Phase 18.3](PHASE18_3_FINAL_ACCEPTANCE.md) · [Phase 18.4](PHASE18_4_FINAL_ACCEPTANCE.md)

## Implementation

| Phase | Implementation and acceptance |
| --- | --- |
| 18.5A | `phase185a-v1` family declaration, exact controls, units, policy fingerprint and read-only assessment. |
| 18.5B | Existing `StrategyConfig` mapper and both AMMs, using market-qualified precision. |
| 18.5C | Existing inventory, volatility, book imbalance and perpetual-context policies applied to synthetic scenario inputs. |
| 18.5D | Optional asset policy through the existing PAPER proposal, eligibility and worker, including Phase 18.3 risk and Phase 18.4 advisory provenance. |
| 18.5E | Read-only policy draft endpoint, opt-in configuration in Generalized PAPER, runtime validation and bound result evidence. |
| 18.5F | Independent financial and authority tests, Chromium workflows, bounded public metadata, historical comparison and full regressions. |

| Allocation | Changes |
| --- | --- |
| Reuse 50% | Simulation workspace, API transport, discovery, both AMMs, strategy compiler, worker, all nine agents, Risk Firewall, accounting and margin. |
| Enhance 35% | Generalized PAPER UI and API client, policy and admission lifecycle, financial results, advisory attachment and browser harness. |
| Add 15% | One read-only draft route, compact asset controls and runtime validators, focused tests and this report. |

### Changed files

- Backend production · `backend/app/api/market_universe.py` and `backend/app/simulation/generalized_market_profiles.py`.
- Backend acceptance · `backend/tests/test_phase185e_asset_api.py` and `backend/tests/test_phase185f_asset_acceptance.py`.
- React · `frontend/src/components/simulation/GeneralizedPaper.tsx`, `GeneralizedPaperAdvisory.tsx` and `GeneralizedPaperAssetPolicy.tsx`.
- Browser contracts and transport · `frontend/src/api/client.ts`, `frontend/src/types/assetAmm.ts`, `frontend/src/types/generalizedPaper.ts`, `frontend/src/utils/assetAmm.ts`, `frontend/src/utils/advisory.ts`, `frontend/src/utils/generalizedPaper.ts` and `frontend/src/utils/researchFingerprint.ts`.
- Frontend acceptance · `frontend/tests/browser-phase182.py` and `frontend/tests/phase182-generalized-paper.test.cjs`.
- Documentation · `CHANGELOG.md`, `docs/ROADMAP.md`, `docs/PHASE18_5_ASSET_AMM_ARCHITECTURE.md` and `docs/PHASE18_5_FINAL_ACCEPTANCE.md`.

## Configuration, provenance and admission

Simulation → Generalized PAPER starts in Standard PAPER. Asset-aware mode
adds the existing Constant Product and Concentrated Liquidity choices and
the Crypto, Equity, Index, Commodity, Energy, FX, Rates, Other and Unknown
research labels. The labels describe the operator's declaration. Exchange
metadata supplies the canonical market, network, DEX, listed state and
`szDecimals`. Changing the label alone changes provenance and fingerprints.

The main form exposes levels per side, maximum quote distance, base order
size, per-side liquidity and minimum order notional. Advanced settings cover
reserves, concentration, target and limits, skew, and volatility and funding
adaptation. Labels specify base units, hypothetical quote units, basis points
or dimensionless factors. The displayed research price grid follows the
decimal and significant-figure restrictions of the existing generalized
compiler. Exchange tick calibration remains unverified.

`POST /api/v1/generalized-paper/asset-policy/preview` derives defaults from
the same Python baseline strategy constructor used by PAPER. It validates
optional exact overrides, binds the active catalog and official metadata
fingerprint, stamps the declaration, and resolves any selected risk or
published advisory reference. It returns a `phase185a-v1` policy and a
`RESEARCH_DRAFT` assessment. The draft's PAPER eligibility, risk readiness
and execution flags are false. Quote precision, minimum notional, opening
capacity and modeled risk feasibility are resolved through the existing
`/eligibility` endpoint. The preview performs zero scenario runs and zero
order operations.

The browser validates nested contract versions, canonical source identity,
clocks, exact decimals, cross-field bounds, unit and authority flags, and the
policy digest using the existing sorted, ASCII JSON SHA-256 convention.
Eligible bindings must match the selected metadata, policy, catalog and
applicable risk fingerprint. The same policy is sent via `/run`. The worker
revalidates the captured inputs, deadline and generation before starting.
Edits, catalog replacement, source expiry and advisory expiry retire
browser admission and results. A run consumes the browser's asset-aware
admission. Standard PAPER requests omit the asset extension.

Advisory attachment is explicit and limited to fresh, server-published
discovery evidence for the selected market. The server checks the retained
snapshot again. The synthetic scenario supplies price, book depth and
funding independently of provider observations. The UI reuses the existing
collateral, modeled margin, funding and quote economics views.

Result evidence includes the returned research controls and policy digest,
mapped strategy digest, scenario and frames, simulated fills, equity, P&L,
fees, funding, inventory and modeled risk when enabled. Capital, book
liquidity, economics, fills and price paths are hypothetical. The policy
has PAPER scope, `authority=NONE` and `execution_eligible=false`.

## Financial and adversarial acceptance

| Area | Executed evidence |
| --- | --- |
| Family and identity | All nine families, including Unknown, preserved the same numeric controls. Core and HIP-3 identities bind the network and DEX. Malformed, cross-DEX and cross-network declarations failed. |
| Precision and liquidity | Both models ran with `szDecimals` 0–6 at references from `0.001` to `1000000`. Independent exact lot/notional oracles checked outward price rounding, sub-lot retirement and size/notional conservation. The quote test accepted an exact 20-unit floor and rejected the preceding lot. Duplicate rounded prices and sub-lot risk reductions were retired. Authorized sides retained their liquidity budgets. |
| Inventory and spread | Existing Phase 18.5A–D scenarios covered zero and signed targets, long/short inventory, target-relative soft and hard limits, skew, side suppression and absolute cap admission. A real asset-aware high-volatility browser run reached HALT and every affected frame authorized zero quotes. |
| Volatility, depth and funding | A Decimal RMS oracle compared Quiet, High Volatility, Liquidity Shock, Bid Heavy Book and Flash Move at bounded maximum spread and size strengths. Tests checked observation warmup, missing depth, unbalanced L2 and an interval mismatch. A separate high-volatility probe crossed the price magnitude boundary at 100 and independently reconciled 19 scheduled payments for negative, zero and positive synthetic rates on each AMM. The RMS unit remains one accepted observation. |
| Fees, fills and equity | The oracle replayed chronological fills at exact notional, independently computed average-cost realized and unrealized P&L, scheduled funding and maker/taker fees, and reconciled inventory, net P&L, final equity and the full-notional reservation. Each run reversed position. The existing engine's modeled matcher supplied a separate partial-fill fixture using the mapped asset strategy. The Generalized PAPER route continues to use the baseline crossing matcher. |
| Margin and capital | The oracle computed final projected margin and headroom from resting quantity, mark and hypothetical capital for both risk modes. Insufficient opening capital, unsupported HIP-3 collateral denomination and unsupported leverage were rejected. Existing margin retirement and real asset-aware maintenance HALT checks kept the Firewall authoritative. |
| Provenance and lifecycle | Tests rejected forged digests, elevated capability, wrong units, bad decimals, unknown controls and models, changed policy, stale catalog, future clock, unretained and expired advisory snapshots, and worker-start expiry. Chromium verified canceled delayed admission, network/DEX replacement, settings edits and reset to Standard PAPER. |
| Operational boundaries | Guard fixtures recorded zero exchange submissions and cancellations, wallet key derivations or signatures, operational leverage changes, and native TESTNET adapter calls. The browser wrote only to local research routes. The six supervisor agents and three research advisory agents retain separate authority roles. |

## Public metadata and provider limits

The November 19, 2026 Pacific evening check used the existing official
Hyperliquid SDK transport. Mainnet returned 567 normalized records. The
sample below was listed and discoverable at evaluation. All normalized
market identities and metadata fingerprints matched their catalog decisions,
and serialization round trips retained the evidence.

| Mainnet market | Qualified source | Discovered size precision |
| --- | --- | ---: |
| BTC | Core `meta` | 5 |
| DOGE | Core `meta` | 0 |
| `xyz:GOLD` | HIP-3 `meta`, namespace `xyz` | 4 |

The catalog digest for the sampled generation was
`e6e15950c7224fa904c2bcaed8775b8aca1110908f861ae8205f7f6ce096737b`.
The full Testnet catalog was unavailable at the existing inventory cap.
A separate Testnet Core request normalized 213 markets, including listed BTC
with five size decimals and a Testnet-qualified identity. A mismatched
network and SDK endpoint was rejected before transport, and an unknown
Mainnet namespace produced a bounded upstream error. All 16 SDK request
sessions closed and the discovery pools drained. Public
metadata does not establish collateral, settlement, product taxonomy or
trading readiness.

## Historical compatibility

The comparison ran against the PR #97 merge and this feature branch with
identical fixtures and observed/admission/worker clocks. Standard captures
used Core DOGE at 0.1234 with two size decimals and HIP-3 `xyz:GOLD` at
2500 with three size decimals. They covered all 13 scenarios per market,
plus Quiet, High Volatility and Flash Move for both risk modes per market.
Runs used 40 frames, 7/13 bps fees, two-second funding, and
2026-11-18 04:00 Pacific for discovery and execution clocks. Modeled runs
used 10,000 capital, a −2,000 bps price shock, 300 bps collateral loss,
50 bps capital reduction, and 15/10 bps funding and fee surcharges.

| Capture | Count | Matching SHA-256 |
| --- | ---: | --- |
| Complete Standard PAPER admission and result JSON | 38 | `fd71e1cf76101636d7a5664f9abf6a84fa4349e39a2b33b2bfb16bd91f475b51` |
| Complete asset-aware admission and result JSON | 18 | `6a162041738cbd8512cce988ad63d3be3ee9079de765e7bd13becaa28e8ca947` |
| Native combined evidence, including 39 dataset fingerprints, BTC/ETH/SOL and portfolio | 39 datasets and 3 native runs | `22eed4a5c0d67fa94b0e8780e9cbfd3af50276cab4e2b5e2a22e581b449a34ad` |
| Six-agent supervisory decisions | 240 | `308a110e3245e593cae3a6386d9ed26377be9a66dda8b3f8f55912a812aa6a2b` |
| Final authorizations | 240 | `ef990233ca2afd8d2662db40bb3e346908f378fddf43d275ece2ccfb344b65a9` |

The two generalized probes compared compact arrays of pairs containing the
exact serialized admission and result strings. Each tree produced identical
bytes, including quote ladders, fills, accounting and risk. The 18 asset
captures use the Phase 18.5D fixture builder with both AMMs, the three
scenarios and risk off, hypothetical or source-constrained. Additional route
tests independently prepared those draft inputs and compared the resulting
mapped strategy and financial result against direct execution.

For the controlled probe, use `market_wire`, `observation`, `hypothetical`
and `sourced` from the Phase 18.3 fixture files and `asset_proposal` from
the Phase 18.5D suite. Use one 10× source tier, Core collateral index 0,
HIP-3 collateral index 268, catalog binding `"c" * 64`, and a 60-second
generation. In each mode capture Core then HIP-3, with standard scenarios
in enum order followed by the three scenarios per risk mode. Use constant
product for the Core asset-policy cases and concentration for HIP-3.
Pack the serialized pairs with compact JSON separators and zero trailing
line feed.

PR #97 publishes
`b7077b26d52a57dd3bd05accb510167793e5f849cf4eb84315d98f62680e3eac`
for its original generalized capture. The exact fixture construction and
array serialization for that aggregate are unspecified in its report.
The new aggregate represents the controlled two-tree comparison. The
published native, supervisor and authorization digests reproduced under
the earlier native convention that drops wall-clock fields from duplicate
decision captures. [PR #97 compatibility record](PHASE18_5BCD_ASSET_AMM_ACCEPTANCE.md#legacy-comparison) · [Native reproduction probe](PHASE18_2G_FINAL_HARDENING_ACCEPTANCE.md#native-btcethsol-compatibility)

## Regression and accessibility

| Check | Result |
| --- | --- |
| Focused Phase 18.5A–F | 122 passed, zero failures or skips. |
| Full backend | 3,914 passed, zero failures or skips, five existing warnings in 706.76 s. |
| Locked frontend install, typecheck, test and production build | 920 tests passed, zero failures, skips or cancellations. Install, typecheck and build passed. |
| Chromium Generalized PAPER, risk and advisories | 36 checks passed, including 10 asset-aware checks and the scoped accessibility scan. |
| Other Chromium research regressions | 16 Replay, 22 Portfolio and 29 Scenario vs Historical checks passed. Total Chromium checks across the four harnesses were 103. |
| Accessibility | Chromium keyboard navigation and accessible control names, status announcements and 390 px layout passed. The scoped asset settings and advisory axe-core 4.11.1 A/AA scans had zero violations and zero incomplete findings. |
| Static and dependency checks | Python compileall, Ruff syntax and undefined-name checks, and Git whitespace checks passed. The npm registry audit reported zero findings. |

The backend used CPython 3.12.14, Pydantic 2.13.5, FastAPI 0.142.2, Hyperliquid
SDK 0.24.0 and scikit-learn 1.9.1. Its warnings were the existing Starlette
TestClient deprecation, the deliberate invalid-concentration serializer
warning and three Pydantic instance-field deprecations. Frontend verification
used Node 24.19.0, npm 11.9.0 and Chromium 151. The build retained 15 TanStack
client-directive warnings and the Vite chunk-size warning.

Reproduce the focused suite with
`python -m pytest -q -rs --tb=short tests/test_phase185*.py` from `backend`.
Run the full backend suite with `python -m pytest -q -rs --tb=short`.
From the repository root, use
`python frontend/tests/browser-phase182.py --python /path/to/backend-python --output work/phase185-browser`.
The harness accepts `--asset-only` and `--axe /path/to/axe.min.js`.
Its metadata and delayed/stale failures are fixture driven. Eligibility,
PAPER execution and the HALT example use the real local application and worker.
The asset browser check starts a fresh fixture catalog. It captures the
real HALT response through Playwright's request routing so Chromium can
read all risk frames even if the page releases the response body.
The extended Scenario vs Historical check used the documented 60-second
Playwright allowance. [Prior browser commands and timeout recipe](PHASE18_2G_FINAL_HARDENING_ACCEPTANCE.md#executed-checks)

## Completion and Phase 18.6

**PASS for Phase 18.5A–F within bounded local PAPER research.** Phase 18.5
is scoped to one discovered perpetual, an explicit synthetic
scenario and locally simulated PAPER evidence. Operator classification and
advisory recommendations carry no exchange trading authority or guarantee of
profit. Advisory references depend on the active process and catalog.

Phase 18.6 can consume the qualified identity, evidence and binding contracts
after this PR's independent review. Future terminal work must keep observed
metadata, research assumptions and operational authority distinguishable
and preserve server-owned risk checks.

Audit 3.0 still tracks signed TESTNET lifecycle and reconciliation, durable
recovery, operational SDK reconnect and shutdown soak, longer provider and
calibration studies, authenticated historical acquisition and licensing,
cross-platform runtime and assistive technology, and reproducible environment
resolution. Wider-market execution, mainnet signing and production readiness
remain gated. [Audit 3.0 remaining limits](AUDIT3_FINAL_REMEDIATION_ACCEPTANCE.md#remaining-limits-and-verdict)
