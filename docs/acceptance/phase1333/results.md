# Phase 13.3.3 — concise validation evidence

Local Linux, October 9, 2026 (America/Los_Angeles). Base `fc8c6303f4ac0114d11b1a6b1f2da30a55e7b315`.

## Baseline frontend

```text
ℹ tests 310
ℹ suites 0
ℹ pass 310
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 23725.04036
```

## Final frontend

```text
ℹ tests 376
ℹ suites 0
ℹ pass 376
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 17852.180072
```

## Baseline complete backend

```text
FAILED tests/test_audit_terminal_contract.py::test_generated_terminal_schema_is_current
1 failed, 1124 passed, 1 warning in 37.58s
```

## Final complete backend

```text
FAILED tests/test_audit_terminal_contract.py::test_generated_terminal_schema_is_current
1 failed, 1124 passed, 1 warning in 62.59s (0:01:02)
```

## Focused backend

```text
182 passed, 1 warning in 40.24s
```

TypeScript and production build exit 0; `pip check`, compileall and diff whitespace checks pass. Build reports the existing TanStack client-directive notices and a 506.16 kB main-chunk advisory. No test suppression or schema regeneration.

## Browser checks

| Harness | Route/viewport checks | Workflows | Page exceptions |
| --- | ---: | ---: | ---: |
| 1331 | 72 | 17 | 0 |
| 1332 | 72 | 25 | 0 |
| 1333 | 72 | 19 | 0 |

Total: **216 route/viewport checks + 61 workflows; zero page exceptions.** Phase 1333 also covers the actual dedicated backend stop/restart and isolated bounded-500/race/historical/provider/storage fixtures.

## Logs/Settings workflows

- live Logs category/search/reset/order/keyboard details and bounded JSON export
- live Settings persistence survives refresh; unavailable saved range remains 1H while Analytics shows SESSION
- live reset confirmation/cancel/keyboard/defaults/refresh preserve strategy, kill, ledger and orders
- live reset leaves Vault, Analytics and Sidebar functional
- all six specified cross-page transitions preserve accepted terminal identity
- 72 live route/viewport checks; mobile drawer keyboard dismissal
- actual backend stop/restart: historical Logs freeze, historical health, editable preferences, new-session isolation
- fixture message/reference case-insensitive trimmed search, reset, stable equal-time ordering, full details and exact filtered export
- fixture null fields, simulated versus unflagged records, long messages and narrow scrollable tables at six viewports
- fixture full 500-event bound with loaded/retained counts and no unbounded pagination
- fixture backend empty, HTTP failure, malformed records and wrong-session response are distinct; retry works
- fixture in-flight old process/session response cannot seed replacement Logs
- fixture batched same-session disconnect/reconnect retires pending response by connection epoch
- fixture disconnected evidence freezes with historical export and no five-second event polling
- fixture rejected stale/future/malformed/replayed frames preserve accepted Logs identity
- fixture unsupported persisted values and malformed JSON hydrate safe owned defaults after refresh
- fixture unavailable/stale sources, advancing source ages and historical SystemHealth; local preferences remain editable
- zero trading/configuration mutations, credential controls or browser-storage export across new workflows
- initial connection without any accepted snapshot still permits browser preferences; runtime remains unavailable

## Regression workflows

### 1331

- 72 live page/viewport checks
- agent keyboard expand/collapse at all six widths
- live agent filter
- live empty PAPER ledger
- shared Vault history charts
- full live provenance access
- all six populated fixture agent cards
- warmup/degraded/insufficient/model unavailable evidence
- fixture agent event filtering/empty/API error/loading
- stale in-flight agent event request rejected across session transition
- fixture ledger keyboard details/full fingerprints/exact tiny decimals
- ledger event/side/source/simulation/combined empty filters
- populated ledger overflow and detail access at all six widths
- ledger API error and version mismatch show explicit unavailable/error; no empty-success fallback
- old in-flight ledger with identical material provenance cannot populate replacement process/session
- backend-reported DIVERGED consistency warning
- TESTNET partial fixture missing equity/PnL and unavailable authoritative fill accounting

### 1332

- live range query and persisted 1M preference
- live Analytics four charts and keyboard explanations
- live Vault shared chart regression
- actual FLASH_MOVE PAPER simulation: backend metrics, 80 trace frames and full provenance
- captured run header survives scenario changes
- actual Balanced grid: backend ordering and two-candidate comparison
- frame input prevents invalid request; backend description displayed
- research/result inspection preserves active config, kill, ledger and orders
- fixture retention disabled ranges, saved unavailable preference and size-bound queries
- fixture chart gaps, signed base and percent axes/data; actual sample-count distribution
- fixture Analytics all six viewports
- fixture old in-flight history after process/session replacement rejected
- fixture history error/retry and disconnected retained chart evidence
- fixture busy state: single admission and changing controls never relabel captured response
- fixture trace same-second frames, missing/nonfinite metrics and invalid timestamps
- fixture Inventory preset, baseline/candidate selectors, null validation and rejection details
- fixture populated Simulation all six viewports
- fixture research error 422 actionable
- fixture research error 429 actionable
- fixture research error 503 actionable
- fixture research error 500 actionable
- fixture research error network actionable
- fixture unmounted research completion cannot seed replacement page
- zero non-research mutation requests across browser acceptance
- real chart mount: config replacement, height/width resize, keyboard reset and observer cleanup

Full raw command logs and large actual research payloads remain in ignored `work/`; only this concise summary and four representative PNGs are committed. Fixture captions do not claim actual venue activity.
