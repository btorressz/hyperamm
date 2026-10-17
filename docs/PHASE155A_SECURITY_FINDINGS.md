# Phase 15.5A — Security and research integrity findings

Reviewed October 17, 2026 (America/Los_Angeles), against main
`e656a51c3d378f787281f6e4ba5d6ad020e48135`, including merged PR #53,
Audit Reports 1.0/2.0, the source map, phase acceptance and actual modules.
Severity describes the supported local single-operator trust model. No actual
credential theft, signed order submission or financial corruption was observed.

| ID | Severity | Verified before change | Resolution / evidence |
| --- | --- | --- | --- |
| 155A-01 | HIGH: local browser boundary | `Origin: http://localhost:9999` reached HTTP/WS handlers despite being unrelated to the terminal. CORS alone cannot prevent simple mutation requests or authorize WS. | Exact configured local HTTP(S) origins or same origin; null/non-HTTP origins rejected. Shared HTTP 403/WS 1008 regressions; actual Chromium HTTP negative paths and successful Vite/WS use. |
| 155A-02 | MEDIUM: boundary parsing | `Host: user@localhost:8000` and `Origin: ftp://localhost` reached application code through permissive URL parsing. Duplicate headers had last-value semantics; forwarding input was not explicitly excluded. | Strict authority/port/serialized-origin parsing; no userinfo, path, whitespace, scoped IP or ambiguous duplicates. Forwarded/X-Forwarded-*/X-Real-IP rejected. Loopback peer and Host still independently required. |
| 155A-03 | MEDIUM: request admission | Existing 64 KiB bound covered selected research POSTs only, retained one ASGI object per chunk, and ran before origin rejection. Other API writes were unbounded at this boundary. | All write methods share the existing bound, reject oversized declared/actual lengths and ambiguous framing, coalesce tiny chunks, and abandon disconnected bodies. Origin rejection precedes body reads. Exact-limit, overflow, 65,536 tiny chunks and framing negatives executed. |
| 155A-04 | MEDIUM: public diagnostics | A selected diagnostic containing `{"api_key":"SYNTHETIC_CREDENTIAL_SENTINEL"}` or a nested Authorization value retained the opaque credential because only text patterns were sanitized. Non-research validation also returned raw input. | Credential-key values redact completely, including nested containers; domain identifiers stay unchanged. All API validation omits input/ctx, masks unknown field/key locations, sanitizes messages and returns no-store. Comparison failures log exception class only and never raw traceback/message. |
| 155A-05 | MEDIUM: configuration integrity | PUT strategy with an unknown `base_spread_bps` field returned 200 and initiated a configuration transition using defaults. | API-only extra-forbid subclass rejects misspellings/protected fields before runtime changes; accepted input converts to the unchanged StrategyConfig. Seeded authority and valid existing API regressions pass. Terminal schema is unchanged. |
| 155A-06 | MEDIUM: evidence presentation | Retained ineligible midpoint values used an unqualified observed label; a historical artifact's individual tables/chart lacked prominent retirement labels. | CURRENT / ELIGIBLE AT CAPTURE, STALE, HISTORICAL and UNAVAILABLE presentation labels; existing COMPARABLE/PARTIAL/NOT_COMPARABLE/UNAVAILABLE wire states preserved. Historical differences clearly labeled; timestamps/values retained without filling gaps. |
| 155A-07 | MEDIUM: response integrity | Missing required PAPER metric properties and metric values inconsistent with attributed source could pass browser shape checks. Output differences incorrectly shared the 1e30 input bound. | Required metrics, exact text-normalized source identity/value consistency and completeness membership checks. Bounded finite output strings allow legitimate large relative differences. No browser financial arithmetic changes economics or authorizes execution. |
| 155A-08 | LOW: session/freshness integrity | Frozen transport age was recalculated from changing wall time; freeze retained a caller-owned object; eviction could retain a nonexistent selected ID. | Capture transit once, advance freshness monotonically, detach frozen data and clear evicted selection. Actual offline/reconnect/unmount/expiry checks and executable abort-generation gate tests prevent late response reactivation. |

## Authority review

PASS: a real seeded PAPER runtime with fills, quotes, accounting/ledger entries,
capital reservations, running/stopped state, authorization and latched/unlatched
manual kill remains unchanged through observation GETs and valid/invalid research.
The existing Phase 15.4 seeded tests also cover all assets, concurrent comparisons,
expiry, cancelled requests and disabled replacement observers. The new HTTP
cancellation test retains the actual worker slot until completion, returns 429 to
a second run, and allows the read-only comparison without SDK activation.

Comparison remains a pure computation over the existing server snapshot. It
cannot submit PAPER/TESTNET orders, apply strategy settings, clear kill, change
capital/accounting, initiate SDK networking, or replace FinalQuoteAuthorization.
Client-provided research remains
`STRUCTURALLY_VALIDATED_CLIENT_SUPPLIED_NOT_AUTHENTICATED`; no execution
attestation, run registry, model promotion, alternate authentication or database
was introduced. No trading/risk/accounting formula or valid strategy economics changed.

## Audit disposition and remaining limits

- A1-009's local boundary is strengthened; remote hosting, proxies/tunnels,
  multi-worker operation and identity-based operator authentication remain outside
  this supported deployment. A local programmatic operator can still make valid
  local requests; browser-origin checks do not authenticate that operator.
- A1-023's selected diagnostic boundary now also covers structured credentials and
  all API validation. This is tested synthetic redaction, not proof that every
  possible secret representation in arbitrary third-party logs is covered.
- A2-005's original failure record remains. Current all-extra regression and actual
  Redis shutdown pass; fresh test-only repetition results are recorded separately
  in acceptance. Linux success does not establish macOS or long-soak behavior.
- No defect in the Phase 15.5B reserved modules was proven by this scope. Their
  genuine venue connection/reconnect/cleanup, provider mappings/time integrity,
  bounded queues/history and long-running soak acceptance remain the collaborator's
  responsibility. The SDK metadata attempt received proxy CONNECT 403; it is a
  network gate, not a successfully validated venue or an application regression.

Full results and platform limits: [acceptance](PHASE155A_ACCEPTANCE.md),
[macOS fallback](PHASE155A_MACOS_FALLBACK.md). Phase 15 is not complete.
