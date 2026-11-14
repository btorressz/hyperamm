# Audit 3.0 — ChatGPT targeted remediation handoff

Base: `main` at `9351683cf4f9877f0c2d083e4b1415ded1f2515c`. This is a **review-only draft**; no native backend, npm, axe or Chromium suites have been executed in the connected GitHub environment.

## Changes

- **A3-002 — strategy update preflight:** Handle stale perp-context `ValueError` in the existing `StrategyFeasibilityError` boundary, preserving explicit HTTP 422 and state before cancellation/invalidation.
- **A3-004 — unsupported HIP-3 precision:** Explicitly reject non-native-perp asset IDs in the guarded TESTNET-only normalizer. Native-perp precision is unchanged. **This does not enable builder perps or spot trading.**
- **A3-007 — Kraken heartbeat:** Ignore strictly shaped Kraken v2 heartbeat control frames in the transport loop without creating/revalidating price evidence, advancing source timestamps or degrading a fresh ticker. Unknown frames continue to degrade.
- **A3-006 — partial accessibility:** Add document language, focusable/named Reference Source and Agent Event scroll regions, improve identified small text contrast/size and prevent financial values breaking across table cells. These CSS changes require real-browser visual and axe validation; do **not** mark A3-006 CLOSED on this source-only evidence.

New focused tests: `backend/tests/test_audit3_chatgpt_hardening.py`.

## Local acceptance required before merging

```bash
cd backend
python -m pytest -q tests/test_audit3_chatgpt_hardening.py
python -m pytest -q tests/test_phase122_amm_hardening.py tests/test_phase8_runtime.py
python -m pytest -q

cd ../frontend
npm ci
npm run typecheck
npm run build
npm test
```

Run the existing Chromium browser harness for Risk, Agent Events and settings with 1440px and 390px widths, plus 200% zoom, keyboard Tab/arrow-scroll, and axe WCAG 2 A/AA. Verify no horizontal document overflow, accessible financial values, and computed contrast ratio >= 4.5:1 for normal small text. Inspect all other UI and API regressions before accepting.

## Deferred by this draft

- **A3-005** custom liquidity-stress preflight: still needs a precision-aware feasibility check before baseline execution and a focused end-to-end stress regression; not addressed here.
- **A3-006** full accessibility closure: partial source patch only; needs measured Chromium/axe evidence and any remaining CSS adjustments.
- **A2-005**: external platform/lifecycle repeat acceptance remains partial; not resolved by these changes.
- **A3-001, A3-003, A3-008** were already remediated in merged PR #82.

Do not use this branch as evidence of signed TESTNET, HIP-3 support, production readiness or successful provider soak. Preserve existing local PAPER/signing restrictions. Merge only after a reproducible local validation or subsequent corrections.
