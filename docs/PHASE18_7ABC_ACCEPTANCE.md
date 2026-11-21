# Phase 18.7A–C acceptance

**Review status: draft.** The bounded Mainnet public-source check and deterministic cross-market and provider-resilience regressions passed. The native financial digest reproduced. A three-tree Generalized PAPER comparison reproduced byte parity for all 56 pairs with controlled inputs. Exact reproduction of the two published PR #100 aggregate hashes remains open. Testnet-wide discovery remains outside the current catalog capacity policy.

## Baseline and scope

The reference is current main at `46c7dd38b53616c070155896baf3f14afe7ea40f`. The Phase 18.6H merge is `06a5b0f97372ae0656eef26753730f11e512f4c3`. The PR #101 merge adds the source map through that implementation. The earlier PR #99 merge is `1b9804146a8de82e7432e18493591385b0f4bb0c`.

Reviewed the PR descriptions, merge diffs and source and test owners for Phase 17 portfolio research (#73–#80), Audit 3 remediation (#84), Phase 18 identity and discovery (#85–#87), Generalized PAPER and financial provenance (#88–#92), advisories (#93–#95), asset-aware PAPER (#96–#98), and Explorer and current documentation (#99–#101). Reviewed the README, codebase map, roadmap, changelog, Audit 3 report and remediation, and Phase 17.6 and Phase 18.0–18.6H acceptance records. [Source and contract inventory](PHASE18_7_ACCEPTANCE_MATRIX.md) · [PR #99](https://github.com/btorressz/hyperamm/pull/99) · [PR #100](https://github.com/btorressz/hyperamm/pull/100) · [PR #101](https://github.com/btorressz/hyperamm/pull/101)

| Area | Change inventory |
| --- | --- |
| Reuse | The existing discovery, summary, advisory, risk and native live-source owners, SDK transport, browser validators and Explorer. Both AMMs, six supervisory and three advisory agents, Risk Firewall and final quote authorization, native portfolio contracts and the shared PAPER worker. |
| Enhance | One production change in `backend/app/market_data/market_summaries.py` to withhold current observations during owner shutdown. The existing summary shutdown test asserts the returned state and absence of financial fields and fingerprint. |
| Add | `test_phase187_market_regression.py`, `test_phase187_provider_resilience.py`, and the fixed-clock `phase187_paper_compatibility.py` reproduction probe. This report and the acceptance matrix support the changelog and roadmap updates. |

The README's dated project snapshot predates the Phase 18 features; PR #101 and the route code supply the current source inventory. PR #100 reports 3,944 full backend, 249 focused backend, 30 summary and 949 frontend tests, plus eight Chromium workflows. Those are historical counts. The Phase 18.6H report also describes shutdown draining but does not cover what an active request can publish after the owner closes. The confirmed difference is recorded below. [Audit 3 findings and gates](../AUDIT_REPORT_3.0.md#15-unverified-concerns-and-external-blockers) · [Historical Phase 18.6H report](PHASE18_6_HARDENING_ACCEPTANCE.md)

## Financial compatibility

| Capture | Independently reproduced | Historical reference |
| --- | --- | --- |
| Standard Generalized PAPER | 38 full serialized admission/result pairs matched byte for byte on PR #99, PR #100 and current main. Controlled SHA-256 `83cfb57fec42efdc9f64114b7891881752da53a904300e7ad4439859445fcf55`. | PR #100 `b564ad46f264f8b8295feb5dc59d4c44a3e97b2302769663aaf94dbd5fbce65e`. Exact aggregate pending. |
| Asset-aware Generalized PAPER | 18 full serialized admission/result pairs matched on the same trees, using constant product for DOGE and concentrated liquidity for GOLD. Controlled SHA-256 `257c8d7ec9d510544b2d45302e3be10467f486eb4a1d53a4d63e9d06d8bf1ec9`. | PR #100 `5fa22910e35da8655a6f99df148cc809a2d6043ba090c2ae051ba479e64cf47f`. Exact aggregate pending. |
| Native PAPER and portfolio | The published combined digest `22eed4a5c0d67fa94b0e8780e9cbfd3af50276cab4e2b5e2a22e581b449a34ad` reproduced on main and PR #99. Dataset `e97b675557f104e1ad2bfe3713133db88c20dbc2eece9e71a3d7ed4467f05abe` and portfolio evidence `e51a1579d079429ed6ee123e120a7d46bc38f4ebd73e7c90283ff97ab53c9417` also matched the published values. | Phase 18.2G native probe, reused in later reviews. |

The controlled Generalized PAPER comparison uses 40 frames, fee rates of 7/13 bps, two-second funding, fixed receipt/admission/worker clocks, and a stable 60-second catalog generation. Its historical fixtures use Core DOGE at 0.1234 and size precision 2 and HIP-3 GOLD at 2,500 and precision 3. Standard mode covers every existing scenario for both markets and three scenarios each under hypothetical and source-constrained risk. Asset-aware mode covers those three scenarios with risk off and both modeled risk modes. The prior report gives the capture counts and broad inputs but supplies neither the exact clock nor the original aggregate generator and input envelope. The controlled results preserve both historical hashes as published and independently compare the actual historical trees. [Controlled probe](../backend/tests/phase187_paper_compatibility.py) · [Native reproduction](PHASE18_2G_FINAL_HARDENING_ACCEPTANCE.md#native-btcethsol-compatibility)

The 782 Phase 17 focused tests include every nonempty native BTC/ETH/SOL subset, canonical request permutations, distinct capital allocations and reserved capital, the independent P&L and drawdown oracle, fees and funding evidence, temporal coverage, bounded stress and worker contention. DOGE and HIP-3 remain outside the native portfolio allowlist. [Phase 17.6 baseline](PHASE176_FINAL_ACCEPTANCE.md)

## Cross-market and authority acceptance

| Evidence | Independent result |
| --- | --- |
| Market selection | Ordered results across Core BTC/ETH/SOL/DOGE, HIP-3 `xyz:GOLD` and `xyz:XYZ100`, same-name Core/`xyz`/`abc` BTC, and a delisted row. Distinct marks and exact identity, ordinal, catalog and metadata bindings. The configured network, DEX and perpetual class are independently bound. |
| Source substitutions | Existing and new fixtures reject foreign network or DEX, wrong source coin, reordered metadata, altered ordinal/precision, incompatible collateral and quote-unit claims, forged fingerprints, retired generations and missing keys. Unknown keys are 404 and foreign or retired generations are 409. A failed namespace retains its own error while an otherwise valid namespace can publish. |
| Precision and observations | Synthetic precision tests cover integer lot sizes, fractional lots, positive/zero/negative boundaries and price magnitudes. Missing optional values stay null, genuine zero funding/notional/OI stays zero, signed hourly funding and exact Decimal comparison retain provider units. Future or expired receipts withhold the mark and a null or shortened context cannot borrow an adjacent row. |
| PAPER and AMM controls | Existing standard and asset-aware suites run qualified Core and HIP-3 with both AMMs, expected metadata/profile bindings, risk and quote retirement, and one worker admission. Changing the operator-declared asset family retains the numerical controls. A blocked public BTC observation and an admitted local BTC PAPER run overlap; PAPER uses its explicit 64,000 reference while the fixture separately returns a 102 mark. |
| Authority | Instrumented summary and PAPER checks observed zero public-path calls to account key derivation, signing, order submission, cancellation, leverage updates, operational adapter, supervisory evaluation, Risk Firewall or final quote authorization. Those last three remain part of the ordinary simulated quote pipeline. Summary requests use no runtime strategy, terminal market selection, capital, portfolio, replay, simulation admission or native WebSocket dependency. |

The broad rerun includes source and authority checks from Audit 3, and native REST and stream tests. Browser fixtures separately cover selection changes, catalog replacement, server and browser expiry and late requests. [Cross-market tests](../backend/tests/test_phase187_market_regression.py) · [Phase 18.6H summary tests](../backend/tests/test_phase186h_market_summaries.py) · [Asset policy baseline](PHASE18_5_FINAL_ACCEPTANCE.md)

## Provider resilience, performance and lifecycle

| Workload | Independent fixture evidence |
| --- | --- |
| Cold Core, 12 cards and following page | One Core context call. The following page reused it; the manual refresh before five seconds reused the same capture, and the request at five seconds made one additional call. |
| 12 HIP-3 markets and sequential pages | The 80-page alternating 12-market fixture exercised a single HIP-3 DEX, 400 seconds on the controlled clock and 40 provider calls with 40 cache hits, including repeated manual refresh. It issued zero calls to unselected namespaces. |
| Concurrent readers and mixed DEX page | Eight concurrent Core readers shared one provider acquisition; two HIP-3 namespaces acquired independently. Peak three active provider calls, three total starts, fourth namespace `CAPACITY` with zero starts. The existing mixed-page test independently exercises bounded rotation back to complete rows. |
| Rolling rate and retention | The actual 24 starts per minute limit admitted 24 starts. Two repeated requests to a new namespace were limited without traffic, including one at 59.9 s. After the window, two starts succeeded. Retained entries stayed at 24, with the two oldest evicted. |
| 429 | The successful Core row survived a sibling DEX limit; four refreshes during backoff issued zero new provider calls. Both DEXs recovered at 30 seconds. The shared transport also independently classified HTTP 429 and closed its session. |
| Deadline, transport and malformed data | The six-second API deadline returned `TIMEOUT` at 6.013 s while the shared call still held its slot. Transport fixtures covered DNS/connect failure, timeout, 500/503, interrupted and truncated bodies, invalid JSON and UTF-8, duplicate keys, excessive nesting and response sizes, unsupported encoding, session cleanup failure, empty universes, null/incomplete context, and invalid Decimals. Public responses carried structured reasons without fixture diagnostics. |
| Catalog turnover | Existing and cross-market fixtures retired requests during refresh, rejected obsolete active-generation fingerprints and reacquired context under the new generation. The browser retired delayed or expired observations. |
| Disconnect and shutdown | Caller cancellation and ASGI `http.disconnect` released their waiters. A surviving waiter received the shared capture from one provider acquisition. Shutdown waited for in-flight work, cleared the owner cache and drained the discovery pool. Fresh owners reacquired data. Default executor threads remain owned by the application event loop. |
| Mixed observation and PAPER | One provider thread held independently while the single research executor admitted and finished one real local PAPER run. The paired results retained separate synthetic and observed reference prices and correct market metadata. |

The 80-page fixture took 0.444 s wall time, produced at most 12,832 bytes per response, had zero provider/HTTP failures and timeouts, and retained seven generation captures at the end and zero after shutdown. Process peak RSS was 117,304 KiB for the pytest process, including imported dependencies and earlier cases. Active process threads were four at start, five before close and two after both owners closed. Discovery pool threads were joined; the remaining test-loop executor thread is released by loop teardown. This short controlled-clock fixture measures call pressure and cleanup. Sustained external traffic and memory profiling on another OS remain rollout evidence. [Provider fixture suite](../backend/tests/test_phase187_provider_resilience.py)

### Reproduced defect

On current main, the existing shutdown fixture was extended to assert that an acquired summary cannot publish a current price once its provider owner starts closing. It failed with `CURRENT` and mark `201`. The owner cleared its cache and stopped accepting new work, while already-waiting requests evaluated the returned capture against an independently active catalog and still published it. The existing owner now selects the existing `CLOSED` row error while assembling results. A shutdown result carries no mark or observation fingerprint, and the SDK acquisition still drains. The retest passed with the same route and contract. [Owner](../backend/app/market_data/market_summaries.py) · [Shutdown reproducer](../backend/tests/test_phase186h_market_summaries.py)

## Official public provider evidence

A bounded check on November 20, 2026 Pacific used `OfficialMetadataClient`, the discovery and summary owners, and the market-universe routes via ASGI. The two endpoints were `https://api.hyperliquid.xyz/info` and `https://api.hyperliquid-testnet.xyz/info`. All 19 upstream requests returned HTTP 200, all 19 SDK sessions closed, and no discovery worker remained after close. The API status reflects downstream catalog admission.

| Network and operation | Upstream calls | Application result |
| --- | ---: | --- |
| Mainnet `perpDexs`, `meta` and `spotMeta` | 13 (1 inventory, 11 namespace metadata, 1 spot) | HTTP 200 `AVAILABLE` with 11 namespaces and 568 records, 491,152 bytes, 6.958 s elapsed. |
| Mainnet `metaAndAssetCtxs`, Core, `xyz`, `io` | 3 | HTTP 200, seven current rows, 7,895 bytes, 1.870 s elapsed. |
| Testnet `perpDexs` | 2 (one for discovery and one bounded count probe) | Discovery HTTP 503, `CATALOG_CAPACITY`, no namespace metadata fan-out or catalog published, 543 bytes, 2.361 s elapsed. Direct inventory contained 288 entries including Core. |
| Testnet Core `metaAndAssetCtxs` | 1 | Direct HTTP 200 in 2.114 s, 213 matching Core context rows, with mark/oracle/funding present for BTC, ETH and SOL. This probe did not qualify a Testnet catalog generation. |

| Mainnet market | Size precision | Receipt (Pacific) | Mark | Oracle | Hourly funding fraction |
| --- | ---: | --- | ---: | ---: | ---: |
| Core BTC | 5 | 21:36:23.988601 | 55,776.0 | 55,806.8 | −0.0000020011 |
| Core ETH | 4 | 21:36:23.988601 | 1,558.5 | 1,559.77 | −0.0000268825 |
| Core SOL | 2 | 21:36:23.988601 | 65.369 | 65.4101 | −0.0000114711 |
| Core DOGE | 0 | 21:36:23.988601 | 0.051535 | 0.051567 | +0.0000019683 |
| HIP-3 `io:AAPL` | 3 | 21:36:24.215804 | 344.0 | 344.04 | −0.0000116772 |
| HIP-3 `xyz:GOLD` | 4 | 21:36:24.890574 | 3,519.6 | 3,521.0 | +0.00000625 |
| HIP-3 `xyz:XYZ100` | 4 | 21:36:24.890574 | 25,133.0 | 25,137.0 | +0.000020855 |

Core, `io` and `xyz` calls took 0.935 s, 1.162 s and 1.836 s respectively through SDK parsing and cleanup. Local receipt age at route evaluation was about 0.909 s, 0.681 s and 0.007 s. Each capture expired at receipt plus 30 seconds. The upstream context carries no verified event time, so this verifies local receipt freshness. The published prices use provider quote denominations. Funding describes the reported rate. Testnet Core completed at 21:36:29.377569 Pacific. Full Testnet catalog-backed summaries were blocked by policy. [Official perpetual metadata](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals)

### Testnet capacity decision

**Outcome A. Retain the existing 64-namespace cap.** The Phase 18.1 change introduced the cap, including Core, as an explicit bounded inventory and response limit. Its history documents fail-closed admission, but supplies no benchmark establishing 64 as a deadline-safe target. The existing limits also include 4,096 total records, a 1 MiB cap per provider body and a 5 MB browser discovery response cap. The request admits a configured network and requires a complete catalog generation before exposing a usable selection. A partial attempt can publish diagnostics and serve the last complete generation tagged stale.

A 15 s refresh starts with inventory, then uses at most three active metadata calls and shares the pool with an optional spot lookup. Even an idealized 5 s inventory and two 5 s collection waves permit six collection slots before accounting for the spot slot, application overhead or the strict deadline. Actual completion depends on latency and response sizes. Collecting 288 namespaces within the deadline would require over 19 metadata responses per second even before inventory and spot. The provider documents 1,200 total IP weight per minute and a default Info call weight of 20. The 288 metadata operations alone imply 5,760 weight, or nearly five minutes of the documented steady-state IP budget. Other owners share that budget. Current summaries independently cap starts at 480 weight per minute. The cap is an admission ceiling and cannot guarantee completion for every in-bound inventory.

A selected Core context requires only Core at the upstream API. The app's catalog and eligibility still require a complete, fingerprinted generation. Publishing Core as the existing complete catalog would change the meaning of that fingerprint and erase failed or absent namespace coverage. A separately represented scoped Testnet catalog would require a versioned completeness and provenance policy. The live and fixture 503 results support keeping the present policy for this scope. [Phase 18.1 design](PHASE18_1_DISCOVERY_ACCEPTANCE.md#refresh-ownership-and-failure-states) · [Provider rate policy](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits)

## Regression commands and evidence

| Check | Result |
| --- | --- |
| Focused historical backend | 1,639 passed, zero failures/skips, six warnings in 294.98 s. This includes 571 Phase 18, 782 native portfolio, 214 native live REST/streams and 72 Audit 3/source cases. |
| Focused summary and A–C additions | 51 passed, zero failures/skips/warnings in 9.94 s. Includes the 30 summary tests and 21 new cases. |
| Full backend | 3,965 passed, zero failures/skips, six warnings in 370.97 s. Warnings came from Starlette/httpx deprecation, Pydantic instance field access and the existing negative serializer fixture. |
| Frontend | Locked `npm ci`, typecheck, tests and production build passed. Node 24.19.0/npm 11.9.0, 949 passed, zero failures/skips/cancellations. Vite reported existing TanStack directive and bundle size warnings. |
| Chromium fixture browser | Chrome 151.0.7922.173, eight workflows, 35 viewport measurements, 14 scoped axe scans with zero automated violations or incomplete findings, a 200% zoom check and zero page errors. Local DEMO with deterministic provider data and real PAPER worker. |
| Fresh processes and lifespan | Four fixture startup/shutdown cycles across two fresh Python processes. Each cycle started new owners, returned two current rows in a 2,487-byte body and joined every discovery pool thread. Each cycle took 0.010–0.085 s. Owner caches and tasks were empty after close. |

Python 3.12.14 used the existing local environment with optional ML and Yahoo extras and two pytest-xdist workers for the broad suites. From `backend/`:

```bash
PYTEST_ADDOPTS='-n 2' python -m pytest -q -rs --tb=short
python -m pytest -q -rs --tb=short -n 2 tests/test_phase18[0-6]*.py \
  tests/test_phase17*.py tests/test_audit3*.py tests/test_phase15[12]_live*.py \
  tests/test_audit_read_observations.py
python -m pytest -q --tb=short -o junit_family=xunit1 --junitxml=/tmp/phase187.xml \
  tests/test_phase186h_market_summaries.py tests/test_phase187*.py
```

The controlled compatibility command works from each historical worktree with the same probe path. Capture stdout separately for each tree and use `cmp` and `sha256sum`.

```bash
PYTHONPATH=backend:backend/tests python /path/to/phase187_paper_compatibility.py standard
PYTHONPATH=backend:backend/tests python /path/to/phase187_paper_compatibility.py asset
```

Reproduce the frontend with `npm ci && npm run typecheck && npm test && npm run build` from `frontend/`. From the root, run the existing `frontend/tests/browser-phase186.py` harness with backend Python, Chromium, an axe-core script and a scratch output directory.

For a bounded official Core or DEX context probe, POST `{"type":"metaAndAssetCtxs","dex":""}` (Core) or `{"type":"metaAndAssetCtxs","dex":"xyz"}` to the configured official `/info` endpoint. The `{"type":"perpDexs"}` operation lists the inventory in one request. For the catalog-bound route, start the existing app in DEMO/PAPER with `MARKET_UNIVERSE_ENABLED=true` and the desired `MARKET_UNIVERSE_NETWORK`. GET the catalog and use its fingerprint, network and selected canonical keys in the summary POST. Leave signed operations disabled. [API inventory](PHASE18_7_ACCEPTANCE_MATRIX.md#contract-inventory)

## Open gates and ownership

- A retains the exact PR #100 aggregate hash reproduction gate. Resolve it with the original generator and input envelope or independently review the controlled historical comparison as acceptance evidence.
- C retains the full Testnet catalog policy restriction and sustained live-provider and multi-platform acceptance. Mainnet and Testnet observations here are time-bounded point checks.
- D owns independent final financial and trading-authority certification, including signed venue and reconciliation evidence.
- E owns alternate browsers, assistive technology and OS-level accessibility. The Chromium fixture rerun covers Phase 18.6H workflows.
- F owns the release and rollout decision, including sustained provider and operational recovery requirements from Audit 3.0.
