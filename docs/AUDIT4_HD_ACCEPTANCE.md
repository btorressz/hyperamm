# Audit 4.0H-D acceptance

H-D starts from `d597af6c9c76febec0c80248a1bc7b3cae97d76a`, the fetched tip of `main` and the verified merge of PR #108. The review covered the first-parent changes from PRs #93–100 and #102–108, the current owners and fixtures, and the Phase 18 and Audit 3.0/4.0 acceptance records. This is local fixture acceptance for the two scoped findings. [PR #108](https://github.com/btorressz/hyperamm/pull/108) · [Original findings](../AUDIT_REPORT_4.0.md#confirmed-findings)

| Finding | Local disposition | Evidence |
| --- | --- | --- |
| A4-006 | PASS | The original fixture and cap-only variant reproduced on the frozen base. Current funding and prices share exact parsing on the candidate. Explicit unsupported unit assertions and conflicting collateral block advice. |
| A4-009 | PASS | Chromium reproduced the missing fields after filtering `io:AAPL` to DOGE on the frozen base. The same workflow passes with current receipt data on the candidate, including page changes, expiry and late responses. |

## Baseline reproductions

- The two assertions for A4-006 failed on unchanged production code. The fixture used `funding="0.006"` with and without `quoteUnit="UNTRUSTED"`. Explorer omitted the rate in both cases and returned `QUOTE_UNIT_MISMATCH` for the tagged response. Funding/Basis returned `READY` with policy confidence `0.90` and a mark/oracle basis of `179.64071856` bps for both.
- In actual Chromium, the fixture `io:AAPL` card showed mark and funding. After selection and a search for DOGE, Details remained `Current` with its own 2-key batch, receipt and canonical identity. The browser assertion for the **Mark price** term failed because the selected panel contained neither mark nor funding.

## Qualified public funding and prices

Both clients parse exact decimals with the existing bound on magnitude and precision. Positive mark and oracle values and inclusive hourly funding from `-0.005` to `+0.005` qualify numerically. The payload stores a signed fraction for 3,600 seconds. Explorer displays it as a percentage and preserves a genuine zero. Invalid decimals, including nonfinite values and values just beyond either funding boundary, are unavailable. [Shared policy](../backend/app/market_data/public_perp_financials.py)

The current context metadata must match the discovery network and DEX, ordered universe, source coin, index, listing and size precision. A tagged row must match its qualified position. Absent row identity tags use the official positional contract after the metadata and length checks. An upstream swap of equally sized anonymous context arrays with unchanged metadata cannot be detected from the documented wire fields. Discovery is checked again at publication, and advisory single-flight and cache reuse are scoped to the captured catalog, market and financial metadata. [Discovery contract](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals) · [Advisory coordinator](../backend/app/agents/advisory_coordinator.py)

An explicit `quoteUnit`, `markQuoteUnit`, `prevDayQuoteUnit`, `oracleQuoteUnit` or `midQuoteUnit` is outside the supported context schema. Even a plausible token symbol in one of those fields has no verified meaning. A context collateral index must match discovery, with strict integer typing. Funding/Basis also requires the discovered collateral index to resolve through same-network spot metadata. Core collateral and price denomination can differ. HIP-3 collateral is scoped to the DEX and its deployment. The adapter relies on the documented in-market price relationships only for relative comparison of the same qualified contract. The source evidence stays in provider quote per base and carries no independently verified price currency or conversion. [Core specifications](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/contract-specifications) · [Core price indices](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/robust-price-indices) · [HIP-3 design](https://hyperliquid.gitbook.io/hyperliquid-docs/hyperliquid-improvement-proposals-hips/hip-3-builder-deployed-perpetuals) · [HIP-3 pricing and deployer fields](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/hip-3-deployer-actions)

| Case | Explorer summary | Funding/Basis |
| --- | --- | --- |
| Qualified current context with matching, resolved collateral | Valid mark, oracle and hourly funding are current | `READY` with `0.90` policy confidence. Mark/oracle basis uses the aligned pair. |
| Missing or invalid funding, mark or oracle | Independently valid fields stay available, with a field limitation | `INSUFFICIENT_DATA` with zero confidence. Independently qualified mark or oracle can still be cited. No basis. |
| Collateral absent or unresolved with no conflicting claim | Individually valid observations can use provider units | `INSUFFICIENT_DATA` with zero confidence and a price-unit compatibility requirement when the numeric fields are complete. No basis. |
| Unsupported unit claim or conflicting collateral | `QUOTE_UNIT_MISMATCH` with no values from the affected context | `UNSUPPORTED` with zero confidence and no prices, funding or basis. |
| Mismatched row identity, network or catalog | Qualified request/response rejection | Error or catalog rejection, with no current numerical advice. |
| Missing, expired, future-dated or unaligned optional book | The Explorer uses the existing current-context fields | Any available qualified current context can stay `READY`. Both midpoint bases are suppressed when the book cannot be used. |

The existing book comparison still requires an uncrossed book, exact market identity, a qualified quote scale and provider-event freshness. The mark/oracle pair binds to one current-context receipt. Source clocks, signed basis arithmetic and rounding are preserved. A current rate has a local receipt and expires at 30 seconds or the discovery deadline. Book and realized funding retain their provider event clocks. A deterministic clock probe verified that a future local receipt suppresses the Explorer values and all advisory points. Valid frozen-fixture summary and advisory source fingerprints matched the base byte for byte. The advisory snapshot digest continues to cover the full result, including the revised explanation. The advisory display labels confidence on a 0–1 policy scale.

`fundingHistory` supplies optional realized hourly evidence over the existing rolling 24-hour request. The documented hourly venue cap supports the same inclusive range for those observations. History retains its event time and `REALIZED_RATE_PER_HOUR` unit. A malformed or out-of-bound history response leaves the qualified current analysis usable and removes the history aggregate. Synthetic PAPER retains its configured interval, provenance and exact analysis. A fixture verified that a hypothetical `0.006` scheduled per three seconds remains `READY` in PAPER while `0.006` per public hour is rejected. [Hyperliquid funding convention](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/funding) · [Historical Info endpoint](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals#retrieve-historical-funding-rates)

## Selected Market Explorer Details

Details displays mark and hourly funding above the discovery metadata using the same formatted current fields as the cards. The panel retains oracle, previous-day reference, the one-hour interval, provider quote per base, source, server receipt, unavailable provider-event timestamp and separate fingerprints. Explorer continues suppressing a displayed mark/oracle basis. Current context data expires by both receipt age and catalog lifetime. The panel clears values while discovery is being checked, through source expiry or failure, and when the active batch cannot validate the qualified binding. A selected result can survive a page-local sort, search or filter in the same catalog.

The existing batch requests 12 visible keys and at most one selected off-page key. Chromium recorded an actual 13-key request and a 2-key DOGE/AAPL request. The snapshot returned read-only authority flags and selecting Details generated only market-summary POSTs. Research handoff became disabled on catalog expiry and available again after discovery refreshed. The 20-second visible refresh, namespace cache, shared weighted provider admission and H-C backoff remain in their existing owners. [Explorer](../frontend/src/components/markets/MarketExplorer.tsx) · [Browser harness](../frontend/tests/browser-phase187.py) · [390 px fixture screenshot](acceptance/audit4hd/audit4-hd-selected-off-page-390.png) · [1440 px fixture screenshot](acceptance/audit4hd/audit4-hd-selected-off-page-1440.png)

Chromium verified keyboard focus and toggle state, Core card parity, the off-page HIP-3 selection, missing mark and funding, backend rejection of excess funding, genuine zero, delisting, retired catalog generations, stale receipts and late responses. Provider timeout, rate limit, catalog and network error UI checks use injected response envelopes. Backend fixtures separately verify the provider and generation failure paths. The Phase 18.7 portfolio and H-A receipt harnesses buffer the real backend bodies before delivering them to Chromium, which avoids a fixture-only response-body retrieval race observed during initial runs. Layout measurements at 390×844, 768×900, 1024×768, 1440×1000 and 1920×1080 had no horizontal overflow. Actual Chromium 200% zoom produced a 720 px layout and 720 px document. The two targeted axe scans reported zero violations and the browser reported zero page errors.

## Verification

| Check | Executed result |
| --- | --- |
| Full backend | 4,122 passed, zero failed or skipped, five existing warnings in 744.74 seconds. |
| Focused H-D, advisory, summary, provider, market and authority suites and H-B/H-C regressions | 228 passed, zero failed or skipped. |
| Frontend locked install, typecheck, unit tests and Vite build | 952 passed, zero failed, cancelled or skipped. Typecheck and production build passed. Vite reported its existing module-directive and bundle-size warnings. |
| Phase 18.4 advisory Chromium | Seven logged checks passed, including observed and synthetic evidence, provider backoff, keyboard interaction and an axe scan with zero violations. |
| Targeted H-D Chromium | Seven workflows, five layouts, two axe scans and actual 200% zoom passed. |
| Full Phase 18.7 Chromium | 14 workflows, 39 route/mode checks, 71 viewport measurements, 26 axe scans with zero violations and zero page errors. Actual 200% zoom passed. |
| Phase 15.5B native Chromium regression | Six workflows passed. The fixture observer retired an old generation and released its browser subscriber with zero page errors. |
| H-A Chromium | Four workflows passed, including completed PAPER evidence through expiry and terminal loss, fresh-only controls and late-response rejection. |
| 38 standard PAPER pairs | Byte-identical to base and the published controlled digest `83cfb57fec42efdc9f64114b7891881752da53a904300e7ad4439859445fcf55`. |
| 18 asset-aware PAPER pairs | Byte-identical to base and the published controlled digest `257c8d7ec9d510544b2d45302e3be10467f486eb4a1d53a4d63e9d06d8bf1ec9`. |
| Native BTC/ETH/SOL and portfolio | The base and candidate reproduced the published combined digest `22eed4a5c0d67fa94b0e8780e9cbfd3af50276cab4e2b5e2a22e581b449a34ad`. |

Both existing AMMs and all nine agent roles retain their financial and authority behavior. The bounded suite covers the Risk Firewall, FinalQuoteAuthorization, PAPER admissions and qualified market binding. H-A verification covers bounded preflight, historical PAPER retention and terminal freshness for A4-005/007/010. H-B verification covers A4-001/002/011 with unsigned provenance, account inventory and SDK ownership fixtures. H-C verification covers native sibling recovery, shared public budget and operational LIVE overflow for A4-003/004/008. [H-A](AUDIT4_HA_ACCEPTANCE.md) · [H-B](AUDIT4_HB_ACCEPTANCE.md) · [H-C](AUDIT4_HC_ACCEPTANCE.md)

| Architecture | Changes |
| --- | --- |
| Reuse | The existing exact decimal parser, discovery catalog and financial metadata, age and evidence contracts, advisory evaluator, summary hook and formatter, provider budget and Chromium harness. |
| Enhance | The two public consumers and advisory coordinator share field validation and bind quote compatibility. Explorer renders the existing selected receipt. The advisory UI explains the policy score. |
| Add | One pure shared field-policy module, a focused backend parity test file, and this acceptance record. |

Run the backend suite and existing controlled comparisons from `backend/`. Use the published probe for the native digest with `PYTHONPATH=.:tests`. Run the browser harnesses serially on the existing loopback ports. [Native digest probe](PHASE18_2G_FINAL_HARDENING_ACCEPTANCE.md#native-btcethsol-compatibility)

```bash
(cd backend && python -m pytest -q -rs --tb=short)
(cd frontend && npm ci && npm run typecheck && npm test && npm run build)
"$PYTHON" frontend/tests/browser-phase187.py --audit4-hd --python "$PYTHON" --axe "$AXE" --output work/hd/explorer
"$PYTHON" frontend/tests/browser-phase187.py --python "$PYTHON" --axe "$AXE" --output work/hd/phase187
"$PYTHON" frontend/tests/browser-phase182.py --audit4-ha --python "$PYTHON" --output work/hd/ha
"$PYTHON" frontend/tests/browser-phase182.py --advisory-only --python "$PYTHON" --axe "$AXE" --output work/hd/advisory
"$PYTHON" frontend/tests/browser-phase155b.py --python "$PYTHON" --output work/hd/native
```

The execution environment used Python 3.12.14, pytest 9.1.1, pytest-asyncio 1.5.0, Node 24.19.0, npm 11.9.0, Chromium 151.0.7922.173, Playwright 1.62.0 and axe-core 4.11.1. Signed TESTNET and durable restart recovery remain blocked. Sustained official provider soak, cross-platform browser execution, physical mobile and manual VoiceOver and NVDA remain separate acceptance gates. The original PR #100 aggregate attestation remains separately open. After H-D review, configure GitHub Actions to run the backend and frontend suites, the controlled compatibility probes and fixture Chromium before enabling branch checks. Keep separately authorized venue checks outside the default CI workflow. [Release gates](PHASE18_RELEASE_RUNBOOK.md) · [Compatibility record](acceptance/phase187f/compatibility.json)
