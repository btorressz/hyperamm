# Phase 18.2 generalized PAPER research acceptance

Phase 18.2 adds single-market, hypothetical PAPER research for validated Hyperliquid Core and HIP-3 perpetual metadata. The implementation base is `8f9e695`, the merge of PR #87. The repository review covered the code and merged changes from PRs #84–#87, including the Audit 3.0 depth preflight, guarded TESTNET wire boundary, Phase 18 identity and provenance validators, discovery cache and native research execution. [Audit 3.0](../AUDIT_REPORT_3.0.md) · [Audit 3.0 acceptance](AUDIT3_FINAL_REMEDIATION_ACCEPTANCE.md) · [Phase 18.0 architecture](PHASE18_0_MARKET_UNIVERSE_ARCHITECTURE.md) · [Phase 18.0B acceptance](PHASE18_0B_ACCEPTANCE.md) · [Phase 18.1 acceptance](PHASE18_1_DISCOVERY_ACCEPTANCE.md)

| Workstream | Delivered |
| --- | --- |
| 18.2A | Versioned profile candidates derived from server-owned discovery metadata, using the existing canonical network and namespace identity. |
| 18.2B | Magnitude-dependent price normalization, exact lot flooring and preflight across the requested dataset. |
| 18.2C | All 13 scenario definitions adapted to explicit synthetic inputs and the existing isolated local PAPER engine. |
| 18.2D | Independent, immutable eligibility evidence with structured rejection reasons and a freshness deadline. |
| 18.2E | Two bounded research endpoints and a Generalized PAPER tab in the existing Simulation workspace. |
| 18.2F | Adversarial backend, TypeScript and Chromium coverage, financial comparisons with PR #87 and guards on signer and exchange order paths. |

## Reuse, enhancement and additions

Backend code owns admission, precision, feasibility and financial evidence. The browser captures a selection and assumptions, validates responses and renders status and local results.

| Approach | Components |
| --- | --- |
| Reuse | v2 Phase 18 identity, metadata, freshness and discovery service, Decimal bounds, price quantum and lot rules, scenario shapes, AMM and quote policy, simulation engine, local PAPER matcher, accounting, Risk Firewall and final quote authorization, shared worker and optional Redis coordination, existing API body limit and bounded JSON reader. |
| Enhance | Existing scenario builder and engine accept a separate generalized profile. Existing simulation service and executor dispatch that profile through the same worker. The market-universe router exposes a distinct research prefix. The Simulation workspace adds one tab, with its own ephemeral selection and the existing scenario catalog. |
| Add | Versioned profile, proposal, admission, fingerprint binding and result contracts. New TypeScript types and validators cover those contracts. Focused backend, frontend and browser tests exercise the new path. |

### Changed files

| Scope | Files |
| --- | --- |
| Backend contracts and precision | `backend/app/simulation/generalized_market_profiles.py`, `backend/app/simulation/market_profiles.py` |
| Backend engine and API | `backend/app/simulation/scenarios.py`, `backend/app/simulation/engine.py`, `backend/app/simulation/service.py`, `backend/app/simulation/executor.py`, `backend/app/api/market_universe.py` |
| Frontend | `frontend/src/api/client.ts`, `frontend/src/pages/Simulation.tsx`, `frontend/src/components/simulation/GeneralizedPaper.tsx`, `frontend/src/types/generalizedPaper.ts`, `frontend/src/utils/generalizedPaper.ts`, `frontend/src/utils/marketUniverse.ts` |
| Tests | `backend/tests/test_phase182_generalized_paper.py`, `frontend/tests/phase182-generalized-paper.test.cjs`, `frontend/tests/browser-phase182.py`, `frontend/tests/run.cjs` |
| Documentation | `CHANGELOG.md`, `docs/PHASE18_2_PAPER_ACCEPTANCE.md` |

## Identity, provenance and admission

Every profile uses `phase182-v1` with the `phase180b-v2` identity and normalized metadata attached. The profile carries venue, network, instrument class, DEX, canonical stable key, exchange-qualified coin, observed local ordinal, `szDecimals`, listing status, the bound v2 discovery decision, provenance, explicitly user-supplied synthetic reference and depth, the supported hypothetical model and its explicit research limitations. A profile is a candidate marked `REQUIRES_ADMISSION`. The separate decision has scope `LOCAL_PAPER_ONLY`, `authority=NONE` and `execution_eligible=false`. The existing discovery API remains read-only and reports `paper_research_eligible=false` for every instrument.

Admission evaluates exact identity on the configured network, a current complete discovery generation and a listed record with fresh official metadata. Pinned research metadata, stale retained generations, invalid clocks, delistings, network mismatches and missing records fail closed. The request explicitly selects `HYPOTHETICAL_LINEAR`. The backend checks reference precision, positive order and inventory quantities, scenario depth, representability of the generated flat-inventory quote ladder and bounded configuration. Each outcome contains its evaluation time, a bounded reason and explanation, the failed check when applicable, available profile evidence and the scope and authority flags. Eligible evidence has a validity deadline and all three input fingerprints.

| Fingerprint | Bound evidence |
| --- | --- |
| Metadata | The v2 canonical observation, including source, status, observed ordinal and timestamp. |
| Profile | Identity, semantic metadata, contract version, synthetic reference and depth, and hypothetical economic assumptions. The observation clock and ordinal are tracked in the metadata fingerprint. |
| PAPER configuration | Normalized proposal, profile fingerprint, engine version, generated dataset fingerprint and effective strategy, agent, risk and simulation settings. |
| Result | Configuration fingerprint, normalized proposal and complete native simulation result. The result envelope retains the evaluation time and full metadata observation as separately captured evidence. |

Core and HIP-3 share the same admission rules. Network, perpetual class and DEX namespace remain part of every engine market identifier through simulation, accounting and receipts. The existing `ResearchPerpMarketId`, `MARKETS` and `phase146-v1` contract retain their BTC/ETH/SOL scope.

## Precision and feasibility

Sizes use lot precision 0–6. The synthetic reference must be representable. Internally the quote compiler uses the finest allowed decimal grid for the instrument. Before risk and reconciliation, every executable limit is rounded at its own price magnitude using the existing five-significant-figure and decimal-place rules, with integer prices supported by the existing rule. Bids round down and asks round up. Size floors against both the proposed size and the original price-times-size, using directed Decimal arithmetic for the notional ceiling. The book uses strictly ordered positive five-level sides and applies the same conservative normalization. Lot collapse and duplicate rounded levels in the flat-inventory preflight reject the proposal. During the actual run, position and risk transforms may retire levels that shrink below one lot or collapse onto an already retained same-side price.

Synthetic depth scales from the supplied top-level quote notional. Quote and virtual pool placement are anchored to the synthetic reference with fixed bounded research defaults. Initial inventory is flat. Soft and hard inventory limits and per-side liquidity are derived from the order-notional assumption, floored to asset precision and constrained by the existing firewall. These bounds belong to the isolated run. Each proposed frame is validated before worker dispatch. The worker rebuilds and verifies the captured proposal and rechecks freshness before constructing the engine run.

All 13 existing scenarios share the established price paths, synthetic book imbalances and shocks, references and funding-stress rates. Flash and liquidity-shock proposals must include their event frame. Funding stresses require a hypothetical interval short enough to accrue inside the requested window. Fixture coverage includes all scenario families, all seven quantity precisions, low and high price magnitudes, significant-digit transitions, coarse ticks, lot collapse, extreme bounded volatility and Decimal overflow.

## Local PAPER economics and execution

The user supplies the reference price. The nominal reference is independent of any provider quote. The engine generates hypothetical books, mark/oracle and reference values, and funding rates. The use of the existing source labels inside consensus represents synthetic scenario data. The model uses hypothetical quote accounting units, linear price-times-quantity P&L and full-notional reservation. The API accepts hypothetical maker and taker fees from 0 to 100 bps and an optional synthetic funding interval in seconds. With default assumptions the fee and funding entries are zero. The browser uses zero modeled fees and offers optional one-second hypothetical funding.

The existing crossing-only adapter owns matching and simulated fills. Depth drives the book and policies. The crossing-only model fills at the local order price after a crossing and has no queue, depth-consumption or latency model. Product-specific collateral, margin, settlement and exchange fee or funding conventions remain unverified. The strategy, risk, accounting, telemetry and orders are freshly instantiated in the existing worker for each isolated run. HTTP cancellation leaves the current worker job in ownership until actual completion. The worker allows one active local job shared with the established research workflows.

The Phase 18.2 API passes a research proposal and observation evidence to the existing isolated engine. Its route dependencies are the server-owned read-only catalog and the research executor. Accepted and rejected API tests install failing guards on venue adapter construction, submit/replace/cancel, SDK order/bulk-order calls and wallet-key derivation. Accepted runs succeed with the operational runtime absent. Instrumented mutation tests confirm rejected inputs never dispatch and an expired snapshot cannot reach engine start. Chromium captures only generalized PAPER POST requests on the added workflow. The guarded TESTNET adapter has no source diff from PR #87.

## API and frontend

Both endpoints are local, no-store POST routes under `/api/v1/generalized-paper`. The catalog uses the existing `MARKET_UNIVERSE_ENABLED=true` opt-in and `MARKET_UNIVERSE_NETWORK` selection.

| Route | Contract |
| --- | --- |
| `/eligibility` | Accepts the canonical identity, explicit version and bounded synthetic assumptions. Returns eligible, rejected or unavailable evidence. |
| `/run` | Accepts the same proposal plus the three expected fingerprints. Refreshes or rereads discovery, recomputes admission and feasibility, verifies the bindings, and returns the local PAPER result. The worker revalidates freshness and the captured fingerprints before running. |

Structured decision statuses are 200 for eligible evidence, 422 for invalid or infeasible input, 409 for changed fingerprints and 503 for unavailable or stale evidence. Shared worker capacity returns 429, coordination unavailability returns 503 and the existing 64 KiB preparse body guard returns 413. A run uses 2–120 frames and retains at most 120 trace points and the engine's bounded order, fill and ledger collections. The JSON result budget is 2 MB. Request schemas reject unexpected authority, credential, admission and runtime fields. Neither API accepts client eligibility flags, a client profile or a venue execution mode.

The Simulation tab lists discovery candidates with their qualified names and status. It labels synthetic inputs and hypothetical quote units and disables runs for rejected, unavailable, retired or expired evidence. It validates the runtime versions, canonical identity, provenance, status, fingerprint bindings and displayed financial fields before making the result available. BTC/ETH/SOL selection continues through the existing scenario tab.

## Financial invariants and PR #87 comparison

An isolated `8f9e695` worktree and this feature tree ran the existing Phase 17.3 native 40-frame `FLASH_MOVE` fixture with modeled fees and one-second funding. Allocations were 40,000 quote units for BTC, 35,000 for ETH and 20,000 for SOL, with 5,000 held in reserve. The comparison captured the native profiles and strategies, native scenario captures, dataset and result fingerprints, full receipts, orders, fills and ledgers, AMM base-to-quote and quote-to-base outputs, portfolio reconciliation and risk evidence. The canonical projection matched byte for byte.

| Market | PAPER fills | Fees in quote units | Signed funding in quote units | Native result fingerprint |
| --- | ---: | ---: | ---: | --- |
| BTC | 2 | 0.235668631 | −0.00047649500 | `2cd27fd5f735b56bc901b973af54071dc6167d8fdb9df93f5c90fe74a9c7ad80` |
| ETH | 8 | 0.942527978 | −0.00191180880 | `1cc80c654525f9eafeddde6a89215ba1d8e6be8ef15168f1c5c35902b1e9e6a0` |
| SOL | 0 | 0 | 0 | `791d9079cd2f319046dbe1422575cc8bcb6c1192f86d992f2c81e240a6c62f54` |

Combined projection SHA-256 `0e240d17e68ddf9b9869ad3986d7b4d238cf094f74251dd39da96567d16808a0`. The 39 native datasets generated separately across all three profiles and 13 scenarios also matched, with a combined fingerprint of `60e8b6a096f6087142a9996b0a00558ded348e1a884d4116d3d68b78880cf7e2`. [Native fixture](../backend/tests/test_phase173_accounting.py)

Generalized Core DOGE and HIP-3 `xyz:GOLD` provider-shaped fixtures each complete a deterministic 40-frame flash scenario with four local fills. Repeated runs match on the full simulation result and result fingerprint. Tests reconcile signed fill inventory, realized and unrealized P&L, fees, funding and starting-to-ending equity. [Generalized fixture and security tests](../backend/tests/test_phase182_generalized_paper.py)

## Provider evidence and limitations

A bounded Mainnet probe through the existing official SDK metadata service returned 566 normalized records. Mainnet DOGE (`szDecimals=0`) and `xyz:XYZ100` (`szDecimals=4`) admitted two local 40-frame flash scenarios with four simulated fills each. The user-specified hypothetical anchors were 0.1234 and 1000 respectively. Provider evidence covers identity, listing and precision for that observation. All scenario data and financial results are synthetic. Testnet isolation is covered by fixtures. The Phase 18.1 full-Testnet catalog-capacity and name-grammar limits remain open.

Incomplete, delisted and stale observations, unsupported scenario mechanics, infeasible coarse-tick books and sub-lot quantities fail closed. Acceptance is single-market and crossing-only. Product-specific collateral, verified margin, cross-currency exposure, settlement and cross-market HIP-3 portfolio risk are prerequisites for Phase 18.3 development. Operational market support, signed TESTNET acceptance, durable worker recovery, authenticated historical data and licensing, sustained provider and operational SDK lifecycle soak, and cross-platform lifecycle and assistive-technology verification retain their earlier dispositions. The historical picomatch advisory is recorded in Audit 3.0. [Open Audit 3.0 gates](AUDIT3_FINAL_REMEDIATION_ACCEPTANCE.md#remaining-limits-and-verdict) · [Phase 18.1 provider gates](PHASE18_1_DISCOVERY_ACCEPTANCE.md#readiness-and-open-gates)

## Executed checks

| Check | Observed result |
| --- | --- |
| Final focused backend `tests/test_phase182_generalized_paper.py` | 51 passed, zero failed or skipped. |
| Phase 18 contracts, discovery and Audit 3.0 targeted recheck | 219 passed, zero failed or skipped, one existing warning. |
| Broader targeted backend regression | 1,584 passed, zero failed or skipped, two existing warnings. Includes native research and simulation, AMM, precision and strategy, PAPER and guarded execution, accounting, portfolio, risk and discovery. |
| Full backend `python -m pytest -q -rs --tb=short` | 3,573 passed, zero failed or skipped, two existing warnings, 636.12 s. The optional ML coefficient-export test ran. |
| Locked frontend `npm ci`, `npm run typecheck`, `npm test`, `npm run build` | All passed. 830 tests passed with zero failures, skips or cancellations. Vite built 246 modules. The focused Phase 18.2 frontend file contributed 16 cases. |
| Phase 18.2 Chromium | Six workflows passed on the final source. Covered Core and HIP-3 completion, delisting and precision rejection, expiry, native selector retention and allowed POST paths. |
| Local scenario sweep | All 13 scenarios completed on a HIP-3 fixture. Both 120-frame boundary runs completed. The largest serialized result was 718,172 bytes against the 2 MB cap. |
| Historical Replay Chromium | 16 workflows passed, zero unexpected console errors. |
| Extended Scenario vs Historical Chromium | 29 workflows passed on the final rerun and on the isolated PR #87 baseline. The initial feature run timed out in the injected malformed source-clock probe after 24 completed workflows. The final rerun passed that probe. |
| `npm audit` and `npm audit --omit=dev` | Both returned zero findings on this lockfile in this environment. Earlier Audit 3.0 runs reported the picomatch development advisory `GHSA-fc5q-39xc-vjpf`; no dependency files changed in this phase. [Advisory](https://github.com/advisories/GHSA-fc5q-39xc-vjpf) |

Python 3.12.14 with FastAPI 0.142.2, Starlette 1.7.0, Pydantic 2.13.5, pytest 8.4.2, Hyperliquid SDK 0.24.0, Redis client 6.4.0, fakeredis 2.40.0 and scikit-learn 1.9.1. The existing Starlette TestClient HTTPX deprecation and deliberate invalid-concentration Pydantic serialization warning appeared in the backend regressions. Node 24.19.0, npm 11.9.0, TypeScript 5.9.3, Playwright 1.65.2 and Chromium 151. The existing Zustand test storage notices, TanStack client directive notices and large bundle warning appeared in frontend checks.

Run the fixture-backed Chromium harness from the repository root with `python frontend/tests/browser-phase182.py --python "$(command -v python)" --output work/phase182-browser` after installing Playwright and the locked frontend dependencies. It uses the actual API and worker and confines fixture injection to the read-only metadata provider.

## Phase 18.3 readiness

**PASS for bounded, single-market hypothetical PAPER research.** Phase 18.3 development may proceed with separate product-specific collateral, exposure and margin evidence. Production execution, signed HIP-3 orders and broader shared-capital research remain separate acceptance gates.
