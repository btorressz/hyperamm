# Phase 15.5B — Streaming and provider integrity findings

Reviewed October 29, 2026 (America/Los_Angeles), against merged PR #54 at
`72596ffed757acbcfc6f61ef36376593b77964c1`. Severity describes the supported local,
single-operator observational service. No signed orders, credential compromise,
financial loss or new trading authority was observed.

| ID | Severity | Verified defect / hardening | Resolution and evidence |
| --- | --- | --- | --- |
| 155B-01 | MEDIUM | An explicit wrong channel could be accepted when its payload matched the requested component. Malformed/conflicting updates erased the last accepted component. | Explicit channel matching; rejected input preserves accepted values and timestamps, removes channel-delivery proof, and publishes DEGRADED. L2 recovery requires a validated REST barrier. Stream adversarial suites and backend-generated frontend fixtures. |
| 155B-02 | MEDIUM | The ingress byte limit ran only after allocating/serializing arbitrary callback structures. | Pre-serialization bounds: 8,192 visited nodes, depth 16, 65,536 text characters, bounded containers/pending traversal and 256-bit integers; existing final 64 KiB UTF-8 limit retained. Cyclic/deep/oversized/nonfinite inputs are accounted as loss. Closed ingress returns before traversing retired callbacks. SDK's upstream JSON decoding remains outside this application bound. |
| 155B-03 | MEDIUM | A throwing REST bootstrap left the barrier true; recovery of one bad market could throw out of the shared loop and reconnect all markets. | Failure/cancellation closes the barrier, retained economics alone cannot prove recovery, per-market exceptions stay isolated and repeated recovery has a minimum 250 ms interval. Reconnection suite exercises partial BTC failure while ETH/SOL become AVAILABLE. |
| 155B-04 | MEDIUM | SDK 0.24.0 stop joins the ping sender without a timeout. A cancelled observer runner caused drain to propagate cancellation before joining its pool. | Use the official manager's same stop-event/socket-close primitives, then individually bounded joins for manager/ping threads. Cancelled runner is retired before retained cleanup/pool drain continues. Cleanup uncertainty retains the owner and blocks replacement. Existing actual SDK tests plus new cancellation, stuck-thread and partial-subscription cases. |
| 155B-05 | LOW | SDK wrapper lacked duplicate/scope admission guards even though the service normally supplied the fixed whitelist. History admitted lower generations directly and identical context economics were repeated on reconnect. | Wrapper rejects duplicate opens/subscriptions and unsupported channel/market identities. History tracks highest admitted generation per market and deduplicates stored context economics across generations; gaps remain explicit. |
| 155B-06 | MEDIUM | Native midpoint health could remain HEALTHY after a rejected update. Actual Chromium showed cached provider HEALTHY until the 15-second provider GET despite DEGRADED stream state. Disabled native rows used ERROR. | Backend health respects source error and DISABLED. Two small React changes project new native degradation immediately over cached health without mutating provider evidence, changing prices or enabling collectors. Rendered-component and real Chromium assertions verify the first provider row is DEGRADED. |
| 155B-07 | LOW | Importing standalone observation/provider modules failed through an eager simulation package import cycle. The full suite's earlier imports masked it. | Lazy public package exports preserve the same simulation classes/functions without initializing the engine just to import shared market profiles. Three fresh Python-process import regressions plus independently collected provider suites pass. No simulation economics or execution logic changed. |

The same 35 selected regressions were run in a detached baseline worktree with
permitted loopback execution: **32 failed, 3 passed**. This is deliberate defect
reproduction, separate from the baseline full suite and final acceptance.
[Failure evidence](acceptance/phase155b/verified-baseline-defects.txt) and
[standalone import counterexample](acceptance/phase155b/baseline-standalone-import.txt)
are retained. Some wrapper guards are defense in depth: an exploit through the
existing whitelisted production service is not claimed.

All previous tests remain. One existing parametrized Phase 15.2 context rejection
assertion was strengthened for the requested retained-evidence behavior: instead
of requiring deletion, it now requires exact prior evidence, DEGRADED status,
rejection accounting and removed delivery proof, while retaining cross-market
assertions. No skips, xfails, schema regeneration or weakened input validation.

Phase 15.5A HTTP/WS origin/Host/peer controls, request bounds and diagnostic
redaction are unchanged. All seven live-market routes remain observational;
external mappings stay inactive. Native midpoint/oracle/mark are one Hyperliquid
source group, RedStone WS/HTTP are one provider, consensus remains null and
`authority=NONE`, `read_only=true`, `simulated=false` retain their meanings.
Actual seeded PAPER fills, quotes/orders, ledger, reservations, configuration,
manual kill and final authorization remain equivalent through adversarial actions.

Remaining limits: genuine venue delivery/cleanup/long soak, independent macOS,
external collectors and combined audit remain open. A synchronous SDK/socket call
cannot be forcibly killed by asyncio; a shutdown deadline retains its draining
owner rather than claiming success. The application bounds callback processing,
not the official SDK's initial incoming WebSocket JSON allocation. The unpinned
Pydantic range also permits the independently reproduced older-version schema
mismatch documented in acceptance. None of these limits grants trading authority.
