# Audit 4.0H-B acceptance

Frozen GitHub `main` was `0e641ab1df48f91cba6f8816aae7401a1eb5c617`, the merge commit of PR #106. The scope is A4-001, A4-002 and A4-011. The independent audit and local hardening predecessor remain the historical sources. [Audit 4.0](../AUDIT_REPORT_4.0.md) · [PR #105](https://github.com/btorressz/hyperamm/pull/105) · [PR #106](https://github.com/btorressz/hyperamm/pull/106) · [H-A acceptance](AUDIT4_HA_ACCEPTANCE.md)

| Finding | Disposition | Scope |
| --- | --- | --- |
| A4-001 | **PASS for local fail-closed behavior. Signed TESTNET is BLOCKED.** | All shipped operational sources and direct submission calls fail before SDK transmission. |
| A4-002 | **PASS for unsigned current-inventory reconciliation. Durable recovery is BLOCKED.** | Unknown or unavailable account inventory quarantines issuance. Retained ownership controls cancellation. |
| A4-011 | **PASS in SDK 0.24.0 local lifecycle fixtures. Private transport acceptance is NOT RUN.** | Owned resource cleanup, cancellation, incomplete shutdown and callback retirement are covered with substituted transport. |

## Baseline reproductions

| Finding | Offline observation on frozen main | Cause |
| --- | --- | --- |
| A4-001 | A deterministic ETH DEMO frame produced `VERIFIED` reference consensus and an authorized TESTNET ladder. One fake `exchange.order` call followed. | Operational source selection and execution mode were independent. The final authority did not bind native TESTNET source provenance. |
| A4-002 | With empty local history and a fake BTC order waiting in the account inventory, reconciliation returned with zero calls to the inventory reader and no unknown exposure. | The empty-local shortcut skipped the account. Nonempty reconciliation considered only locally indexed orders. |
| A4-011 | A fake SDK constructor retained one allocated WebSocket manager when metadata failed. After the adapter's `close()`, the adapter held no Info reference and the fake manager was still allocated. | The return from the constructor was the first point where the adapter captured Info. Cleanup also depended on successful subscription registration. |

All three baseline probes used deterministic clients without outbound exchange transport or signing. Prior authority, accounting and lifecycle constraints were traced through the Phase 8 risk firewall and execution work, Phase 11 accounting, Phase 12 terminal integrity, Phase 17 native portfolio acceptance and Phase 18 evidence and research ownership. [Phase 8 #5](https://github.com/btorressz/hyperamm/pull/5) · [Phase 11 #12](https://github.com/btorressz/hyperamm/pull/12) · [Phase 12 #40](https://github.com/btorressz/hyperamm/pull/40) · [Phase 17 #80](https://github.com/btorressz/hyperamm/pull/80) · [Phase 18 #104](https://github.com/btorressz/hyperamm/pull/104) · [Audit 3 acceptance](AUDIT3_FINAL_REMEDIATION_ACCEPTANCE.md)

## A4-001 operational source and request authority

| Operational source owner | Evidence and eligibility |
| --- | --- |
| DEMO | Synthetic L2 and perpetual context. Reference consensus measures internal agreement and can report `VERIFIED`. Supported for PAPER. Unsupported for TESTNET. |
| Hyperliquid LIVE | Existing native Hyperliquid public market-data adapter uses the Mainnet endpoint. Its configured market symbol, L2 freshness and perpetual context retain their existing PAPER semantics. Unsupported for TESTNET. |
| Core/HIP-3 Explorer, public summary and scenario data | Separate read-only or hypothetical research provenance. The catalog network and market identity cannot grant operational authority. |
| TESTNET-qualified operational source | **Unavailable.** There is no trusted producer of same-venue, same-network and same-Core-asset L2, perpetual and reference evidence for the private adapter. |

Settings rejects TESTNET at initial validation. Runtime construction checks again for programmatic copies. Updates reject the proposed TESTNET configuration before invalidating the published PAPER graph. Service startup, strategy Start and Resume, quote authority creation and runtime concrete authority reject an unsupported source. The private adapter independently denies normalization and new submissions, including direct calls with a substituted authority callback. Its TESTNET endpoint and account binding still constrain account reads and owned cancellation. The existing normalized Decimal and wire checks, RiskFirewall, capital and authorization checks remain exercised by legacy downstream fixture tests with the source gate explicitly stubbed. [Settings](../backend/app/config.py) · [Operational source](../backend/app/market_data/service.py) · [Runtime](../backend/app/runtime.py) · [Execution](../backend/app/execution/hyperliquid.py)

A separate source integration must define an owner-issued, revocable binding between the official Testnet transport, account and native market identity including Core asset index. It must bind the current L2, perpetual and reference observation clocks and session generation to the normalized concrete request and recheck after awaits. The current release has no positive provenance token, browser input or feature flag that can satisfy that contract.

## A4-002 venue scope, uncertainty and restart

The adapter reads the complete bounded inventory available from SDK `frontend_open_orders` for the configured account in the default Core/spot scope and each named perpetual DEX returned by the same endpoint. Missing scope lists, failed reads, capacity limits, malformed orders, duplicate identities, conditional exposure and conflicting point status checks block readiness. Account and network are bound by the same official endpoint, exact account request and current client generation. Where the SDK response carries explicit account or network fields, conflicting values are rejected. Readiness progresses from `NOT_CHECKED` to `CHECKING` and then `VERIFIED` or `BLOCKED`. The adapter bounds each inventory check to 32 scopes, fewer than 2,000 open rows and at most 16 point-status lookups. A verified observation expires after ten seconds or on a venue update, account change or session retirement. [Normalizer](../backend/app/execution/venue_inventory.py) · [OrderManager](../backend/app/execution/order_manager.py)

Only a retained exact order ID or derived client ID can establish ownership. Coin, side, limit price, original size and remaining size must agree with retained evidence. Known partial fills update remaining exposure and stay pinned until position/account evidence is consumed. A cancel acknowledgement alone leaves a verification pin. A still-open row, contradictory or missing order status or unavailable response keeps the account blocked. The local strategy order list remains separate from unmanaged account inventory. The risk API exposes the reconciliation state and unmanaged count when the TESTNET adapter is selected. Terminal diagnostics show unresolved venue exposure instead of an old success timestamp. [Risk API](../backend/app/api/risk.py) · [Execution history and pins](../backend/app/execution/hyperliquid.py)

After restart, unexplained active rows quarantine the strategy, including same-market rows, rows without a client ID and rows on another market. Fresh authoritative empty inventory can verify current open-order scope. The process cannot recover a previous owner's identity, an interrupted submit that disappeared before the next read, or the fees and fills of a terminal order discarded with the process. Kill latches locally and cancels only retained strategy client IDs. It retains unconfirmed cancellations, leaves unmanaged rows alone and reports unresolved exposure. There is no manual acknowledgment override. This change uses the existing bounded local history and adds no journal. Durable intent, ownership, terminal status and account fill recovery remain prerequisites for any signed rollout.

## A4-011 resource ownership

Owned Info is recorded before its SDK constructor runs. The SDK 0.24.0 Exchange methods share the already-owned Info. The adapter preallocates Exchange and initializes its HTTP transport with the SDK API initializer, avoiding the nested Info construction and hidden session in the SDK Exchange constructor. Both owned HTTP sessions and each returned subscription handle have an explicit release path. Injected clients are borrowed, and cleanup releases adapter subscriptions without closing borrowed sockets or sessions.

Private calls serialize with reconciliation and cancellation. The adapter retains a timed-out or cancelled worker until it exits. Cleanup retires callback generations, unsubscribes known handles, signals the SDK stop event, closes the socket and joins the manager and ping threads with bounded waits. Incomplete cleanup retains ownership, blocks replacement and can be retried through close. Runtime shutdown still attempts SDK teardown when owned cancellation fails. Errors exposed by this adapter use fixed, redacted reasons. The tests exercise SDK constructor ordering with substituted HTTP and WebSocket transport and include the real SDK manager and ping threads with a local socket stub. Actual private SDK transport shutdown, venue error payloads and external reconnect behavior remain **NOT RUN**. [Adapter](../backend/app/execution/hyperliquid.py) · [Lifecycle and combined fixtures](../backend/tests/test_audit4_hb.py) · [Public adapter shutdown regression](../backend/tests/test_phase155b_sdk_lifecycle.py)

## Architecture inventory

- **Reuse.** Existing runtime, market/perp/reference models, risk and final authorization, Decimal normalization, OrderManager and Kill, bounded history and accounting pins, SDK methods and test doubles.
- **Enhance.** Settings and strategy lifecycle rejection, current source identity at authority, account-wide reconciliation, owned cancellation verification, private lifecycle and operator diagnostics.
- **Add.** Small venue inventory parser, readiness states and deterministic regressions. The existing operational and research graphs remain the owners of their respective data.

## Verification

The Linux tests used Python 3.12.14, FastAPI 0.141.1, pytest 9.1.1, Hyperliquid SDK 0.24.0, Node 24.19.0, npm 11.9.0 and Chromium 151.0.7922.173. Browser requests used loopback DEMO/PAPER and deterministic provider fixtures. All TESTNET fixtures used fake or stubbed transport and no real wallet keys.

| Verification | Fresh result |
| --- | --- |
| Focused backend | PASS. 323 execution, lifecycle, authority and integration tests passed. Separately, 456 Phase 8/11/12/17/18 and Audit 3 regression tests passed. Both runs had 0 failures and 0 skips. |
| Full backend | PASS. 4,037 passed, 0 failed, 0 skipped, 5 warnings in 665.07 seconds. |
| Frontend install, typecheck, tests and build | PASS. 949 passed, 0 failed, 0 skipped. |
| Chromium Phase 18.7 fixture suite | Two complete passes with Playwright 1.62.0 and axe 4.10.3, including the final code. Each covered 14 workflows, all 13 routes in each of three modes, 71 viewport checks, 26 scoped axe scans with zero violations and zero page errors. Two repeat attempts hit an intermittent Chromium response-body error in the portfolio test harness. |
| Targeted Chromium H-A regression | PASS with Playwright 1.65.2. Four workflows covered retained PAPER results, terminal disconnect, Stop and Kill, fresh-only Start and Resume after process replacement, and retired requests. |
| Fixed-clock standard and asset-aware PAPER | PASS. 38 standard and 18 asset-aware pairs matched frozen main byte-for-byte. Controlled SHA-256 values are `83cfb57fec42efdc9f64114b7891881752da53a904300e7ad4439859445fcf55` and `257c8d7ec9d510544b2d45302e3be10467f486eb4a1d53a4d63e9d06d8bf1ec9`. Original PR #100 aggregate attestation remains open. |
| Native BTC/ETH/SOL portfolio | PASS. Published combined digest `22eed4a5c0d67fa94b0e8780e9cbfd3af50276cab4e2b5e2a22e581b449a34ad` reproduced. |
| Signed TESTNET, actual private transport and external provider acceptance | **NOT RUN.** This work adds no signed venue acceptance or signing permission. |

The compatibility probe compares complete serialized receipts and results across the candidate and frozen main. The native probe follows Phase 18.2G. Coverage includes both AMMs, modeled capital and accounting, six supervisory agents, three observational advisories, and the H-A PAPER preflight and terminal behavior. [PAPER probe](../backend/tests/phase187_paper_compatibility.py) · [Native probe](PHASE18_2G_FINAL_HARDENING_ACCEPTANCE.md#native-btcethsol-compatibility) · [Chromium suite](../frontend/tests/browser-phase187.py)

## Remaining work

| Milestone | Findings and acceptance work |
| --- | --- |
| H-C provider and runtime lifecycle | **A4-003** component-scoped native stream recovery, **A4-004** shared weighted provider budget, **A4-008** bounded operational callback ingress. Exercise slow consumers, 429/backoff and isolated stale components with deterministic clocks before separately approved provider checks. |
| H-D research evidence and presentation | **A4-006** reuse qualified public normalization for advisory inputs and validate bounds and denomination. **A4-009** expose source, availability and expiry consistently across Explorer and PAPER. Verify both at exact receipt boundaries without changing modeled financial results. |
| Separate TESTNET milestone | Trusted operational Testnet source and evidence binding, durable intent/ownership and terminal-fill recovery, live account-inventory contract validation, then separately authorized signed acceptance with independent review. |

[Original severity and rollout plan](../AUDIT_REPORT_4.0.md) · [Release runbook](PHASE18_RELEASE_RUNBOOK.md)
