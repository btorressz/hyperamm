# Audit 4.0H-A local acceptance

Frozen `main` was `61f29348ad52d7c846872a7879b46ec4a933f994`, the merge of PR #105. Audit 4.0 took its measurements at the PR #104 merge `ea1a87321bfd5f22dd375bbc6ca203cc9b41948e`. This review covers three local-release P0 findings on loopback DEMO/PAPER. [Audit findings and release scope](../AUDIT_REPORT_4.0.md) · [#88](https://github.com/btorressz/hyperamm/pull/88) · [#89](https://github.com/btorressz/hyperamm/pull/89) · [#99](https://github.com/btorressz/hyperamm/pull/99) · [#100](https://github.com/btorressz/hyperamm/pull/100) · [#102](https://github.com/btorressz/hyperamm/pull/102) · [#103](https://github.com/btorressz/hyperamm/pull/103) · [#104](https://github.com/btorressz/hyperamm/pull/104) · [#105](https://github.com/btorressz/hyperamm/pull/105)

| Finding | Disposition | Evidence |
| --- | --- | --- |
| A4-005 | **PASS for scoped local regression** | Bounded off-loop preflight, current-source publication and one execution worker tested under controlled overlap, cancellation and shutdown. |
| A4-007 | **PASS for scoped local regression** | A real 40-frame result that disappeared on frozen main remained visible and correctly attributed after the same class of catalog expiry on the candidate. |
| A4-010 | **PASS for scoped local regression** | Chromium and loopback WebSocket interruption and backend restart left Start and Resume disabled until fresh acceptance. Stop and emergency Kill remained available during terminal loss. |

## Before the changes

| Finding | Baseline evidence |
| --- | --- |
| A4-005 | Audit 4.0 measured 134–159 ms per synchronous 120-frame HIGH_VOLATILITY preflight on its host. Source review on frozen main confirmed the route called the synchronous assessment directly on the loop. This task timed the same class of 120-frame calculation in a standalone, server-free process at 0.811–0.861 s while other suites were running. Baseline endpoint contention was not rerun. |
| A4-007 | Fresh Chromium baseline reproduction on frozen main. The deterministic Mainnet-shaped `xyz:GOLD` fixture used a 12 s catalog lifetime and synthetic input 3,500. The real worker returned HTTP 200 and the UI displayed 40 frames. The result vanished when the discovery deadline passed, Run disabled, and only one run request was observed. |
| A4-010 | Audit 4.0 observed Header's last-snapshot label, a FRESH order book and an enabled Risk Start six seconds after terminal disconnect. Source review on frozen main confirmed that the shell's historical flag never reached Markets or Risk. Current verification exercised the repaired behavior only. |

## Changes and source ownership

- **Reuse.** Generalized PAPER proposal/profile validation, precision, full-frame feasibility, asset-policy/risk/advisory binding, the lifespan-owned simulation executor and optional Redis coordination. The browser reuses the response validator, local simulation mount, result types, Results workspace, terminal store and process/session/sequence validation.
- **Enhance.** `backend/app/api/market_universe.py` and `backend/app/simulation/generalized_market_profiles.py` split cheap assessment from scenario compilation. Both routes recheck the captured generation, current deadlines, server-held risk/advisory inputs and binding before publication. The worker revalidates before engine start and uses the prepared scenario to avoid a second frame compilation. The one-job execution limit and busy response still apply. `backend/app/simulation/executor.py` and `backend/app/infrastructure/research.py` own the bounded preflight path and preserve Redis request fingerprints.
- **Enhance.** `frontend/src/components/simulation/GeneralizedPaper.tsx` retains the entire validated result and its local receipt time for one completed run. The result displays the original market/network/DEX, synthetic assumptions, recorded admission deadline, catalog/metadata/configuration and result fingerprints and the accepted money and risk evidence. Source status describes the capture. Fresh eligibility and any usable advisory receipt follow the current selection and source checks. A deliberate new run clears the prior result at submission. A canceled or retired request cannot attach its response to later inputs.
- **Enhance.** `frontend/src/App.tsx` and `utils/freshness.ts` derive effective terminal freshness from the accepted envelope and socket state. `pages/Markets.tsx`, `pages/Risk.tsx`, `pages/Dashboard.tsx`, `pages/Strategy.tsx`, `components/Header.tsx`, `components/QuickStrategyControl.tsx` and their existing evidence panels consume that state. The controls recheck freshness on activation. Risk and chart/book labels identify retained values. Stop can be attempted with historical evidence. Kill can be attempted before a first envelope or during terminal loss, and the HTTP failure is shown if the backend cannot be reached. Current manual-kill and running flags continue to drive the controls when the validated connection returns.
- **Add.** Bounded preflight capacity within the existing executor, focused backend timing and invalidation regressions in `test_phase182g_paper_hardening.py`, a targeted browser mode in `browser-phase182.py` and this report. The existing frontend navigation tests still check current and historical header rendering and now also check Kill availability.

## Liveness and lifecycle

The per-process preflight pool has two threads and admits four outstanding calculations. A fifth valid candidate receives HTTP 429 while capacity is occupied. Malformed and foreign input can be rejected before taking a slot. Canceling a waiter leaves its submitted calculation accounted for until the executor finishes it or drains it at shutdown. This keeps canceled queued work inside the same bound. The guarded publication tests retired the catalog at its exact deadline and replaced a generation during computation, including a replacement with the same fingerprint. Neither case reached the simulation worker. Shutdown drained four outstanding slots and joined both preflight threads with zero left.

The controlled heartbeat case exercised a legal 120-frame HIGH_VOLATILITY proposal with a 120-point trace bound. It held the preflight after feasibility and verified real health and strategy GETs, a new terminal frame and a separate 40-frame PAPER run before release. The feasibility section took 79 ms and the maximum 5 ms probe overrun was 5.6 ms across ten samples. The terminal/status/run group completed in 0.876 s, including a terminal publication. Both admitted requests compiled once. A separate maximum-size local API check accepted and ran all 120 frames and trace points with matching admission binding. Its HTTP 200 result was 776,469 bytes against the 2,000,000-byte limit. Eligibility took 0.363 s and the run took 7.233 s. These are host observations. The isolated baseline timing, audit timing and candidate heartbeat use different measurement windows and load conditions.

## Browser and local regression

Executed on Debian 13 with Python 3.12.14, FastAPI 0.165.0, pytest 9.1.1, Node 24.19.0, npm 11.9.0, Playwright 1.65.2 and Chromium 151.0.7922.173. Scoped accessibility checks use axe-core 4.11.1. Browsers exercised the real loopback terminal, PAPER API and worker with deterministic provider responses. The official-provider observations in Audit 4.0 remain a separate historical record.

| Check | Result |
| --- | --- |
| Full backend suite on the final code | 3,980 passed, 0 failed, 0 skipped, 5 warnings in 640.03 s. Warnings came from Starlette's httpx deprecation and four Pydantic instance-field deprecations. |
| Focused Phase 18, runtime/terminal, Audit 3.0 and final authority | 1,106 passed, 0 failed, 0 skipped, 4 warnings in 183.82 s. |
| Targeted bounded preflight, stale publication, cancellation and shutdown | 5 passed, 0 failed in 3.18 s. |
| Locked frontend install, typecheck, Node tests and build | 949 passed, 0 failed, 0 skipped, 0 canceled. Install, typecheck and build passed. Existing test storage notice, bundled client directive and chunk size warnings. |
| Targeted browser `browser-phase182.py --audit4-ha` | 4 workflows passed at 1440 and 390 CSS px. Exercised actual source expiry during disconnect, Results and history navigation, all modes, old-frame rejection, backend process/session replacement, recovery, failed and successful Kill, Stop, explicit refresh and a held real response after a different selection. |
| Phase 18.6 Chromium | 9 passing checks in 22.07 s, including keyboard and 200% zoom. |
| Phase 18.7 Chromium | 15 passing checks in 79.03 s, including all 13 routes in three modes, history, responsive layouts, Replay, native portfolio and 200% zoom. Existing assertions were retained. |
| Phase 18.2 Chromium | 36 passing checks in 69.97 s, including two axe scans with zero reported violations. Covers standard, risk-modeled, advisory and both asset-aware models. |
| Audit 3 accessibility Chromium | 32 route/viewport checks, 14 contrast sets, two keyboard checks and 200% zoom in 21.93 s. Zero page or console errors or automated violations. Axe flagged 33 items for manual review. |

The targeted Chromium rerun on the final code finished in 32.17 s. The Phase 18.6 runner recorded eight workflows plus the Chromium zoom check, 35 viewport measurements and 14 axe scans. Phase 18.7 recorded 14 workflows plus zoom, 71 viewport measurements and 26 axe scans. Both reported zero page errors and zero automated violations. Phase 18.7 reported nine items for manual review. An initial combined run was discarded because an earlier fixture Vite process still held port 5173. The first accessibility run used discovery-disabled configuration and failed its console assertion on two catalog HTTP 503s. The same harness passed with the existing local discovery fixture and all assertions intact.

## Financial and authority compatibility

| Evidence | Candidate and frozen baseline |
| --- | --- |
| 38 complete standard PAPER pairs | Byte-identical. Controlled SHA-256 `83cfb57fec42efdc9f64114b7891881752da53a904300e7ad4439859445fcf55`. |
| 18 complete asset-aware PAPER pairs | Byte-identical. Controlled SHA-256 `257c8d7ec9d510544b2d45302e3be10467f486eb4a1d53a4d63e9d06d8bf1ec9`. |
| Native BTC/ETH/SOL | Published comparison digest reproduced, including 39 dataset fingerprints, three native receipts and portfolio reconciliation. SHA-256 `22eed4a5c0d67fa94b0e8780e9cbfd3af50276cab4e2b5e2a22e581b449a34ad`. |
| Serialization schema | Both trees matched for PAPER admission (`3365f756459e71f1fce7876b01c34dfcaa3607bc8b7904ec4e2c6386170fc69f`) and result (`6be3025bcb8c5f8fe75c6cc5f6723b8d0122a477b3c5e5122b92bfae8d0acb36`). |

The controlled probes compare complete serialized pairs under identical fixed evidence. The original PR #100 aggregate hashes remain attestation-only under the Phase 18.7F limitation. The passing financial and authority fixtures cover both AMMs, simulated fills, fees, ledger and funding reconciliation, operational isolation, six supervisory agents including Predictive SHADOW, and the three observational advisories. The PAPER API tests forbid wallet derivation, live SDK construction and venue operations, and the targeted browser observed zero Start or Resume submissions during recovery. Backend Risk Firewall and final authorization govern operational quotes. [Financial compatibility probe](../backend/tests/phase187_paper_compatibility.py) · [Native probe](PHASE18_2G_FINAL_HARDENING_ACCEPTANCE.md#native-btcethsol-compatibility) · [Authority tests](../backend/tests/test_phase187d_authority_acceptance.py)

## Reproduction

Run serial browser suites on the default loopback ports. Set `PYTHON` to the backend virtual-environment interpreter and `AXE` to a local axe-core 4.11.1 script. The Phase 18.2, 18.6 and 18.7 runners own their fixture servers.

```bash
(cd backend && "$PYTHON" -m pytest -q -rs --tb=short)
(cd frontend && npm ci && npm run typecheck && npm test && npm run build)
"$PYTHON" frontend/tests/browser-phase182.py --audit4-ha --python "$PYTHON" --output work/audit4-ha/targeted
"$PYTHON" frontend/tests/browser-phase182.py --python "$PYTHON" --axe "$AXE" --output work/audit4-ha/phase182
"$PYTHON" frontend/tests/browser-phase186.py --python "$PYTHON" --axe "$AXE" --output work/audit4-ha/phase186
"$PYTHON" frontend/tests/browser-phase187.py --python "$PYTHON" --axe "$AXE" --output work/audit4-ha/phase187
```

For the Audit 3 accessibility runner, start the same loopback DEMO/PAPER configuration with the `browser-phase182:fixture_app` Uvicorn factory and the Vite frontend. Run `browser-audit3-accessibility.py --axe "$AXE" --output work/audit4-ha/accessibility`.

## Open release gates

Current acceptance covers a single operator on Linux/Chromium with local DEMO/PAPER and controlled provider inputs. Sustained official-provider operation, Firefox/WebKit and other OS/browser combinations, physical mobile and manual assistive technology, restart durability, signed TESTNET and production remain outside this acceptance. In-memory browser results survive route and mode changes and a backend restart within the same mounted browser workspace. Reloading the browser or closing that workspace ends its local retention.

Other Audit 4.0 findings remain **OPEN**. The following split reflects the audit's priority and owners.

| Handoff | Findings |
| --- | --- |
| H-B guarded TESTNET | A4-001 same-network genuine source gating and A4-002 restart reconciliation and uncertain orders. |
| H-C provider and runtime lifecycle | A4-003 component recovery, A4-004 provider budget, A4-008 operational callback ingress and A4-011 private SDK lifecycle. |
| H-D research evidence and presentation | A4-006 advisory normalization and A4-009 source and freshness labels. |

[Audit rollout priorities](../AUDIT_REPORT_4.0.md) · [Phase 18 release runbook](PHASE18_RELEASE_RUNBOOK.md)
