# Phase 17.1A.5 — Native Integration, Contract Hardening & Acceptance

**Recommendation: PASS for Phase 17.1A; ready to begin Phase 17.2 within its separate integration scope.** Accept only the configuration foundation; portfolio execution and aggregate performance remain unimplemented.

## Starting revision and independent PR review

Reviewed merged [PR #73](https://github.com/btorressz/hyperamm/pull/73), its entire 13-file, 758-line additive diff (`git diff 82e7649^1 82e7649`), and each model, validator, receipt, fixture, test and documentation change. Starting latest fetched `main`: `82e7649a47fd5e7f15646a7c30de9573232b5477`; PR head: `21092b8b1797c7c50f8fd776938c000da51f1c5b`; predecessor: `d21f66978ea83384e1bc07d3d53bacd355a23a94`. Branch: `phase17/17-1a5-native-acceptance`.

Executed November 11, 2026, Pacific time, on managed Linux x86-64/glibc 2.41, Python 3.12.14, pytest 8.4.2, Pydantic 2.13.5, Node 24.19.0 and npm 11.9.0. Used the existing `/workspace/.hyperamm/venv`; installed unchanged project extras with `python -m pip install --cache-dir /workspace/.hyperamm/pip-cache -e '.[test,redis]'`. This corrected preinstalled redis 8.1.0 to the declared 6.4.0 range. No product dependency or lockfile changes. Bare system `python -m pytest` initially could not import pytest; native execution below uses the prepared interpreter.

## Original REUSE / ENHANCE / ADD plan and completeness

The original 60% reuse / 15% enhancement / 25% addition figures describe architecture, not line quotas. Existing snapshot, market, financial and fingerprint contracts provide the appropriate reuse boundary; no second configuration engine is needed.

| Workstream | Original requirement | Actual PR #73 implementation | Starting gap | Correction and final disposition |
| --- | --- | --- | --- | --- |
| 17.1A.1 | Versioned, immutable, bounded PAPER portfolio contracts | All eight requested types, USDC/BTC/ETH/SOL, one scenario per allocation, captured strategy/agent/risk/simulation/profile | PARTIAL: nested copied models could bypass field validation | Portfolio-local `revalidate_instances="always"`, validation before fingerprint/receipt verification; PASS after native adversaries |
| 17.1A.2 | Exact allocation, reserve, simulation/accounting reconciliation | 80-digit accumulation, 18 fractional places, 1e12 bound, positive unique allocations, exact per-market capital | PARTIAL: public reconciliation helper did not validate its own financial bounds/types | Reuse the existing portfolio exact-decimal validator at the helper boundary; PASS |
| 17.1A.3 | Canonical provenance from validated inputs | Self-checking configuration/allocation/capture receipts, explicit unauthenticated source labels | PARTIAL: equivalent captured capital spellings changed hashes; direct nested invalid config and copied receipt verification bypasses | Normalize validated portfolio captures with accounting canonicalization and rebuild existing comparison snapshots; revalidate receipt/config; PASS |
| 17.1A.4 | Executed deterministic, integration and security tests | Four suites and a reusable fixture, previously NOT RUN | PARTIAL: 48 native tests passed but omitted the reproduced defects and several required adversaries | Add 67 native adversarial/integration cases; 115 portfolio tests PASS |

ADD consists of one focused acceptance test file and this report. ENHANCE is confined to three existing files in `portfolio_research`. The original five package files remain the complete production package; no route, worker, engine, queue, database, frontend component or authorization mechanism was added.

## Reuse and existing-module enhancement decisions

| Module | Existing support sufficient? | Enhancement necessary? | Action |
| --- | --- | --- | --- |
| `simulation/models.py` | Yes | No | Reuse `stable_fingerprint`; existing SimulationResult/dataset/metric ownership is preserved. No placeholder portfolio result consumes or aggregates these metrics. |
| `simulation/market_profiles.py` | Yes, with existing comparison validation | No | Reuse BTC/ETH/SOL literals, market order, profile builder, native precision and `research_strategy`; comparison capture verifies market, size precision, supported profile and rebuilt profile fingerprint. |
| `simulation/research_vault.py` | Yes | No | `ResearchVaultConfig.to_simulation()` carries capital, fees, funding and utilization into captured existing SimulationConfig/AccountingConfig. Six new compatibility cases exercise the conversion. |
| `accounting/config.py` | Yes | No | Reuse `bounded_exact_decimal`; portfolio retains its stricter local 18-place/1e12 bound. Reuse `accounting/models.py:canonical` to normalize numerical identity inside portfolio captures. No ledger semantics changed. |
| `risk/firewall.py` | Yes | No | Preserve quote/base units and fraction-based drawdown/utilization concepts. Portfolio risk fields are static research ceilings; only captured utilization is compared here. Aggregate enforcement belongs to 17.3. `FinalQuoteAuthorization` is unchanged. |

Also reviewed and reused `simulation/config.py` (frame bounds/PAPER execution), `accounting/models.py` (immutable ledger/equity/PnL evidence and canonical decimals), `strategy/models.py` (both supported AMMs and strategy feasibility), `agents/config.py` (deterministic/heuristic/predictive SHADOW settings), and `research_replay/provenance.py` (source trust conventions and shared fingerprint algorithm). `research_replay/comparison.py:ComparisonConfigSnapshot` remains the canonical, detached five-domain capture. Its validation is reused unchanged, including complete normalized configuration, DEMO/PAPER restrictions and domain fingerprints. Existing result fingerprints are untouched.

## Reproduced defects and corrections

1. A copied budget with `quote_currency="USD"` was admitted as a nested model. A copied portfolio with `execution_mode="TESTNET"` could be embedded in a self-consistently hashed receipt. Frozen models alone did not establish validation. All portfolio types now revalidate instances at model boundaries; fingerprinting, receipt creation and receipt verification also validate their inputs. Copied scenario source/authority/frame restrictions, allocation fields and risk fields are tested. No operational model validation was weakened.
2. Constructing otherwise equal captures with `40000` and `40000.00` gave different portfolio fingerprints. Normalization now reuses accounting's exact Decimal canonicalizer and each existing domain model's JSON serializer before rebuilding ComparisonConfigSnapshot. This preserves tiny scientific-notation amounts as well as equivalent financial spellings, without altering existing single-market algorithms. Existing draft portfolio fingerprints can change and callers must regenerate those configuration receipts; no executed portfolio results exist to migrate.
3. Direct `allocation_totals()` calls bypassed model-level float/bool/precision/magnitude restrictions. Total and every amount now pass the same exact validator before arithmetic; positive totals and allocations remain mandatory.

The original fixture required no correction: `research_strategy`, ResearchPerpMarketProfile, ComparisonConfigSnapshot.from_payload, SimulationConfig, AccountingConfig, RiskFirewallConfig and AgentConfig all execute together natively. An initial supplemental normalization attempt used fixed decimal strings directly in strict snapshots; the tiny-residual test exposed the mismatch with existing scientific-notation JSON. The final implementation uses domain serializers, retaining the strict comparison validator. A test initially expected Pydantic ValidationError from an existing builder that raises ValueError; its assertion now matches that actual API. No test was removed or skipped.

## Capital, market, provenance and authority evidence

- The original 100,000 USDC example reconciles exactly: BTC 40,000 + ETH 35,000 + SOL 20,000 + reserve 5,000. Single/two/three-market, full/partial allocations and all six order permutations pass. A large fractional budget retains reserve `0.999999999999999999`; direct reconciliation remains exact under an ambient Decimal precision of eight.
- Simulation initial equity and accounting initial equity must each equal the assigned allocation; accounting must remain enabled. Reserve minimum and over-budget cases fail closed. Unsupported currencies/markets, duplicate allocations/scenarios, bool/float/nonfinite/negative/zero money, exponent bombs, overprecision and excessive magnitude are rejected.
- BTC allocation with ETH capture, SOL strategy with BTC profile, altered profile fingerprints, invalid frame types/bounds and nested forged capture fingerprints are rejected through the existing snapshot and portfolio validators.
- Equivalent financial spellings, repeated captures and reordered valid inputs give the same identity. Changed capital/budget/scenario, AMM, agents, risk, profile source, simulation controls, fees, funding and utilization change identity. All receipt hash components are rechecked. A modified configuration cannot retain its original receipt. Fingerprints prove consistency, not signatures or ownership-independent authenticity.
- Evidence is frozen; configurations returned by `captured.inputs()` are detached. New tests preserve passed ResearchVault/SimulationConfig objects and snapshot actual runtime strategy/agent/risk/kill-switch/authorization/accounting/ledger/orders/fills/quotes/TESTNET state before and after portfolio validation. Execution adapter submit/cancel/replace/account-state paths are guarded against calls. The existing isolation scan confirms no portfolio API, engine construction, task creation or operational state references. The package has no wallet service or signing/order execution path.
- `PortfolioResearchResult` admits only NOT_EXECUTED with null aggregate equity/PnL, false synchronized-window evidence and no execution authority. Claims of completed simulation, real fills, aggregation or synchronization fail validation. Source kind is deterministic-scenario-only; authenticated source/licensing/engine-attestation upgrades are rejected.

## Native verification

Commands below ran from `backend/` with `python` resolving to `/workspace/.hyperamm/venv/bin/python`. Counts are separate runs, not additive totals.

| Check | Result |
| --- | --- |
| Original four portfolio suites, before changes | PASS: 48 passed, 0 failed/skipped, 1.45 s |
| Four original suites plus `test_phase171a_hardening.py`, final | PASS: 115 passed, 0 failed/skipped, 1 warning, 9.88 s |
| Existing focused compatibility selection below | PASS: 407 passed, 0 failed/skipped, 1 warning, 58.52 s |
| Full `python -m pytest tests -q -rs` | PASS: 2,635 passed, 0 failed, 1 optional ML skip, 1 warning, 160.53 s |
| Separate-process comparison against untouched starting main | PASS: all six complete scenario/replay/accounting/receipt digests equal |
| `cd frontend; npm ci --cache /workspace/.hyperamm/npm-cache` | PASS: 27 packages installed, unchanged lockfile |
| `npm run typecheck` | PASS |
| `npm run build` | PASS: Vite production build, 2.24 s |
| `npm test` | PASS: 717 passed, 0 failed/skipped, 15.343 s |

```bash
python -m pytest tests/test_phase171a_contracts.py tests/test_phase171a_allocation.py \
  tests/test_phase171a_provenance.py tests/test_phase171a_isolation.py -q -rs
# Final portfolio acceptance additionally includes tests/test_phase171a_hardening.py.
python -m pytest tests/test_phase165a1_contracts.py tests/test_phase165d_acceptance.py \
  tests/test_phase166d_acceptance.py tests/test_phase1641_acceptance.py \
  tests/test_phase14_research_vault.py tests/test_phase146_research_markets.py \
  tests/test_phase162_replay.py tests/test_phase11_accounting.py \
  tests/test_phase11_simulation.py tests/test_phase10_simulation.py \
  tests/test_phase8_risk_firewall.py tests/test_strategy_risk.py -q -rs
python -m pytest tests -q -rs
```

Cross-revision parity reused existing `test_phase166d_acceptance.py:custom_accounting_case` in separate processes importing each checkout's backend/tests. For each of BTC/ETH/SOL × gap/crossing, create fresh private HistoricalStorage, then call that helper with its market and kind. Compare the returned SHA-256 of complete scenario/replay/receipt JSON; all six match exactly, including custom capital `12345.123456789123456789`, modeled execution, fees/funding, 0.75 utilization, archives and original fingerprints. Existing tests verify unchanged PAPER accounting and guarded TESTNET authorization. No signed exchange operation was performed. Local harnesses/logs remain ignored under `work/`.

The full-suite skip is `tests/test_agent_expansion.py:406`: optional scikit-learn is absent. No backend failure occurred, so no pre-existing failure needed baseline attribution. Post-documentation static authority suites also pass: 18 tests, 0.28 s.

Warnings: backend Starlette/httpx TestClient deprecation; frontend React Query `use client` bundling notices, Vite chunk over 500 kB, and unavailable browser storage in the Node test harness. No warnings were suppressed. Browser screenshots/tests are NOT RUN for this backend-only change, as allowed by the task.

## Final gates and deferred requirements

| Gate | Disposition |
| --- | --- |
| PR #73 review and REUSE / ENHANCE gap analysis | PASS |
| 17.1A.1 contracts, 17.1A.2 allocation, 17.1A.3 provenance, 17.1A.4 security coverage | PASS |
| Strict Decimal, BTC/ETH/SOL identity, profiles, Vault/accounting, tamper rejection, deterministic fingerprints | PASS |
| Read-only/no-authority isolation and existing single-market compatibility | PASS |
| Full backend regression | PASS |
| Frontend typecheck/build/tests | PASS |
| Compact Markdown acceptance evidence | PASS |
| Physical Redis integration | BLOCKED: separate external gate; fakeredis/native local tests do not satisfy it |
| Phase 16.6B lifecycle/recovery | NOT RUN: remains deferred |
| Historical multi-market window synchronization and source/dataset binding | NOT RUN: deferred to applicable Phase 17 integration |
| Multi-market orchestration / aggregate exposure and PnL | NOT RUN: Phase 17.2 / Phase 17.3 |

There are no temporal-window or historical-dataset inputs in this version, so there is no passing temporal-alignment test to invent. The contract explicitly rejects synchronized/aggregate performance claims. Phase 17.2 must bind actual admitted per-market dataset/source identity and prove window compatibility before making any synchronization claim. Exposure snapshots are unverified single-market observations, not portfolio accounting. Portfolio risk limits do not yet calculate or enforce aggregate risk. Stress intelligence, terminal UI and multi-market browser acceptance remain 17.4–17.6. No fabricated datasets were added; parity reused existing clearly labeled test fixtures.

**Readiness for Phase 17.2: PASS for the independently verified configuration foundation.** No merge is authorized by this report; delivery is a separate draft PR.
