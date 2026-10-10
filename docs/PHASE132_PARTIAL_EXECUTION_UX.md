# Phase 13.2 partial implementation — execution evidence UX

This branch deliberately addresses one high-value correctness defect first, without taking on the entire Phase 13.2 redesign.

## Implemented
- Introduced `frontend/src/utils/quoteEvidence.ts` to classify backend `OrderStatus` evidence rather than treating every non-FILLED status as RESTING.
- Classifies `OPEN`/`PARTIALLY_FILLED` as active retained evidence, `UNKNOWN`/unrecognized as uncertain, and `FILLED`/`CANCELLED`/`REPLACED`/`REJECTED` as historical evidence.
- Does **not** infer a matching order from side + level alone: requires exact normalized price and size. Unmatched authorized quotes report missing matched order evidence; historical slot records cannot be silently treated as current.
- Separates STRATEGY/AGENT proposals from final AUTHORIZED quotes so pre-authorization stages can never be represented as resting venue orders.
- Reworks the existing quote-ladder display with standard repository formatters, explicit evidence descriptions, and order IDs for inspection.
- Adds `frontend/tests/quote-evidence.test.cjs` with **11 new test definitions** for status categories, matching, and proposal-versus-authorized behavior, and registers them in the existing test runner.

## Validation
- GitHub repository source and backend OrderStatus enum were inspected; only frontend display and test files are modified.
- **Not yet run:** `npm ci`, `npm test`, `npm run typecheck`, production build, and real Chromium integration. This execution environment cannot reach the GitHub/npm network and does not have the repository's React/dependency tree available locally. Do not infer acceptance or merge readiness from the code review alone.
- Run all existing 164 frontend cases plus new cases, typecheck, build, and browser observation on the branch before merging.
- Run backend regression as needed; backend implementation was not changed.

## Scope
No API/schema/backend mutation, AMM model, risk, signing, accounting, agents, GitHub Actions, Docker, Postgres or mainnet changes. No order placement or control invocation. Phase 13.2 Dashboard, Markets, AMM Settings, broader Risk and Execution UX, and browser acceptance remain pending; Phase 13.3 remains untouched.

## Base and continuity
Based on merged PR #41 commit `eade78350c22dcc2fd27e6aeaa6f0c7729e2c9e2`. Review this as an independent partial Phase 13.2 draft, and then build the remaining Phase 13.2 work onto a merged base or explicit dependent branch.
