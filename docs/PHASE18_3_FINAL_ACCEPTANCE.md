# Phase 18.3E–F final acceptance

The implementation starts at merged PR #91, `27713d0e51d5399bd5ded43b969a3446b6b43a7d`. Review followed the first-parent history through Audit 3.0 remediation (#84), the Phase 18.0 contracts and hardening (#85–#86), discovery (#87), Generalized PAPER (#88), financial provenance (#89) and risk foundation (#90). The checks exercise the current routes, provider normalization, Decimal model, simulation worker and UI. [PR #91](https://github.com/btorressz/hyperamm/pull/91) · [Audit 3.0](../AUDIT_REPORT_3.0.md) · [Audit remediation](AUDIT3_FINAL_REMEDIATION_ACCEPTANCE.md) · [Phase 18 architecture](PHASE18_0_MARKET_UNIVERSE_ARCHITECTURE.md) · [18.0B acceptance](PHASE18_0B_ACCEPTANCE.md) · [18.1 acceptance](PHASE18_1_DISCOVERY_ACCEPTANCE.md) · [18.2 acceptance](PHASE18_2_PAPER_ACCEPTANCE.md) · [18.2G acceptance](PHASE18_2G_FINAL_HARDENING_ACCEPTANCE.md)

| Phase | Delivered evidence |
| --- | --- |
| 18.3A | Versioned asset, collateral, margin declaration and blocked risk-readiness contracts. |
| 18.3B | Normalized public collateral mapping, margin policy, timestamps and source status in a discovery generation. |
| 18.3C | Decimal exposure, margin, headroom, leverage and stresses for one market with a separate hypothetical budget. |
| 18.3D | Optional modeled risk on the existing local PAPER worker and Risk Firewall, with per-frame and final evidence. |
| 18.3E | Read-only financial evidence lookup and three research modes in the existing Generalized PAPER workspace. |
| 18.3F | Public metadata validation, independent financial and adversarial acceptance, and compatibility comparisons against #91 and #89. |

Earlier formulas and the current integration are described in the architecture and Phase 18.3B–D acceptance. [Risk architecture](PHASE18_3_MARKET_RISK_ARCHITECTURE.md) · [18.3B–D acceptance](PHASE18_3BCD_RISK_IMPLEMENTATION_ACCEPTANCE.md)

## Reuse, enhancements and additions

| Architecture target | Delivered work |
| --- | --- |
| Reuse 50% | Market identities, discovery ownership and freshness, Pydantic financial models, Decimal validation and fingerprints, existing eligibility and run routes, worker, simulation, six agents, AMM, Firewall, final quote authorization, PAPER matcher and accounting. Reuse the React workspace, API client, response budget reader, controls and browser harness. |
| Enhance 40% | Expose one selected market's risk evidence through the discovery router. Reuse the risk engine's source policy checks for available modes. Extend the existing form and results and tighten typed validation, request ownership and expiry. Reject a provider token symbol that collides with the reserved PAPER accounting unit. |
| Add 10% | Versioned lookup envelope, TypeScript risk contracts and validators, a focused risk UI component, independent backend acceptance cases and this report. |

| Changed files | Scope |
| --- | --- |
| `backend/app/api/market_universe.py`, `backend/app/risk/market_risk_engine.py`, `backend/app/market_data/market_risk_metadata.py` | Selected-market lookup, shared support checks and reserved-unit guard |
| `frontend/src/api/client.ts`, `frontend/src/types/generalizedPaper.ts`, `frontend/src/types/marketRisk.ts`, `frontend/src/utils/generalizedPaper.ts`, `frontend/src/utils/marketRisk.ts` | Bounded requests, risk contracts and validation |
| `frontend/src/components/simulation/GeneralizedPaper.tsx`, `frontend/src/components/simulation/GeneralizedPaperRisk.tsx`, `frontend/src/phase1331.css` | Configuration, evidence, accessible status and responsive presentation |
| `backend/tests/test_phase183ef_risk_api.py`, `frontend/tests/phase182-generalized-paper.test.cjs`, `frontend/tests/browser-phase182.py` | Adversarial API, independent tier oracle, TypeScript and Chromium coverage |
| `docs/PHASE18_3_FINAL_ACCEPTANCE.md`, `docs/PHASE18_3_MARKET_RISK_ARCHITECTURE.md`, `CHANGELOG.md` | Acceptance and architecture |

## API, browser validation and scope

`GET /api/v1/market-universe/risk-evidence` accepts the selected network, instrument class, DEX, unqualified market name and discovery catalog fingerprint. A `phase183e-v1` response ties normalized `phase183b-v1` financial evidence to the active catalog and metadata fingerprints. It carries source and evaluation times, a validity deadline, source fingerprint, model version, supported research margin modes and a bounded source-constraint reason if the observed policy is unusable. A replaced or expired catalog returns 409. The response is read-only with no-store caching and the authority scope `LOCAL_PAPER_ONLY`, `authority=NONE` and `execution_eligible=false`.

Collateral, margin and whole-observation statuses remain explicit. A missing market mode can coexist with an observed collateral token and tier schedule. An observed HIP-3 multi-tier policy can still be unsupported for this formula. A provider token using the reserved `HYPOTHETICAL_QUOTE` symbol now normalizes to an unresolved collateral observation. Previously it could resolve as spot metadata and then fail when constructing the exchange-asset financial unit. The guard introduces a bounded unsupported state for that collision.

The existing `POST /api/v1/generalized-paper/eligibility` and `/run` routes accept the optional `research_risk` proposal. They continue to resolve financial source data server-side and check the bound market, catalog, profile, configuration and risk model fingerprints. Eligibility for local research never establishes account or execution readiness. Stale evidence and forged source/collateral, leverage, authority and shared-capital claims fail before execution. The worker rechecks the deadline and generation before the engine starts, then retains the captured evidence for a started run.

The TypeScript client bounds the lookup to 16 KiB and retains the 2 MB PAPER response limit. It validates wire versions, identity, timestamps, authority, token ID and denomination, tier order, declared settings, digests, risk decisions and bounded stress and frame arrays. Risk-input decimals stay as strings. Exact comparisons validate bounds and contradictory leverage assumptions. The browser displays computed financial amounts from the server. Input changes, source expiry, refreshed generations and delayed obsolete requests retire admission and results. The backend still owns eligibility and every decision that reaches the worker.

## Configuration and results

| Mode | Research inputs and units |
| --- | --- |
| Existing PAPER (default) | Synthetic reference, existing scenario and optional hypothetical funding. Omits the risk settings and uses the existing full-notional PAPER reservation. |
| Hypothetical risk research | Separate capital in PAPER quote units, explicit initial and maintenance fractions and optional modeled leverage with a declared ceiling. Fresh observed tier caps can constrain proposed leverage. |
| Source-constrained risk research | Exchange-observed market constraints with explicit hypothetical capital and fixed valuation. Uses exact network, spot namespace and token ID, a supported isolated mode and integer leverage. Scenario valuation expresses collateral units per PAPER quote. |

The selected market panel shows canonical identity, network, DEX, discovery status, collateral observation, market mode, tier thresholds, reported leverage limits and receipt times. Exposure is rendered in base or PAPER quote units as appropriate. The risk panel shows the modeled margin unit, declared capital, current and one-sided projected requirements, utilization and headroom, effective order exposure and separate proposed/resting metrics. Stress results show the configured price shock, haircut, reduction and funding/fee costs along with modeled P&L, headroom deterioration, tier transition and feasibility.

The Firewall renders recorded `NORMAL`, `WIDEN`, `REDUCE` and `HALT` states, candidate and authorized quote counts, projected headroom, reasons and margin retirements. Browser fixtures produce actual retirements and HALT for exhausted maintenance headroom through the shared worker. The accepted result renders synthetic source timing, prices, liquidity and fills, the hypothetical budgeting and fixed valuation, and the limits on balances, account mode, settlement, shared capital, cross-market netting and liquidation next to financial metrics.

### Accessibility

The existing Chromium harness exercised the labeled controls, explicit text statuses, validation errors, keyboard activation of the per-frame disclosure and Chromium's accessibility tree for headings, units and decisions. At 390 × 844 the financial descriptions and decision lists fit the panel and document widths. Desktop coverage used 1440 × 900. Platform-specific assistive technology verification remains an Audit 3.0 open item.

## Financial and adversarial acceptance

The public specifications describe a continuous maintenance deduction across increasing tiers, initial margin proportional to notional divided by leverage, and documented single-tier table IDs below 50. The independent oracle uses rational arithmetic for a three-tier schedule immediately below, exactly at and immediately above a boundary. It confirms continuity and upward rounding within one `0.00000001` unit. Published example tables display the tighter cap above the threshold. The local model retains the conservative, stricter cap at the exact lower bound. This acceptance establishes local model behavior at equality. [Margin tiers](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/margin-tiers) · [Margining](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/margining) · [HIP-3 policy](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/hip-3-deployer-actions)

The existing Decimal path calculates signed inventory and marked exposure, counts overlapping desired and resting levels once and compares current, projected long and projected short requirements. The budget incorporates PAPER net P&L once. Stress reprices the one-sided positions, applies the least favorable modeled P&L, haircuts positive budget, adds funding and fee costs and recomputes tiers and headroom. Decimal tests cover zero, signed exposure, partial resting fills, adverse and favorable economics, tiny and extreme input bounds, and conservative precision. The new presentation leaves the model calculations and ledger reservation formulas intact.

| Area | Exercised outcomes |
| --- | --- |
| Collateral and unit binding | Core versus HIP-3 and same market name across DEXs, Mainnet versus Testnet, same symbol with different token IDs, missing or unresolvable collateral, unknown account and settlement units, reserved unit collision, blocked cross-market netting. |
| Tier and mode validation | Single and multi-tier tables, boundary and rounding oracle, malformed, repeated and contradictory tiers, absent and deprecated flags, strict-isolated and no-cross distinction, unsupported HIP-3 multi-tier denomination and excessive leverage. |
| Authority and lifecycle | Forged flags and digest, wrong-network conversion or identity, retired generation, existing source-expiry tests, single-flight discovery and worker, cancellation and shutdown. New refresh test retires old eligibility during a started run while that run keeps its original fingerprint and source observation. |
| PAPER control | Infeasible headroom and leverage, quote reductions and mandatory retirement, modeled maintenance HALT, existing mandatory HALT and recovery, and final quote authorization. Existing integration compares signed fills, fees, funding and ledger with the non-binding model. |
| Zero signed operations | Instrumented SDK constructor, submit, cancellation and leverage-update calls, guarded adapter boundaries, and key derivation and signing all recorded zero calls in the tested PAPER scenarios and adversarial probes. Browser write requests stayed under the two research endpoints. |

## Public provider observations

On November 18, 2026 at approximately 9:20 p.m. Pacific, the official Mainnet public metadata provided 567 records across 11 namespaces. The following selected active markets had fresh metadata at lookup. Core market receipts were at 05:20:30.878437 UTC, `xyz:HOOD` at 05:20:34.590546 UTC and `io:ANTH` at 05:20:32.698182 UTC. Each used the Mainnet `hyperliquid.spot` token at index 0, `USDC` with ID `0x6d1e7cde53ba9467b783cb7c530ce054`, received at 05:20:32.109402 UTC.

| Canonical market | Observed policy | Research outcome |
| --- | --- | --- |
| `HYPERLIQUID:MAINNET:CORE_PERP::BTC` | Table 56, 40× from zero and 20× from 150,000,000. Mode absent. | Source-constrained unavailable. |
| `HYPERLIQUID:MAINNET:CORE_PERP::XTEN` | Strict isolated. Documented table 3, single 3× tier. | Source-constrained PAPER completed. |
| `HYPERLIQUID:MAINNET:HIP3_PERP:xyz:HOOD` | No cross. Documented table 10, single 10× tier. | Source-constrained PAPER completed. |
| `HYPERLIQUID:MAINNET:HIP3_PERP:io:ANTH` | Documented table 15, single 15× tier. Mode absent. | Source-constrained unavailable. |

`XTEN` and `xyz:HOOD` each completed five local PAPER frames at a synthetic price of 100, capital of 10,000 PAPER quote units, fixed hypothetical 1:1 valuation and 1× research leverage. Both results carried authority `NONE`. Captured observations retained the same fingerprint after normalization and serialization round trip. Thirteen distinct Mainnet SDK sessions closed and the discovery executor drained. Only the public inventory, perpetual metadata and spot metadata endpoints were accessed.

A bounded Testnet spot and Core read independently resolved BTC to USDC index 0, token `0xeb62eee3685fc4c43992febcd9e75443`, with table 54 and tiers at 0, 10,000 and 50,000. Its mode was absent. Repeating normalization of the same inputs yielded equal observations and all three Testnet SDK sessions closed. The Testnet inventory had 286 entries and exceeded the existing 64-namespace gate. No full Testnet catalog or account evidence was available.

## Historical financial compatibility

The same CPython environment and fixture inputs ran against the Phase 18.2G merge `4d57eaf`, the PR #91 merge `27713d0` and the implementation. Native evidence matched byte for byte across the three trees. The comparison used 39 dataset fingerprints and three 40-frame native simulations plus the aggregate portfolio. It included effective profiles and configuration, AMM quote output, agent and Firewall evidence, final authorizations, result and receipt fingerprints, fills, fees, funding, net P&L, equity and ledger. Wall-clock creation fields were omitted from the direct Firewall and final-authorization captures. The 18.2G published dataset, portfolio and combined checksums were independently reproduced. [18.2G reproduction probe](PHASE18_2G_FINAL_HARDENING_ACCEPTANCE.md#native-btcethsol-compatibility)

| Native evidence | Matching digest |
| --- | --- |
| Dataset matrix | `e97b675557f104e1ad2bfe3713133db88c20dbc2eece9e71a3d7ed4467f05abe` |
| Portfolio receipts, evidence and reconciliation | `e51a1579d079429ed6ee123e120a7d46bc38f4ebd73e7c90283ff97ab53c9417` |
| Published 18.2G combined evidence | `22eed4a5c0d67fa94b0e8780e9cbfd3af50276cab4e2b5e2a22e581b449a34ad` |
| Direct final-authorization capture | `ef990233ca2afd8d2662db40bb3e346908f378fddf43d275ece2ccfb344b65a9` |

The risk-disabled comparison matched all 26 complete normalized PAPER results across the three trees. It used all 13 scenarios per market for Core `DOGE` and HIP-3 `xyz:GOLD`, 40 frames, synthetic references of 0.1234 and 2500, size precisions of 2 and 3, maker and taker fees of 7 and 13 bps, two-second funding, and fixed observation, admission, and worker-start time `2026-11-18T12:00:00Z`. For every market/scenario the comparison included the dataset, configuration, result and full output fingerprints. This matrix's digest is `2d952586386a46967752b619fea0c126859ce09cb59d09d8567a70d5403c2b4f`. The PR #91 report publishes `c9d5683eee8192599440333a3dbc7e5f1a7540ed799a78222f3e2d30baf1a29e` for its historical aggregate. Its exact aggregation recipe and clock value are unspecified in the report. The controlled comparison establishes parity with the actual PR #91 code and retains the historical value for that capture.

Twelve opt-in PAPER outcomes also matched PR #91 byte for byte using the same fixed clock. The comparison used Core and HIP-3 fixtures, both modeled modes and three scenarios with stress assumptions. It included source and model binding, per-frame Firewall outcomes, final stress and margin evidence, accounting, and result fingerprints. The comparison digest is `0fefaae7a65c5d61926b5fc0d6813b8014a4663fc9148f8df1fc6d7f36fd4011`.

## Regression record

| Check | Observed result |
| --- | --- |
| Focused Phase 18 backend | 323 passed, zero failed or skipped, one existing TestClient warning, 13.64 s. |
| Focused Phase 18.3 on Pydantic 2.10.6 | 97 passed, zero failed or skipped, 9.06 s. |
| Full backend `python -m pytest -q -rs --tb=short` | 3,696 passed, zero failed or skipped, 675.09 s. Two existing warnings for Starlette's TestClient integration and Pydantic serialization in the Phase 17.4 tampering fixture. |
| Locked frontend install, typecheck, test and build | All passed. 864 tests passed, zero failed, cancelled or skipped. Vite reported 15 ignored dependency client directives and the existing chunk-size warning. |
| Chromium Generalized PAPER | 19 workflows passed on Chromium 151.0.7922.173 and Playwright 1.62.0. Includes the original ten and nine additional risk workflows. Zero unexpected page errors. |
| Chromium Historical Replay | 16 existing workflows passed. Zero unexpected console or page errors. |
| Chromium native portfolio | 22 existing workflows passed across five viewports with 60 engine invocations. Zero unexpected console or page errors. |
| Chromium extended Scenario vs Historical | 29 existing workflows passed in 118.59 s with the documented 60-second Playwright page and route waits. The initial default-timeout attempt stopped after two workflows during post-restart dataset selection. The rerun reported zero unexpected console or network errors. |
| Maximum risk envelope | Frontend validation accepted 120 frames and eight stresses in the two fixture modes. Core hypothetical serialized to 419,048 bytes and HIP-3 source-constrained serialized to 421,818 bytes. |
| npm audit, full and production-only | Both returned zero advisories on the locked tree at the time of the run. |

The standard backend ran on CPython 3.12.14, Pydantic 2.13.5, FastAPI 0.142.2 and Hyperliquid Python SDK 0.24.0 with the test, Redis, ML and Yahoo extras. The frontend used Node 24.19.0 and npm 11.9.0. The backend suite includes accounting, AMM, the Risk Firewall, simulation and replay, research executor, portfolio, final quote authorization, Audit 3.0 and guarded native TESTNET regressions. Browser fixtures used a real loopback backend and worker. Synthetic financial and provider fixtures are identified in the harness. The independent live metadata observations above use the official read-only transport.

Reproduce the focused backend suite with `python -m pytest -q -rs --tb=short tests/test_phase18*.py` from `backend`. From the repository root, run the reused browser harness with `python frontend/tests/browser-phase182.py --python /path/to/backend-python --output work/phase183ef-browser`.

## Scope and Phase 18.4

**PASS for Phase 18.3E–F and the Phase 18.4 advisory handoff within local PAPER scope.** The full suite, browser workflows, public observations and controlled before/after financial comparisons passed. The historical PR #91 generalized aggregate and the separate Audit 3.0 operational gates retain their recorded limitations.

Supported Core multi-tier schedules require canonical USDC for thresholds. HIP-3 multi-tier denomination, missing or deprecated mode fields, unresolved collateral, unavailable or stale observations and unsupported valuations remain outside source-constrained research. Account transfers, cross-margin sharing, fees and funding as charged by a venue, live mark/oracle pricing for generalized PAPER, wallet access and exchange liquidation prices require separate evidence.

Audit 3.0's remaining gates include signed TESTNET lifecycle and reconciliation, operational SDK reconnect and shutdown soak, long-running provider validation, historical acquisition and licensing, quantitative calibration and cross-platform accessibility/runtime verification. Its earlier development-tree advisory is recorded historically. The current registry audit outcome above applies to this run. Production trading remains outside this acceptance. [Audit 3.0 remaining limits](AUDIT3_FINAL_REMEDIATION_ACCEPTANCE.md#remaining-limits-and-verdict)

Phase 18.4 can build Market Eligibility, Funding/Basis and Quote Economics as advisory agents. It must bind each recommendation to supported market identity, explicit financial units and source freshness, surface missing pricing and funding evidence, and preserve the existing deterministic Firewall and final quote authorization hierarchy. Observational and hypothetical metrics retain their respective provenance in advisory outputs. [Phase 18 roadmap](PHASE18_0_MARKET_UNIVERSE_ARCHITECTURE.md)
