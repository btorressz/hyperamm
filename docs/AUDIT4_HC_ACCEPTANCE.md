# Audit 4.0H-C acceptance

Frozen GitHub main is `71cf84c82a9ee4e368cf402f0cedae4573c81a64`, the merge of PR #107. Review used the first-parent evidence from PR #87, #93–#100, and #102–#107, including the Phase 18.6H, Phase 18.7 A–C and final records, and H-A/H-B. [PR #107](https://github.com/btorressz/hyperamm/pull/107) · [Audit 4.0](../AUDIT_REPORT_4.0.md) · [Phase 18.7 A–C](PHASE18_7ABC_ACCEPTANCE.md) · [Phase 18.7 final](PHASE18_7_FINAL_ACCEPTANCE.md)

| Finding | Deterministic decision | Evidence |
| --- | --- | --- |
| A4-003 | **PASS** | Recover isolated native losses in the same SDK generation. Retire shared evidence on socket failure or a verified change to the native asset bindings. |
| A4-004 | **PASS** | All public Hyperliquid REST paths owned by the application lifespan use the same rolling weighted budget, including native and operational SDK construction and recovery. |
| A4-008 | **PASS** | An operational callback gap immediately removes fresh quote evidence. Recovery requires a trusted fresh book and, when subscribed, a valid context. |
| Sustained official provider availability | **CONDITIONAL** | This change used deterministic fixtures and loopback Chromium. Official provider observations cited here come from predecessor runs. |

## Baseline and comparable fixtures

The baseline tests ran against the frozen main worktree. Three isolated native stalls caused the baseline to retire the common generation, including the healthy sibling subscribed by the fixture. The same three cases keep generation 1 and deliver available sibling frames in the candidate. The target stays stale or degraded for a missing book or context. An expired metadata receipt recovers after a validated shared refresh with matching bindings.

| Fixture | Frozen main | Candidate |
| --- | --- | --- |
| Legal 64-namespace discovery, including inventory and collateral token metadata | 66 Info sends, 1,320 weight | 41 sends, 820 weight. Explicit partial/unavailable outcome with no complete catalog. |
| 512 operational callbacks while downstream awaits | 512 scheduled closures | One scheduled wakeup, eight retained messages, 504 losses recorded, gap enforced before the consumer resumed. |
| 20-cycle native fixture with overflow, invalid context and a forced disconnect each cycle | Peak depth 8 per market, 180 drops, 21 SDK starts | Same depth, drops and explicit SDK starts. Pre-gap buffered events are discarded; each market retains 32 history points. |
| End of the 20-cycle fixture | Zero owned threads, tasks, subscribers and uncertain SDK resources | Zero owned threads, tasks, subscribers and uncertain SDK resources. |

The 1,800-second predecessor run recorded 687 Info starts, a peak of 779 weight and all three native markets fresh at 36/90 polls. The independent 105-second audit recorded peak weight 807 and all three fresh at 4/6 polls. Those observations are sampled availability. The fixtures deliberately control stalls, bursts and disconnections. A time-weighted or before/after provider comparison requires an equivalent official workload. [Historical measurements](../AUDIT_REPORT_4.0.md#provider-budget-and-native-freshness)

In the additional 20-cycle Linux resource sampling run, baseline and candidate both peaked at two OS threads and four asyncio tasks with the fixture sampler included. Peak sampled RSS was 84,028 and 84,088 KiB respectively. The 10 ms heartbeat reached 79.65 and 162.93 ms of lateness while backend tests ran concurrently. Six subscriptions were observed at peak and zero after shutdown. The runs finished in 2.867 and 2.951 seconds, with shutdown taking 242.14 and 200.72 ms respectively. One sampler control task remained before each loop exited. The sampled values are host observations.

## Native generation and freshness rules

The common socket still owns up to six BTC, ETH and SOL subscriptions. L2 exchange time and local receipt age, perpetual context receipt age, and metadata age are evaluated independently. An expired L2 component closes only that market's snapshot barrier. A serialized and budgeted book repair can run while the loop processes other markets and publishes browser updates. A valid snapshot must meet the current market index, size precision, freshness and watermark rules. Subscription readiness requires validated WebSocket evidence for both channels. An identical book watermark can establish a trusted REST barrier under the existing equality rules. Repeated WebSocket books with the same watermark preserve their original timestamps and history.

A quiet perpetual channel stays stale until a valid new context arrives. Expired metadata schedules one shared refresh and compares the validated native index, precision and listing bindings. A matching refresh qualifies the metadata under the existing generation. A verified binding change retires it. Ingress overflow drops the affected market's pre-gap batch, records a history gap and retires both of its component views until the barrier and new readiness pass. Transport disconnect and manager termination retire the whole generation before SDK cleanup. A non-transport subscription failure isolates its market for that generation. SDK 0.24 registers callbacks before sending a subscription, so an uncertain handle is left for the owner's verified teardown. Scoped book failures back off within the existing reconnect bounds. Shared provider rate limiting extends that delay.

## Weighted Hyperliquid admission

FastAPI creates one coordinator per lifespan. It counts attempted sends in a monotonic rolling 60-second window. `HYPERLIQUID_REST_WEIGHT_PER_MINUTE` defaults to 900, with a validated range of 60–1,150. The provider documents a 1,200-weight per-IP limit. Mainnet and Testnet share the same process budget conservatively, and each request and cache retains its original endpoint, network, namespace and generation. Other processes on the public IP can use the headroom independently. WebSocket connection, subscription and message limits are separate. [Official REST and WebSocket limits](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits)

| Operation | Reservation and charge |
| --- | --- |
| `meta`, `spotMeta`, `perpDexs`, `metaAndAssetCtxs` | 20 each. |
| `l2Book` | 2. |
| `fundingHistory` | Reserve 45, based on the 500-item time-range page. After a successfully parsed list with a verified count of 0–500, charge `20 + ceil(count / 20)`. A timeout, failed response or unverifiable count retains the full reservation. |

[Official Info pagination and request formats](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint)

The coordinator reserves up to 80 weight for live SDK owners within the configured ceiling. Four of 24 waiting slots are reserved for those owners. A feasible ordinary request joins the priority order after waiting one second, retaining FIFO order with older work. Issuance happens only on an existing owned worker. A wait is bounded by the original deadline. Losing the last reader retires a pending single-flight acquisition, and any send already authorized remains charged. Shutdown retires admission first, then drains existing owner tasks and workers. Retired requests discard late responses. HTTP 429 sets a shared cooldown of at least 30 seconds, honoring a longer valid `Retry-After`. Each owner's existing cache age and local retry policy still apply. Budget metrics record operation and owner, charged and reserved weight, waits, denials, admissions, cache reuse, active work, and rolling usage without recording raw payloads.

| Covered production owner | Covered operations |
| --- | --- |
| Market discovery and financial metadata | Perp DEX inventory, Core/HIP-3 metadata and spot token metadata. Namespace and record caps remain 64 and 4,096. |
| Market summaries | Qualified namespace contexts. Existing 24 owner starts per minute, three concurrent acquisitions, 15-second reuse and 30-second maximum age remain enforced. |
| Advisory observations | Qualified current context, L2, and bounded funding history. |
| Research native metadata | Mainnet SDK `meta`. |
| Native REST observations | Mainnet SDK `meta`, `l2Book`, `metaAndAssetCtxs`. |
| Native stream | Startup metadata, book and context, and scoped book and metadata recovery. |
| Operational LIVE | Mainnet SDK constructor `spotMeta` and `meta`, plus context and L2 on startup and recovery. |

The SDK binding is installed before construction and guards the final `Info.post` path. Operational LIVE completes admitted metadata bootstrap before opening its socket. Redirects are disabled on that SDK session. SDK and owned HTTP 429s share the cooldown. Injected fixtures have their own explicitly supplied transports. The dormant private execution adapter is outside this public budget and operational TESTNET remains blocked. RedStone, Kraken, CoinGecko and Yahoo retain their own provider identities and limits.

## Operational callback ingress

The operational adapter uses the native bounded ingress and existing normalizers. The SDK callback verifies channel and market and bounds the retained wire representation to 64 KiB. One FIFO holds eight messages across book and context. An in-progress drain can hold one further batch of eight. A burst schedules at most one outstanding loop wakeup. The adapter preserves exchange ordering, existing same-timestamp economic sequence handling, and actual callback receipt time for context. Duplicates retain their exchange freshness age. Book messages that arrive late or context buffered behind a later bootstrap cannot regain readiness.

Overflow or a malformed callback latches a generation gap. The runtime's market snapshot exposes stale, degraded evidence even while the existing consumer is blocked. The adapter discards the old generation, retires callbacks, and performs its existing bounded reconnect. A post-gap bootstrap must provide an L2 exchange timestamp newer than the retired watermark. Operational context and L2 both must be valid before connected publication. The existing Risk Firewall and final authorization consume the same runtime market source. Stop, Kill and explicit Start/Resume behavior remain in the established runtime.

## Deterministic acceptance and compatibility

The H-C fixtures exercise scoped stale book/context/metadata, an isolated subscription error, a verified binding change, overflow under a stalled consumer, generation retirement while a scoped worker owns an active request, true 60-second boundaries, capacity contention, aging, funding reservations, queued cancellation, active thread ownership and shared HTTP 429 across endpoints. A shared real-SDK fixture on a fake transport charges 62 weight for operational bootstrap, 46 for native bootstrap and 2 for a native scoped repair. The repair retains the native generation and the operational source. The existing suites exercise independent book watermarks, equal-time cases, invalid recovery, REST single-flight, summary capture expiry, generation retirement, SDK teardown, runtime isolation and authority.

| Financial comparison against the frozen worktree | Result |
| --- | --- |
| 38 complete standard PAPER pairs | Byte-identical with SHA-256 `83cfb57fec42efdc9f64114b7891881752da53a904300e7ad4439859445fcf55`. |
| 18 complete asset-aware PAPER pairs | Byte-identical with SHA-256 `257c8d7ec9d510544b2d45302e3be10467f486eb4a1d53a4d63e9d06d8bf1ec9`. |
| Native BTC/ETH/SOL portfolio | Combined 39-dataset, result, receipt and reconciliation digest `22eed4a5c0d67fa94b0e8780e9cbfd3af50276cab4e2b5e2a22e581b449a34ad`. |

The existing authority fixtures cover both AMMs, six supervisory and three advisory-only agents, native and qualified Core/HIP-3 sources, Risk Firewall and FinalQuoteAuthorization. The H-A browser check exercises retained completed results, terminal freshness, explicit Start/Resume and independent emergency Kill. The H-B suite exercises the signed TESTNET gate, external order quarantine and owned SDK shutdown. [H-A acceptance](AUDIT4_HA_ACCEPTANCE.md) · [H-B acceptance](AUDIT4_HB_ACCEPTANCE.md)

## Regression record

| Check | Executed result |
| --- | --- |
| Full backend | 4,058 passed, 0 failed, 0 skipped, 5 warnings in 640.30 s. |
| H-C fixture cases | 21 passed, 0 failed, 0 skipped. |
| Focused native, provider, runtime and authority suites | 455 passed, 0 failed, 0 skipped. |
| Lifespan fixture and optional ML rerun | 90 passed, 0 failed, 0 skipped. |
| Frontend locked install, type check and production build | Passed. |
| Full frontend tests | 949 passed, 0 failed, 0 skipped. |
| Chromium Phase 15.5B | 6 workflows passed. The native observer and browser released the retired generation and subscriber. |
| Chromium Phase 18.7 | 14 workflows and real 200% zoom passed, including 39 route/mode checks, 71 viewport measurements and 26 automated accessibility scans. |
| Chromium H-A | 4 workflows passed. Deliberate Start/Resume, emergency Kill and historical PAPER results retained their authority and freshness rules. |

Linux verification used Python 3.12.14, pytest 9.1.1, pytest-asyncio 1.5.0, Node 24.19.0, npm 11.9.0, Chromium 151.0.7922.173 and Playwright 1.62.0. The Vite build reported dependency directives and a bundle-size advisory. Phase 18.7 and Phase 15.5B reported zero browser page errors.

## Reproduction and handoff

Run the backend from `backend/` and the frontend from `frontend/` with their test dependencies installed. Run the existing Chromium harnesses serially because they use the same loopback ports.

```bash
python -m pytest -q -rs --tb=short
python -m pytest -q tests/test_audit4_hc.py
python tests/phase155b_soak_runner.py --seconds 10 --max-cycles 20
npm ci && npm run typecheck && npm test && npm run build
```

From the repository root, set `PYTHON` to the backend virtual-environment interpreter and `AXE` to a local axe-core 4.11.1 script.

```bash
"$PYTHON" frontend/tests/browser-phase155b.py --python "$PYTHON" --output work/hc/native
"$PYTHON" frontend/tests/browser-phase187.py --engine chromium --python "$PYTHON" --axe "$AXE" --output work/hc/phase187
"$PYTHON" frontend/tests/browser-phase182.py --audit4-ha --python "$PYTHON" --output work/hc/ha
```

| Architecture priority | Files and behavior |
| --- | --- |
| Reuse | FastAPI lifespan, current worker pools and SDK sessions, source normalizers, native ingress partitions and ring history, cache keys and expiry, and the existing runtime and terminal authority path. |
| Enhance | `live_streams.py`, `history.py`, `hyperliquid.py` and `service.py` for scoped recovery and bounded callbacks. `main.py`, `config.py`, `runtime.py`, the public discovery, metadata, summaries, advisory and native REST modules, and `advisory_coordinator.py` share admission. The existing soak runners and lifespan/browser fixtures exercise the resulting owner boundaries. |
| Add | `provider_budget.py` for weighted admission and `test_audit4_hc.py` for the focused deterministic cases. The existing mixed provider runner records admitted operations and source health. |

H-D covers A4-006 advisory evidence normalization and A4-009 source and freshness labeling. The eventual CI rollout can carry these same regression and compatibility gates. Sustained official-provider checks and deterministic packaging remain open. Signed TESTNET and durable restart recovery are blocked. Firefox/WebKit and native macOS Safari, Windows and physical mobile coverage remain outside this Linux Chromium run. Manual VoiceOver and NVDA sessions remain open. [Release runbook](PHASE18_RELEASE_RUNBOOK.md) · [Roadmap](ROADMAP.md)
