# Phase 18.4E–F advisory research acceptance

The feature starts at merged PR #94, commit `d4341293a07d112d5d80222290def02e908bd77f`. The pre-edit review followed the first-parent merges for PRs #84–#94 and inspected discovery, PAPER admission and worker ownership, the six-agent supervisor, risk and quote authorization, the three advisory evaluators and the Simulation workspace. Compatibility runs also used merged PR #92, commit `bb07f717e707ec21b005b9692992b5bd90bdac07`. [PR #94](https://github.com/btorressz/hyperamm/pull/94) · [PR #92](https://github.com/btorressz/hyperamm/pull/92) · [Audit 3.0](../AUDIT_REPORT_3.0.md) · [Phase 18.2G](PHASE18_2G_FINAL_HARDENING_ACCEPTANCE.md) · [Risk architecture](PHASE18_3_MARKET_RISK_ARCHITECTURE.md) · [Phase 18.3 acceptance](PHASE18_3_FINAL_ACCEPTANCE.md) · [Phase 18.4B–D acceptance](PHASE18_4BCD_AGENTS_ACCEPTANCE.md)

## Milestone inventory

| Phase | Delivered and reviewed |
| --- | --- |
| 18.4A | Immutable `phase184a-v1` advisory contracts and authority boundaries |
| 18.4B | Operation-specific Market Eligibility using discovery and PAPER admission |
| 18.4C | Official public and synthetic PAPER Funding/Basis using `phase184bcd-v1` captures |
| 18.4D | Quote Economics using attributed simulated fills, fees, funding, risk and mature markouts |
| 18.4E | Application-owned coordinator, bounded API, ephemeral PAPER receipts, runtime-validated Simulation panels |
| 18.4F | Independent financial and provenance tests, lifecycle probes, Chromium and accessibility checks, historical comparisons and final acceptance decision |

PR #94 already supplied the three evaluators, their evidence digests and the bounded observations adapter. Discovery owns catalog generations and the Phase 18.3 financial metadata. The existing worker and admission route already validate completed PAPER output, and Simulation supplies the canonical market selector and risk controls. Integration required one lifecycle owner, a server-side selector for completed results, a transport contract and a React view. The audit focused on publication races, equal-name markets, source-clock ambiguity, false fill attribution, cost rounding, expiry and the separation of advisory findings from trading authority.

| Architectural emphasis | Changes |
| --- | --- |
| Reuse 45% | Canonical discovery, existing bounded SDK transport, PAPER assessor and worker, Phase 18.3 financial evidence, advisory evaluators, fee and funding functions, markouts, Simulation and React Query |
| Enhance 35% | Application lifecycle, generalized PAPER response headers, additive advisory metrics and typed provider failures, existing Simulation and browser harness |
| Add 20% | Coordinator and bounded receipt lookup, unified response, validated panels, independent API and financial acceptance |

### Implementation files

| Files | Responsibility |
| --- | --- |
| `backend/app/agents/advisory_coordinator.py` | Selectors, coherent snapshots, publication checks and completed PAPER receipts |
| `backend/app/agents/advisory_contracts.py`, `funding_basis.py`, `quote_economics.py` | Additive display values bound to existing source captures |
| `backend/app/market_data/advisory_market_observations.py` | Provider failure codes from the existing bounded adapter |
| `backend/app/api/market_universe.py`, `backend/app/main.py` | API and configured-network lifecycle |
| `frontend/src/types/advisory.ts`, `utils/advisory.ts`, `api/client.ts`, `types/generalizedPaper.ts` | Wire shape, exact Decimal validation, digest checks and receipt handoff |
| `frontend/src/components/simulation/GeneralizedPaper.tsx`, `GeneralizedPaperAdvisory.tsx`, `frontend/src/phase1331.css` | Three research panels and evidence invalidation |
| `backend/tests/test_phase184e_advisory_api.py`, `test_phase184f_final_acceptance.py`, `frontend/tests/phase184-advisory.test.cjs`, `run.cjs`, `browser-phase182.py`, `browser-phase1641.py` | Acceptance and regression coverage |
| `docs/PHASE18_4_FINAL_ACCEPTANCE.md`, `PHASE18_4_ADVISORY_ARCHITECTURE.md`, `ROADMAP.md`, `CHANGELOG.md` | Release boundary and Phase 18.5 handoff |

## Coordinator and API

`POST /api/v1/market-universe/advisory` uses the existing local-only API and 64 KiB request cap. It accepts the canonical identity, expected catalog fingerprint and one of six operations. Optional selectors are a matching PAPER proposal for admission research, `OBSERVED` or `PAPER` funding, a completed PAPER receipt, and a retained trace sequence with explicit holding duration, closing liquidity, exit slippage and inventory rates. The endpoint resolves official metadata, public observations and risk evidence itself. Selectors cannot supply evidence, fills, recommendations, risk outcomes or authority fields.

After a worker result passes the existing admission, result and response-size checks, the run response includes `X-Paper-Advisory-Receipt`. The response body retains its existing serialization and economic fingerprints. The coordinator holds up to eight serialized results of at most 2 MB each. A receipt expires by its original admission deadline or five minutes after receipt, whichever comes first, and can only be used with the original active generation and identity. It disappears on eviction or restart. The endpoint returns available trace sequences and uses the selected frame's actual Risk Firewall state. Validated retained evidence supplies fill and economic values. The receipt alone supplies no permission.

The `phase184e-v1` response contains the canonical identity, evaluated time, valid-until time, snapshot digest, one `phase184a-v1` context and the applicable `phase184bcd-v1` agent results. The context binds catalog, metadata, PAPER configuration and risk model fingerprints where applicable. Results cite bounded source references that include provenance, financial units, acquisition and event clocks, expiry and limitations. Relative to PR #94, the new optional display fields expose the consumed mark, oracle and midpoint, two submitted best prices, exact entry and modeled exit fees in hypothetical quote units, and attributed fill and mature markout counts. The legacy 18.4A wire shape omits these extensions. The browser checks response and context digests as well as the schema and bindings. A digest gives content integrity. Provider authenticity comes from the server capture boundary.

Catalog, identity, worker capacity and binding errors use the existing HTTP `detail` envelope with a code and bounded message. Invalid selectors use normal 422 validation. Within a valid snapshot, missing or expired PAPER evidence, unsupported cohorts and provider availability are explicit issues, with independent agent status, explanation and confidence. A provider rate limit can coexist with available Quote Economics. Metadata-only requests acquire no market observations. Responses carry `Cache-Control: no-store` and are capped at 64 KiB.

The application owns one public observations adapter for its configured discovery network. The coordinator captures metadata and current financial evidence, awaits optional public evidence, then evaluates within bounded worker capacity and rechecks the active catalog and clock. The response expires at the earliest cited source or context deadline. If a cited source expires during evaluation, the coordinator can evaluate again using the changed clock before rejecting the result. Every published snapshot passes `AdvisorySnapshot.validate_at()`. Existing public transport limits, cache capacity, per-market single-flight and rate-limit backoff apply. Shutdown drains shared work and clears in-memory state.

## Simulation and accessibility

With `MARKET_UNIVERSE_ENABLED=true` on the configured `MARKET_UNIVERSE_NETWORK`, open **Simulation → Generalized PAPER** and select a qualified Core or HIP-3 market and choose one of the six operations in Market Eligibility. Run the existing PAPER eligibility and simulation controls to complete a standard, hypothetical-risk or source-constrained scenario. The Funding/Basis panel has separate observed and synthetic sections. Quote Economics loads the completed run's retained cohort list and requires explicit modeling inputs. All numeric values come from the validated backend fields. Positive and negative residual edge are described as hypothetical. Cohort HALT remains an unsupported economics finding.

Quote, funding and suitability requests use separate React Query owners. Changing network, market, DEX, catalog generation, risk settings, PAPER assumptions, completed run or quote cohort retires the associated display and pending requests. A browser timer retires expired snapshots. The panels label text announcements, forms, section headings, evidence links and metric rows. Source details show a provider event time only when the source supplied one and show scenario time separately.

## Independent financial and provenance review

| Area | Evidence |
| --- | --- |
| Market Eligibility | Core, HIP-3 and same-symbol namespaces, delisting, missed precision, stale catalog, rejected or mismatched research modes, and absent prerequisites. The API imports capture from the existing PAPER assessor. Browser advisory suitability never enables PAPER actions. |
| Funding/Basis | Two source-clock types, exact signed basis and genuine two-sided L2 midpoint, wrong coin and network, missing mark or oracle, stale and future book events, negative and zero rates, history duplicates or contradictions, hourly live convention and explicit PAPER intervals. Posted historical funding is distinct from the current rate, which can change before settlement. |
| Quote Economics | Real isolated worker fills independently reconciled with rational arithmetic for submitted bid/ask, capture, reference notional, entry fees, maker and taker residual exit fees, signed carry, inventory expansion, adverse movement, slippage, break-even and residual edge. Deterministic fixtures exercise positive, negative and break-even, absent or immature fills, mismatched source and order receipts, margin units, HALT and retirement. |
| Provenance and publication | Wire forgery tests reject client sources, fabricated snapshots, supplied result objects, claimed digests and authority escalation. A digest cannot replace the opaque receipt. Two DEXs with the same instrument label cannot share a receipt. Tests check freshness after public acquisition and observe the later publication clock passed to `validate_at()`. |
| Lifecycle | Simultaneous Core and HIP-3 observations, shared per-market acquisition, bounded cache reuse, caller cancellation, provider backoff and shutdown are exercised. A catalog refresh during acquisition invalidates the old request. Closing the coordinator removes receipts. Delayed browser results are discarded when the selection changes. |

Captured spread is signed against the accepted fill-time synthetic reference. Adverse selection uses the difference between that reference and the matured midpoint, so it does not charge the fill-to-reference move twice. The independent oracle uses a median of eligible scenario core sources, actual attributed fill quantities, the existing five-second fixture horizon and integer counts of scheduled boundaries. Capture rounds toward negative infinity and cost components toward positive infinity to eight decimal places in bps. The denominator is executed reference notional, separate from quoted notional and modeled margin headroom. Positive funding implies longs pay. Missing required evidence produces an indeterminate result with zero confidence. A modeled residual close and inventory rate are explicit assumptions.

## Official public provider observations

Read-only validation at approximately 2:42 a.m. Pacific on November 19, 2026. Mainnet discovery found 567 records across 11 namespaces. The checked Core and HIP-3 instruments were listed. The Mainnet adapter made two captures for each, with a cache-hit round in between and a repeat after ten seconds. Public Testnet Core BTC was verified through scoped public metadata. A follow-up full Testnet catalog request confirmed `CATALOG_CAPACITY` for its inventory, which exceeded the existing namespace cap. Delisted Mainnet Core `AI` was rejected by fixture-free metadata validation with zero requests to the advisory provider for that market.

| Market | First current hourly rate | Mark | Oracle | L2 midpoint | Posted history |
| --- | ---: | ---: | ---: | ---: | ---: |
| Mainnet Core BTC | `-0.0000036446` | 63819.0 | 63854.6 | 63818.5 | 24 |
| Mainnet HIP-3 `xyz:XYZ100` | `0.000008319` | 27669.0 | 27660.0 | 27669.5 | 24 |
| Testnet Core BTC | `-0.0007196585` | 62221.0 | 63854.9 | 62199.0 | 24 |

The run produced seven available observations from five acquisitions and two cache reuses. All 30 public SDK sessions closed, including 15 advisory requests, 13 Mainnet discovery requests and two Testnet metadata requests. The current context had only a receipt clock, with receipt ages from 812 to 1,355 ms when inspected. L2 included provider event times, 386 to 869 ms before receipt. History receipt age was 0 to 498 ms and included hourly provider timestamps. For example, the first Mainnet history window ran from approximately 3 a.m. Pacific November 18 through 2 a.m. Pacific November 19. No real rate limit occurred in this bounded sample. The deterministic tests exercise 429 backoff, timeouts and cancellation. No private account or signed API calls occurred. This sample does not establish sustained provider availability.

## Historical compatibility and trading authority

Native captures matched PRs #92 and #94 across 39 dataset fingerprints, three 40-frame BTC/ETH/SOL runs and the aggregate portfolio. They included market and reference snapshots, quote ladders, fill and markout evidence, inventory, accounting, fees, funding, equity, P&L and Risk Firewall decisions. The native output reproduced the published digests below. The same 240 evaluations also matched all six agents' states, confidence, multipliers and fingerprints, including Predictive Adverse Selection SHADOW, after recursively dropping the wall-clock `updated_at` fields from the duplicate supervisor captures. Direct authorization capture excluded wall-clock `created_at`.

| Native check | Digest |
| --- | --- |
| Dataset matrix | `e97b675557f104e1ad2bfe3713133db88c20dbc2eece9e71a3d7ed4467f05abe` |
| Portfolio | `e51a1579d079429ed6ee123e120a7d46bc38f4ebd73e7c90283ff97ab53c9417` |
| Combined native evidence | `22eed4a5c0d67fa94b0e8780e9cbfd3af50276cab4e2b5e2a22e581b449a34ad` |
| Final authorizations | `ef990233ca2afd8d2662db40bb3e346908f378fddf43d275ece2ccfb344b65a9` |
| Six-agent supervisor outputs | `308a110e3245e593cae3a6386d9ed26377be9a66dda8b3f8f55912a812aa6a2b` |

The Generalized PAPER probe uses the same fixed inputs on the three trees. It compares 26 standard runs over all 13 scenarios for Core `DOGE` and HIP-3 `xyz:GOLD`, and 12 opt-in runs over QUIET, HIGH_VOLATILITY and FLASH_MOVE in both risk modes. All runs use 40 frames, synthetic prices 0.1234 or 2500, 7/13 bps maker/taker fees, two-second funding and a fixed market/admission/worker clock of 4 a.m. Pacific on November 18, 2026. The risk runs use 10,000 PAPER quote units of capital and the existing risk fixtures, with a −2,000 bps price shock, 300 bps collateral loss, 50 bps capital reduction, 15 bps funding surcharge and 10 bps fee surcharge. The comparison covers full economic result bytes, underlying result fingerprints, accounting and risk decisions. All 38 objects matched byte for byte in each tree. The SHA-256 of the compact JSON array with sorted keys and a trailing line feed is `073ada31133bda263c678b12707b3c018a08d393b7943ccb933f9791b92c2804`. A separate run with the same matrix and no stress assumptions also matched across trees with digest `e0d773be577f71afc2e34a4c8c38253b2c4baf88cb0010a63cc18162ee9090ef`. PR #94 reports `9b82ad883b63a737fc22be0105dd6f7d9e69ea5bcec75776ad46432e2579b219` with its original capture and aggregation. The direct tree comparisons use the current probe's identical fixture and serialization in each tree.

Tests instrumented key derivation, wallet signing, exchange execution and cancellation, leverage updates and the native TESTNET adapter, with zero calls. A separate fixture fails if an advisory calls the material supervisor, Risk Firewall or FinalQuoteAuthorization. Existing quote authority remained final, including real PAPER HALT producing a neutral Quote Economics result. Advisory requests did not mutate accounting or allocate capital across markets. The six-agent supervisor, its aggregation, the authorization path, collateral valuation model and accounting implementation retain their existing call sites.

## Regression and decision

| Check | Measured result |
| --- | --- |
| Phase 18.4A–F and supervisor static tests | 102 passed, zero failures or skips, three existing warnings |
| All Phase 18 backend tests | 419 passed, zero failures or skips, four existing warnings |
| Full backend `python -m pytest -q -rs --tb=short` | 3,792 passed, zero failures or skips, five existing warnings, 916.55 s |
| Frontend clean install, typecheck, node:test and production build | All passed. 889 tests, zero failures, skips or cancellations. One Zustand storage notice, 15 TanStack client directive warnings and one Vite chunk-size warning. |
| Phase 18.2–18.4 Chromium | 26 checks, including three browsers exercising the real API and PAPER worker with controlled public metadata and observations |
| Replay, portfolio and comparison Chromium | 16 replay, 22 portfolio and 29 comparison workflows passed. Together with the Phase 18 harness, this is 93 workflow checks. |
| Accessibility | Phase 18.4 advisory axe-core 4.11.1 scan reported zero WCAG A/AA violations at 390 px, with zero incomplete checks. Chromium verified accessible names, the accessibility tree, keyboard tab sequence, progress and expiry, table row headers and absence of clipping. The separate Audit 3.0 accessibility runner also passed 32 route/viewport axe scans and its 200% zoom check with zero reported violations. |
| Static analysis | Python compileall, Ruff syntax and undefined-name checks on the edited Python files, TypeScript typecheck and git diff whitespace checks passed. |
| Dependency registry | `npm audit` and `npm audit --omit=dev` each returned zero findings in this run. |

The first backend regression run found that the original receipt implementation imported the Python `secrets` module from the advisory package, which matched the existing no-secret-configuration source guard. The receipt generation now uses OS random bytes. The existing guard passed with the same 256-bit receipt entropy. The installed backend includes the optional scikit-learn test path. Other backend warnings are the existing Starlette TestClient deprecation and the deliberate invalid-concentration serializer warning. The initial historical replay run hit Chromium's response-body inspection error on a real 422. The harness now clones the actual response in the page, using the same mechanism as successful replays. The retry verified the unchanged structured error and UI assertions. The comparison harness used the existing documented 60-second Playwright allowance. [Browser timeout recipe](PHASE18_2G_FINAL_HARDENING_ACCEPTANCE.md#executed-checks)

Use the existing browser harness from the root with `python frontend/tests/browser-phase182.py --python /path/to/backend-python --output work/phase184-browser`. Add `--axe /path/to/axe.min.js` for the scoped accessibility scan. The standalone command uses Playwright and Chromium. Browser fixtures control external observations and the catalog replacement while PAPER admission, simulation and quote attribution run through the application. The public provider probe above was separate.

**Decision.** Phase 18.4E–F passes acceptance for the bounded local PAPER advisory workflow. The three integrated agents join the six existing agents in the research architecture. The existing supervisor, Risk Firewall and final authorization path retain their authority. This fixture, browser, compatibility and public-observation evidence leaves production trading certification open.

### Boundaries and Phase 18.5 handoff

The local discovery catalog may be disabled or expire. Testnet discovery stays subject to the existing inventory capacity. Unsupported public fields and funding schedules, unretained quotes, absent or immature fills and exhausted modeled headroom have explicit unavailable or unsupported findings. Forecast funding, real balances, margin netting, liquidation estimates and realized performance outside the PAPER ledger remain outside this scope. The application uses one configured network at a time. Browser network replacement tests exercise invalidation of the previous configuration.

Audit 3.0 gates still apply to signed Testnet submission and reconciliation, operational network-fault soak and durable financial recovery. Cross-platform lifecycle acceptance, remote operational security, cost-policy calibration and empirical model calibration are separate acceptance work. Phase 18.4 supplies bounded local research evidence for Phase 18.5 asset-aware simulation. Reuse the canonical identity, catalog and validated Phase 18.3 risk context. Preserve synthetic PAPER prices and independent final quote authorization. [Audit 3.0 final remediation](AUDIT3_FINAL_REMEDIATION_ACCEPTANCE.md)
