# Phase 16.2 — deterministic historical market replay

Base: `b8b46acda942f15eef13b4056ec9a9c52c832eab`, latest main with PR #57
merged. This change is for draft review and acceptance only. Do not merge
automatically. Phase 16.3 execution realism requires a separate PR after 16.2
acceptance.

## Scope and authority

Replay reads datasets already admitted by Phase 16.1B `HistoricalStorage`.
The Phase 16.1A contracts, fingerprint rules and import/storage boundary are
unchanged. There is no alternate importer, engine, queue or worker.
`SimulationService.replay_history` adapts evidence through existing
`simulation/replay.py` into the existing `SimulationEngine`. Every engine call
constructs its existing isolated PAPER adapter, risk firewall, final quote
authorization, order manager and accounting service. No operational strategy,
signer, subscription, kill switch, reference state or accounting ledger is
modified.

The existing lifespan-owned single-slot `SimulationExecutor` admits catalog,
provenance and replay operations alongside scenarios and optimization. Its
original shielded-waiter cancellation and shutdown behavior is retained:
cancelling an HTTP request detaches the waiter, **does not interrupt the bounded
worker**, and retains admission until actual completion. Shutdown closes
admission and waits for that work. The optional Redis coordination wrapper uses
the same operation allowlist and local worker; its existing expiring result
mirror remains observational. There is no new job polling or persistent result
service.

## Compatibility with SimulationFrame

Historical datasets permit L2 absence, zero-size levels, and missing mark,
oracle, funding or open interest. `SimulationFrame` requires a complete book
and a complete `PerpMarketContext`, including open interest. This adapter
requires **all four** historical economics fields and positive sizes for every
retained L2 level. It never invents an oracle, mark, funding rate, OI, order book
or external provider reference, and never silently drops zero-size levels.

A new partial context replaces the previous context in full. Missing values
cannot inherit older economics. Rejected candidates carry `INCOMPLETE_FRAME`
and typed `missing_fields`; age failures carry `COMPONENT_TOO_OLD`. A segment
with fewer than two frames is excluded with `SHORT_SEGMENT`. A request without
any usable segment is rejected with `NO_VIABLE_FRAMES`, including its preceding
missing-data reasons. There is no fabricated second frame or successful
zero-frame result. Other structured rejections cover identity mismatches and
frame/segment budgets.

The only derived economics are BBO midpoint, basis ratios and open-interest
notional, calculated from the admitted values. `updated_at` and frame book
timestamps are **simulation evaluation receipt clocks**, not assertions of
exchange source time or fresh native delivery. Every result frame retains its
original immutable book and context observations, including actual receipt
times, source timestamps/verification flags, observer identity and generation.

## Receipt ordering, gaps and explicit assumptions

- Replay uses admitted `(received_at, sequence)` order. Source timestamps never
  reorder events. Context source event time stays unknown.
- At a receipt-time tie, events are consumed in sequence order and one frame
  evaluates the batch's last available components. The frame sequence is the
  final admitted sequence and the receipt lists all consumed batch sequences.
  No microseconds are added to satisfy `SimulationDataset` timestamp rules.
- Components must share observer identity/generation. The default component
  age allowance is zero: both components must have the same receipt time.
  Explicit `policy.max_component_age_ms` enables bounded as-of pairing up to
  30,000 ms. This is a modeling allowance, never proof of freshness.
- Declared gaps, observer/generation changes, unavailable candidates and receipt
  intervals above `policy.max_frame_interval_ms` break segments. The interval
  default is 1,000 ms; its permitted range is 1–60,000 ms. A window starts cold,
  without seeding components from before `start_at`.
- Each segment runs from fresh orders, inventory, risk, history, telemetry and
  accounting, with its own initial capital. There is no cross-gap fill,
  historical markout, funding accrual or continuous portfolio claim. Segment
  returns are not aggregated into an apparent uninterrupted return.
- Results are always `COMPLETED_PARTIAL`, including recordings without declared
  gaps. Snapshots and the absence of declared gaps cannot verify continuity.
- `execution.size_decimals` is required and explicitly user-asserted research
  precision. Existing fixed demo market profiles perform strategy reserve/size
  scaling. Their anchors and complete adapted configuration are retained in
  `captured_configuration_json`; they are not historical metadata or prices.
- Existing frozen `ResearchVaultConfig` supplies bounded hypothetical capital,
  fees and sampled funding assumptions. External reference prices stay absent.
  Existing risk consensus/authorization can consequently suppress every quote;
  a replay need not produce fills.
- PAPER crossing-only fills, including existing maker/taker labels, are
  simulated outcomes. No actual passive fill, actual queue position, latency,
  hidden liquidity or executable fill probability is claimed.

## Immutable identities and reproduction

`HistoricalReplayRequest`, policy, execution assumptions, issues and results
are frozen contracts with immutable nested tuples/evidence. Dataset identity
is pinned by the required expected fingerprint as well as market and ID.
Worker-side request serialization forces revalidation even after a caller uses
`model_copy(update=...)`.

The result retains original dataset/source/observations/gaps fingerprints,
all declared gaps, the full request and its fingerprint, a separate temporal
and execution modeling fingerprint, the captured adapted configuration and
its fingerprint, and every segment's simulation dataset/run fingerprint.
Recorded and synthetic fixture values carry separate explicit provenance.

Each segment archives the complete existing `SimulationResult` as canonical
`simulation_result_json` with its own checked fingerprint. It includes engine
version, metrics, trace, PAPER orders/fills, accounting snapshot/ledger and
accounting fingerprint. The JSON string avoids putting the existing mutable
result/list/dict objects inside an immutable replay receipt. Callers can parse
it into the existing simulation result contract when needed. The outer
`result_fingerprint` binds the full receipt, including exclusions and modeling
assumptions. Deserialization checks all archive/configuration/receipt hashes.

To reproduce, retain the result JSON and securely admitted dataset, use the
same code/dependencies and engine version, and submit the retained request
with the retained strategy/agent/risk snapshot. The adapted strategy, profile
and simulation settings are all retained for engine-level reproduction. The
HTTP endpoint captures current operational configuration copies; when those
inputs change, run/result fingerprints change. There is no API to overwrite
operational configuration from a replay receipt. Fingerprints are content
identities, not signatures, license verification or tamper-proof custody.

## Limited local APIs

Set `HISTORICAL_REPLAY_ROOT` to an existing owner-only local POSIX vault
provisioned under the Phase 16.1B requirements. The default is disabled.
No directory creation, file upload, import, save, delete, remote acquisition,
trade, apply or deployment endpoint is added.

- `GET /api/v1/historical-replay/datasets`: at most the vault's 256 IDs.
- `GET /api/v1/historical-replay/provenance?dataset_id=...`: one validated
  dataset's provenance. IDs remain data and are not interpreted as paths.
- `POST /api/v1/historical-replay/run`: computationally read-only replay.

Example request (replace the fingerprint with the admitted dataset identity):

```json
{
  "dataset_id": "btc-capture",
  "dataset_fingerprint": "0000000000000000000000000000000000000000000000000000000000000000",
  "market": "BTC",
  "execution": {"size_decimals": 5},
  "policy": {"max_component_age_ms": 0, "max_frame_interval_ms": 1000},
  "max_frames": 250
}
```

Wire markets reuse `BTC`, `ETH`, `SOL` for BTC-PERP/ETH-PERP/SOL-PERP. The receipt
window is inclusive. `max_frames` is 2–5,000 across consumed segments; at most
32 segments execute. Excess requests are rejected, never silently truncated.
The existing 5,000-observation/16 MiB admission and 64 KiB API request budgets
remain in force. Catalog/provenance reads also use the single slot, returning
429 while busy. All responses use `Cache-Control: no-store`; disabled storage
or unavailable shared admission returns 503, structured replay rejection 422,
and unexpected failures a generic 500. Filesystem/provider errors do not expose
paths or raw wire data. Existing local-only and request-body middleware apply.

## Native validation

Python 3.12.14. No Docker or GitHub Actions were used. Dependencies were installed
with the actual backend extras, without stubbing application modules:

```sh
python -m venv work/venv
work/venv/bin/python -m pip install -e './backend[test,redis]'
```

From `backend/`, the final focused command was:

```sh
../work/venv/bin/python -m pytest tests/test_phase162_replay.py tests/test_phase161a_contracts.py tests/test_phase161b_importers.py tests/test_phase10_executor.py tests/test_redis_infrastructure.py -q
```

**205 passed**, one dependency deprecation warning, 5.85 s. Replay tests cover
all three markets and both source kinds, repeated full-result determinism and
serialization, missing L2/context/economics, partial-context replacement,
zero-size L2, ties without timestamp jitter, unknown source time, explicit age
modeling, windows, identity rejection, corrupt storage, forged frozen requests,
short/zero viable segments, frame/segment limits, HTTP and executor concurrency,
cancelled HTTP waiters, shutdown, Redis mirroring, and seeded PAPER authority
isolation with the operational kill switch both off and on.

```sh
timeout 300 ../work/venv/bin/python -m pytest tests -q -rs -o faulthandler_timeout=45
```

**2,102 passed, 3 failed, 1 skipped**, one dependency deprecation warning,
73.68 s. The complete backend suite is **not green**. The failures are exactly
the known Phase 15 documentation-related static failures:

- `test_phase8_static.py::test_repository_contains_no_forbidden_oracle_provider_token`
- `test_phase9_static.py::test_phase9_does_not_create_github_actions_or_forbidden_oracle`
- `test_phase10_static.py::test_no_github_actions_or_forbidden_oracle_added`

All three identify existing text in unchanged `docs/PHASE155B_ACCEPTANCE.md`.
They reproduced before implementation against an untouched archive of this
PR's main base, using these commands from the repository root:

```sh
mkdir -p work/baseline
git archive b8b46acda942f15eef13b4056ec9a9c52c832eab | tar -x -C work/baseline
cd work/baseline/backend
../../../work/venv/bin/python -m pytest tests/test_phase8_static.py tests/test_phase9_static.py tests/test_phase10_static.py -q
```

Baseline outcome: **3 failed, 15 passed**, 0.22 s. No baseline documentation was
edited to suppress these failures. The final broad run has no new regressions.
The same static command was repeated against the final tree after adding this
acceptance document: **3 failed, 15 passed**, with the same unchanged document
as the only reported hit.
The skip is
`test_agent_expansion.py::test_offline_training_optional_import_and_real_coefficient_export`
because optional scikit-learn is absent. The warning concerns Starlette's httpx
TestClient deprecation. Native suites used network-enabled execution so the
sandbox permits TestClient's local event-loop machinery; no venue access was
required by these replay fixtures. The initial development focused run had
185 passes and one failing age-policy test; the test allowance was corrected to
span sampled receipts under the implemented unavailable-frame reset policy.

`git diff --check` passed. Local execution logs are retained under ignored
`work/` (`install.log`, `baseline-static.log`, `focused.log`,
`full-backend.log`, `final-static.log`); they are not committed artifacts.

## Unverified acceptance gaps

- Fixtures assert native recording or synthetic origin; no licensed native
  recording was acquired, authenticated or independently completeness-checked.
- No real-provider/live-subscription soak, venue experiment, real Redis server
  or multiprocess crash soak was run. Redis integration uses the existing native
  fake-Redis fixture with Lua support.
- The 5,000-observation, 32-segment and output-retention budgets are code bounds;
  this is not a throughput, worst-case memory or production latency certification.
- The pre-existing storage POSIX/local-owner/crash-recovery trust limits still
  apply. Result files are returned to callers, not automatically persisted in
  a new research vault. Reproduction across changed dependencies is unverified.
- Strict pairing can reject ordinary asynchronous recordings. Explicit bounded
  as-of pairing permits only available economics; synthetic missing-economics
  imputation is unsupported. Gaps and exclusions prevent continuous performance
  interpretation even when some segments execute.
- Cancelling a request does not abort computation; shutdown waits for bounded
  completion under the existing executor contract.
- Frontend workflows, actual queue/passive fills, latency/slippage realism and
  broader execution modeling remain outside 16.2. Phase 16.3 is deferred until
  acceptance of this draft.
