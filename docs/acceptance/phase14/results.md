# Phase 14 concise local validation results

Base: `bf547ad889d0e549b8d67beb966323614f2a5c27`; PRs #43–#47 merged; clean preflight.

| Check | Actual result |
| --- | --- |
| Clean unchanged-base backend | 1125 passed, 0 failed/skipped, 1 warning, 57.72s |
| Baseline frontend | 376 passed, 0 failed/skipped/cancelled, 26.52s |
| Baseline TypeScript / build | Passed after locked dependency reinstall |
| Final backend (`pytest -q`) | 1185 passed, 0 failed/skipped, 1 warning, 46.33s |
| Focused research/API/accounting | 85 passed, 0 failed/skipped, 1 warning, 8.75s; final full includes additional Redis comparison case |
| Final frontend (`npm test`) | 410 passed, 0 failed/skipped/cancelled, 17.05s |
| Final TypeScript (`npm run typecheck`) | Passed |
| Final production build (`npm run build`) | Passed; 3.97s; existing TanStack notices / ~527 kB main chunk advisory |
| `pip check` / compileall | Passed |
| Chromium | 72 route/viewport checks + 13 workflows; zero page exceptions / document overflow |
| Recorded UI POSTs | 14, all preview / comparison / simulation / optimization; zero trading mutations |
| Diff whitespace | Passed |

Python 3.12.14, Pydantic 2.14.0, FastAPI 0.143.0, Node 24.19.0. One backend warning
is upstream Starlette/httpx TestClient deprecation. The historical terminal-schema
Decimal mismatch did not reproduce on unchanged base or final; test/schema untouched.

Browser-only delayed/malformed preview fixtures are declared in the report. Runs,
optimizer, comparison, backend restart and screenshots are actual local DEMO/PAPER.
Real runtime strategy/config, manual kill, orders, ledger fingerprint/version and
TESTNET eligibility stayed unchanged before restart. One dataset feeds both runs.
`comparison-summary.json` contains a small actual result excerpt without traces.

Development attempts were corrected and are not counted as passes; see the detailed
acceptance report. macOS, external providers/source integrity, real Redis, signed
TESTNET, long soak and unrelated audit/Phase 13.2A–E gates remain open. Phase 15
untouched. No durable storage or future-profitability claim. Draft only; do not merge.
