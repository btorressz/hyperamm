# HyperAMM Audit Report 2.0

## Executive Summary

**HyperAMM has a complete AMM MVP and a complete integrated research MVP implementation. Freeze model/agent feature expansion. Resolve the acceptance and hardening findings below, then calibrate and obtain external acceptance.** This is a virtual AMM that compiles liquidity onto a CLOB, not an on-chain swap pool or a custody system.

The current main implements the five material expanded agents plus Predictive Adverse Selection in SHADOW, bounded offline logistic research, isolated simulation/optimization, accounting, optional ephemeral Redis, and all twelve terminal pages. The authority hierarchy remains deterministic. No critical/high defect was established in this audit. Five new **MEDIUM / HARDENING** findings are supported by direct counterexamples or failed acceptance runs. They are not fixed in this PR.

| Verdict | Current result | Meaning |
|---|---|---|
| AMM MVP | **COMPLETE** | Constant-product, concentration over reserve deltas, inventory/adaptation and CLOB integration are sufficient; completion does not mean every valid configuration is hardened. |
| FULL HYPERAMM MVP | **COMPLETE — implementation scope** | Local, single-operator research platform; acceptance caveats remain. |
| LOCAL PAPER ACCEPTANCE | **PASS — runtime/browser; test reproducibility qualified** | Lifecycle, controls, API, streaming and research work locally. Initial normal-extra pytest acceptance failed; later complete extra-enabled acceptance passed. |
| PUBLIC LIVE DATA ACCEPTANCE | **ENVIRONMENT BLOCKED** | No public provider accepted successfully here; proxy CONNECT denied with HTTP 403. |
| AUTHENTICATED PROVIDER ACCEPTANCE | **CREDENTIALS UNAVAILABLE** | RedStone Live configuration/key unavailable; not exercised. |
| SIGNED TESTNET | **NOT EXERCISED** | No signed order or real trade submitted. Fixture acceptance is separate. |
| PRODUCTION | **NOT CLAIMED** | No durability/recovery, remote security, live soak, exchange execution acceptance or profitability certification. |

The tick-collapse question has a concrete answer: **100 distinct `(side, level_index)` slots can occupy two final prices.** Each is a separate PAPER order, and exposure includes every slot. Unchanged reconciliation returns KEEP rather than automatic churn. The costs are redundant slots, correlated replacement work when tolerances are exceeded, and overlapping distribution bars. Rejecting or coalescing is a policy decision, not an emergency exposure fix (A2-003). A separate, more important AMM hardening defect is raw-distance metadata surviving outward tick rounding on the neutral PAPER path (A2-001).

Backend normal-extra run: **990 passed, 1 failed, 1 skipped, 1 warning, 29.42s**. After declared optional ML/Redis extras: **992 passed, 1 warning, 27.94s**. Frontend: **75 passed**, typecheck/build passed. Actual Chromium screenshots succeeded. Real Redis 7.4.11 accepted Pub/Sub, TTL, leases, heartbeat and application outage/recovery. These results do not erase the original test teardown failure (A2-005).

## Audit Baseline & Methodology

| Item | Recorded value |
|---|---|
| Repository | `btorressz/hyperamm` |
| Verified GitHub main / audited baseline | `44fbf22333fa8bf6705684e7f87f7c0fbc2fcbce` |
| Baseline verification | 2026-10-08 22:21:54 UTC / 15:21:54 America/Los_Angeles (PDT) |
| Re-verification during audit | 2026-10-08 22:37 UTC; `git ls-remote origin refs/heads/main` still returned the same SHA |
| Recent merged work | #33 Audit 1.0 current-status update; #34 Agent Expansion, source verified |
| Initial workspace HEAD | `5f3336999d62d9241bb8591b807f48a634f9812f`; fetched main before auditing |
| Audit branch | `audit/full-system-2-0`, created from fetched main |
| Cleanliness | Clean tracked/untracked status before report; installs/build outputs ignored or outside repository |
| Python / Node / npm | Python **3.12.14** / Node **v24.19.0** / npm **11.9.0** |
| Audit 1.0 preserved blob | `3eedb9cb51d823ca16bc024d22426fee7449ed13` |

Inspected the prior finding catalog/dispositions, README, Summary, roadmap, architecture, math, agents, simulation, accounting, references, risk and terminal documentation against current source. Reviewed domain implementations under `backend/app/{amm,strategy,market_data,references,agents,risk,execution,accounting,simulation,research,infrastructure,terminal,api}`, runtime/config/main/dependencies/deployment and frontend pages/components/stores/validators/socket/history/API/CSS/test contracts. Full tests provide broad regression coverage; focused suites and scratch counterexamples provide direct evidence for specific boundaries. This is not formal verification or an exhaustive exploit assessment.

An isolated environment and scratch scripts were kept in `/workspace/work/audit2`, outside tracked repository files. Backend and Vite ran over loopback, initially DEMO/PAPER, signing explicitly disabled. A second DEMO/PAPER instance exercised optional Redis. No source, dependency manifest, test, schema, configuration, roadmap or prior audit was changed. The final repository change is this report only.

Evidence vocabulary throughout:

| Label | Scope |
|---|---|
| IMPLEMENTED | Current code exists and was inspected. |
| TESTED WITH FIXTURES | Deterministic tests/mock venue or source evidence passed. |
| TESTED LOCALLY | Actual local application/browser or direct domain execution passed. |
| FAKEREDIS ACCEPTED | Compatible emulator tests; not a Redis server. |
| REAL REDIS ACCEPTED | Actual Redis server and application probes passed. |
| PUBLIC PROVIDER ACCEPTED | Successful public provider connection/schema/freshness observed; **none here**. |
| AUTHENTICATED PROVIDER ACCEPTED | Legitimate credentials and actual protocol acceptance; **none here**. |
| SIGNED TESTNET ACCEPTED | Actual authorized signed venue lifecycle; **not exercised**. |
| PRODUCTION READY | Operational evidence beyond this audit; **not claimed**. |

## Audit 1.0 Crosswalk

All 27 entries were reconsidered. The prior disposition is recorded separately from what this audit established. **No regression of a specifically closed A1 defect was established.** A2 findings cover additional edge cases and an unresolved acceptance failure; they do not retroactively certify the partial A1 items.

| A1 ID | Audit 1.0 current disposition | Audit 2.0 re-verification / new evidence | Regressed? | Remaining acceptance gate |
|---|---|---|---|---|
| A1-001 | PARTIAL: code closed, signed pending | Current runtime normalizes venue quotes before final validation/authorization; adapter requires exact request membership and SDK wire equality; execution/authorization suites passed. | No established regression | Signed TESTNET wire/lifecycle acceptance. A2-001 concerns neutral PAPER distance metadata. |
| A1-002 | CLOSED | Material book identity independent of sample dedup; conflicting same-sequence economics rejected/version-bound; market/integration tests passed. | No | Public feed schema/freshness and reconnect soak. |
| A1-003 | PARTIAL: code closed, live pending | SDK lifecycle is explicitly owned with bounded backoff/resubscription and fresh-book recovery. Actual adapter retried denied proxy connections. | No | Successful public connection, induced disconnect/resubscribe/fresh recovery. |
| A1-004 | PARTIAL: code closed, live pending | SDK call cancellation drained; subscriptions/socket and threads explicitly shut down; blocked connection start/stop completed. | No | Successful socket/thread teardown soak, not merely denied connections. |
| A1-005 | CLOSED | Retention bounds, incremental fill consumers and pinned uncertain/unacknowledged evidence present; full/focused execution tests passed. | No | Long-session soak; pending authoritative evidence intentionally pins capacity. |
| A1-006 | PARTIAL: code closed, signed pending | All resting orders per slot sum into exposure; surplus cancellation and uncertainty gates remain. Collapse probe has 100 different slots, correctly counted. | No | Signed duplicate/cancel confirmation acceptance. |
| A1-007 | CLOSED | First eligible markout observation is frozen, eviction becomes unavailable; multi-horizon expansion tests passed. | No | Real fill/source cadence calibration. |
| A1-008 | CLOSED | Latest price retains its source timestamp while semantic deadband/provenance identity are separate; reference tests passed. | No | External-provider acceptance. |
| A1-009 | PARTIAL: local boundary, remote pending | Peer/Host/Origin and worker checks retained across new routers; evil Host/Origin 403; forwarded header does not confer authority. Redis remains observation/admission only. | No | Remote authentication/roles/TLS/resource policy, before any remote scope. |
| A1-010 | CLOSED | One cached serialized publication and one-slot client queues; two real WS connections advanced normal shared sequence. | No | Sustained fanout/load acceptance. |
| A1-011 | CLOSED | GET routes return copied/current published observations rather than refresh/reconcile; all safe GETs exercised. | No | Long-running observation stability. |
| A1-012 | CLOSED | Nested NaN/Infinity and invalid ML mode rejected; duplicate/regressive frames rejected; browser utility watchdog closed malformed open socket and reconnected. | No scoped regression | Additional emitted-time/retired-session edge case A2-004. |
| A1-013 | DOCUMENTED / ACKNOWLEDGED | Expanded agents still ERROR to neutral soft advice; five-agent failure tests passed; Phase 8 retains final decision. | Not a closed-code claim | Operator acceptance of relaxation policy and calibration. |
| A1-014 | CLOSED | Action-changing churn window excludes KEEP dilution; capture/markout provenance and retained lifecycle timing explicit; quality tests passed. | No | Venue latency/partial-fill evidence and PAPER realism. |
| A1-015 | CLOSED | Scenario/dataset overlap validated, same holdout honestly labeled, expected candidate errors bounded; optimizer tests and local request passed. | No | Independent empirical holdouts, repeated-selection bias management. |
| A1-016 | PARTIAL: code hardening, calibration pending | Finite ratio/log/statistic guards and per-observation semantics retained; extreme domain matrix exercised. | No scoped regression | Cadence/threshold calibration; additional strategy feasibility gap A2-002. |
| A1-017 | PARTIAL: compatibility documented, cleanup deferred | No NumPy import in app live core; NumPy remains declared intentionally; sklearn lazy/offline. No cleanup performed. | No | Separate justified dependency cleanup; reproducible dependency acceptance A2-005. |
| A1-018 | CLOSED, scoped current-summary repair | Current summaries include twelve pages/new agents and separate historical acceptance; scoped repaired status remains. `docs/ACCOUNTING.md` still contains an older Phase 12 planned sentence outside its listed repair files. | No established scoped regression | Small documentation housekeeping, no production certification from historical counts. |
| A1-019 | CLOSED | Serialized lifecycle, captured ownership, retired callbacks and failed/restart-required state retained; lifecycle/full tests and config controls passed. | No | Live transport failure/long-running concurrency soak. |
| A1-020 | CLOSED | History merge preserves newer same-session live points; fits keyed to explicit session/range; frontend tests and range controls passed. | No | Longer real session range acceptance. |
| A1-021 | CLOSED | Ladder/envelope identity joined explicitly in chart/table lineage; backend tests and inspected UI preserve envelope truth. | No | Signed execution lineage acceptance. |
| A1-022 | CLOSED | Current-source age suppresses stale values separately from last decisions; frontend freshness tests passed. | No scoped regression | External freshness acceptance; envelope-age gap A2-004 is distinct. |
| A1-023 | CLOSED | Structured diagnostics sanitize outward copies, complete credential-token redaction tests passed; no artifact paths/raw model bytes exposed. | No | Continued allowlist/redaction review when adding diagnostics. |
| A1-024 | DOCUMENTED / ACKNOWLEDGED | Fixed per-side CLOB budget cancels common virtual-k scaling; code/docs distinguish mathematical reserves from capital. | Not applicable | Preserve wording; do not claim TVL. |
| A1-025 | DOCUMENTED / ACKNOWLEDGED | A concrete optional offline sklearn workflow now exists; runtime still does not depend on sklearn import/training. | Not applicable | Evidence/calibration, not scientific-library expansion. |
| A1-026 | DOCUMENTED / ACKNOWLEDGED | In-memory noncustodial ledger, simulated PAPER economics and partial TESTNET fields preserved; real Redis adds no durability. | Not applicable | Durable journal/recovery and account attribution before operational production. |
| A1-027 | DOCUMENTED / ACKNOWLEDGED | Semantic authority identities remain separate from raw archives; model/dataset/config/window provenance added and inspected. | Not applicable | Immutable empirical evidence archives/trust policy when needed. |

## System Architecture

FastAPI owns one runtime, one local research worker, optional Redis infrastructure/relay, and application lifespan teardown. Market services normalize venue and DEMO evidence. Reference adapters terminate transport payloads and publish typed evidence. Strategy/policies compile and restrict quotes; risk and authorization guard execution. Accounting consumes authoritative execution evidence. Terminal observation copies state and distributes a cached wire snapshot. React consumes observations and explicit local controls.

The simulator constructs separate execution/accounting/history/agent/risk objects and a deterministic clock in the research worker. Research parameters/results do not deploy themselves. Optional Redis stores TTL snapshots, capacity leases and heartbeat, not trading state.

## Full Pipeline / Authority Model

Current runtime ordering, from `HyperAmmRuntime.refresh_once`, is more specific than the prompt's approximate diagram:

1. Acquire execution lock; read accepted market snapshot/history and calculate valid fair midpoint. In TESTNET, reconcile venue state and account/position evidence; PAPER inventory comes from the shared accounting authority.
2. Read source-timestamped perpetual context; synchronize accounting marks/funding/consistency.
3. Apply **PerpContextPolicy before AMM compilation**: bounded mark/oracle/funding-derived strategy reference; external consensus is risk evidence, not a replacement fair-value center.
4. Initialize/recenter virtual pool, sample reserve movements and compile the neutral ladder.
5. Inventory policy shifts reservation center, scales variable size and suppresses inventory-increasing side at hard limits.
6. Market adaptation applies volatility/book policy around inventory reservation; retains market fair, perp reference and inventory lineage.
7. Capture coherent references/agent evidence; telemetry observes recorded orders/fills/reconciliation. Five material agents compose MAX spread, MIN per-side size and MIN level cap. SHADOW is excluded.
8. Calculate candidate capital reservation/exposure; RiskFirewall decides and transforms. A later stage cannot restore an absent upstream side/level. Multipliers across strategy, agents and risk are deliberately sequential, not five-agent multiplication.
9. In TESTNET, normalize to conservative venue economics, then rerun final structural/distance/exposure/capital checks. PAPER uses structural validation directly (A2-001).
10. Reserve accepted capital, bind FinalQuoteAuthorization to ladder economics and domain versions/fingerprints; reconcile slots. Immediately before CREATE/REPLACE transmission, check running/kill/freshness/identity again. TESTNET adapter also checks concrete request membership and exact SDK wire round trip.

Authorization binds market, inventory, perp, reference, material agent, risk and accounting identities, and the quote fingerprint. Display timestamps and SHADOW prediction/model identity do not independently acquire material authority. Config transitions use a lifecycle lock and captured transport ownership; transport start/stop runs outside the execution lock while transitions are serialized and stale callbacks gated. Failed staging is restart-required, not an optimistic recovery.

Current tests verify stale authorization, changed evidence/version, wire changes, accounting mismatch, kill and unknown venue state fail closed. The new neutral metadata gap is not an observed signed transmission escape.

## AMM Mathematics & CLOB Compiler

`constant_product.py` correctly uses `k=x*y`, `p=y/x`, and fee-free swaps `y'=k/(x+Δx)` or `x'=k/(y+Δy)`. Recentering computes square roots for the target marginal price and carries the original k. Arithmetic equality involving square roots is subject to Decimal rounding; this is numerical approximation, not exact arbitrary-precision symbolic algebra.

Sampling uses `d_i=D(i+1)/N`, target `f(1±d_i/10000)`, target base `sqrt(k/p_i)` and successive absolute reserve movement. Per-side cumulative movement increases outward. Incremental movement is positive but does **not** have to increase on both sides: equally spaced ASK increments decrease naturally. Weights normalize successive deltas independently per side.

CONCENTRATED multiplies the natural deltas by distance concentration factors, then renormalizes. It does not replace the AMM profile with a generic geometric ladder. Factor zero reproduces the neutral distribution within Decimal tolerance; concentration bounds affect allocation, not guaranteed execution or hard price bands. Distances below the lower bound can receive equal factors, intentionally leaving the natural profile. Two modes are enough for the MVP; additional AMM models have no demonstrated need.

`total_liquidity` is **per-side base quantity**. The compiler rounds the baseline up to executable size precision, reserves N floors, allocates the remainder using weights and rounds final sizes down. Default and precision tests establish positive floors and no neutral budget excess. Rounding leaves dust. Virtual reserves/k are neither TVL nor wallet/margin balances. Common scaling of reserve deltas cancels under normalization to the explicit budget.

Direct adversarial matrix: 120 accepted model configurations covering reserves `1e-50`, `1e-12`, `100`, `1e50`, `1e100`; fair `1e-12`, `.01`, `3000`, `1e12`; 1/50 levels; distances `.001`, `2500`, `1e-26`. Decimal precision was 28. **80 compiled; 40 with distance `1e-26` failed closed** because successive movement rounded to zero. Swap invariant probes passed in representable cases. This supports ordinary-domain mathematics, but **not** every positive unbounded configuration allowed by StrategyConfig. Precision feasibility is A2-002.

Other accepted configurations fail only at compilation: floor `.10001`, precision 2, four levels and budget `.40004` requires a rounded floor budget `.44`; extremely large size `1e30` encounters Decimal quantize InvalidOperation. These were also saved through the live PUT endpoint with HTTP 200. Their invalid economics were not turned into excess/zero-sized orders. Early feasibility validation should give a clear 422.

Conservative tick rounding is BID down/ASK up; representable positive ladders stay strictly separated around fair. With fair 3000, tick 4000 produced BID zero and QuoteLevel validation rejected it. Same-side collapse does not produce a locked market; rounding distance can exceed raw bounds, however (A2-001).

**AMM conclusion:** coherent MVP math, **A- engineering**; compiler **B** due to discovered hardening gaps. Freeze new AMM features. A small later hardening PR should fix final-distance truth and accepted-config feasibility before choosing a collapsed-slot policy.

## AMM Tick-Normalization / Level-Collapse Investigation

Reproduction: initialize `(100,300000)`, fair `3000`, CONSTANT_PRODUCT, 50 levels per side, `max_distance_bps=.2`, `total_liquidity=5`, tick `.1`, precision 4, baseline `.05`.

| Measurement | Observed |
|---|---|
| Mathematical / emitted levels | 50 BID + 50 ASK = 100 |
| Unique `(side, price)` | 2: BID 2999.9, ASK 3000.1 |
| Logical identities | 100 unique `(side, level_index)`; 100 distinct client IDs |
| Raw BID range | First distance .004 bps / 2999.9988; outer .2 bps / 2999.94 |
| Emitted per-side size | 4.9975, dust .0025 per side |
| First reconcile | 100 CREATE; 100 resting PAPER orders |
| Identical second reconcile | 100 KEEP |
| Exposure | BID 4.9975, ASK 4.9975, gross quote notional 29985; projected position ±4.9975 from flat |

Follow-through:

| Stage | Effect |
|---|---|
| QuoteLevel | Retains distinct side/index despite equal price; raw distance is retained initially. |
| Inventory | Preserves identities; center/size policy can keep collapse or move several together; hard-side suppression persists. |
| Market adaptation | Preserves side/index; no merge; conservative transforms may keep/cause equal ticks. |
| AgentSupervisor | MAX/MIN recommendations; transform widens/reduces/trims by index, does not add missing slots or coalesce. |
| RiskFirewall | Exposure sums distinct slots; duplicate resting orders **within one slot** are separately summed. NORMAL preserves economics/metadata; restrictive transforms recompute distance. |
| Reconciler / OrderManager | Matches slot, not price. Same-price slots are separate intended orders, distinct from A1-006 surplus orders for the same slot. |
| PAPER | Creates all slots; limit-crossing matching can fill a cohort. No queue priority/venue-depth realism. |
| Distribution UI | Each slot is a bar at its price; equal-price bars overlap rather than aggregate size at that tick. |

The direct QuoteEngine → neutral inventory/adaptation → disabled-agent transform → structural validation → PAPER reconciliation probe reproduced the same collapse. A one-tick `.1` price movement at 3000 stayed KEEP because it was within the configured `.5` bps replacement tolerance; there is no collapse-induced automatic churn. The coarse `2000`-tick probe exceeded tolerance and replaced all 100 slots together. Operational venue request cost for these cohorts remains unaccepted because no signed orders were sent.

**Classification:** stable logical identities and correct summed exposure; avoidable slot/order cost and misleading overlapping size visualization. No evidence that collapse alone doubles an existing budget, undercounts exposure, crosses BID/ASK or breaks slot reconciliation. Remediation options are reject/limit effective levels, coalesce with explicit lineage/identity semantics, or intentionally preserve slots with unique-tick counts and aggregated display. Automatic coalescing changes reconciliation identity and should be separately reviewed. A2-003 records this policy gap without implementing it.

## Inventory & Market Adaptation

Inventory ratio is signed deviation divided by soft limit and clamped for normal skew. Long inventory lowers reservation price, reduces BID variable size and increases ASK variable size; short mirrors it. Hard limits suppress the increasing side. Stale/nonfinite inventory fails safely. The policy retains market fair separately from reservation price and uses side/index lineage.

The neutral compiler's per-side budget is not a promise that every later inventory-reducing side has the same size budget: configured skew can increase its variable component. Downstream exposure/capital limits govern that deliberate behavior. It should not be described as an undisclosed AMM capital increase. Floors are precision-sensitive and can interact with later reductions; early rounded feasibility is preferable to relying on compilation failure.

Phase 6 uses trailing accepted observations, RMS log return per observation (not annualized/time-resampled), base-unit top-N depth and signed book imbalance. Numerical guards protect ratios/log/finite conversions. Policy spreads cannot tighten quotes and size effects are bounded. Independent Phase 6 and agent caution can stack across stages. Empirical cadence/threshold calibration remains A1-016; a deterministic bounded score is not evidence of venue-optimized behavior.

## Hyperliquid / Perpetual Context

L2 BBO gives fair midpoint; mark, native oracle, funding and source-timestamped OI are separate evidence. Mid, mark and oracle are not interchangeable. PerpContextPolicy makes a bounded pre-AMM reference shift using explicit weights/funding adjustment. Runtime/UI retain fair/reference/reservation distinctions. Missing/stale perp evidence is explicitly degraded rather than fabricated fresh zero data.

Perp telemetry requires distinct source observations and an adequate time span for OI change. Re-reading the same context does not manufacture OI growth. Public context normalization is implemented and fixture tested; successful current public endpoint schema/freshness was blocked in this environment.

## Live Market Data & Provider Acceptance

Market service validates finite positive normalized books, correct market, uncrossed nonempty sides, source timestamps and material identity. SDK adapter owns retry/resubscribe/teardown rather than assuming SDK 0.24 reconnects itself. Fresh exchange-time acceptance precedes healthy recovery. HTTP providers bound requests/retries and normalize errors; fallback remains provenance-visible. Actual exchange rate-limit behavior could not be observed through the denied proxy.

| Provider / transport | Attempt | Connection outcome | Schema / freshness observed | Reconnect | Acceptance |
|---|---|---|---|---|---|
| Hyperliquid public L2 HTTP | Safe public info request and production adapter | ProxyError / CONNECT HTTP 403 | No provider schema or accepted fresh book | Adapter retried three denied initializations | **ENVIRONMENT BLOCKED** |
| Hyperliquid mark/oracle/perp HTTP + SDK context stream | Safe info and adapter subscription path | CONNECT denied | No current native context schema/freshness | Same denied adapter retry loop; start/stop completed | **ENVIRONMENT BLOCKED** |
| RedStone public HTTP fallback | Production `poll_once` | ProxyError; normalized DEGRADED | Price/source timestamp null; PUBLIC_HTTP/FALLBACK visible | No successful transport to reconnect | **ENVIRONMENT BLOCKED** |
| RedStone Live | Legitimate configuration availability checked | Key/WS configuration unavailable | None | Not attempted without credentials | **CREDENTIALS UNAVAILABLE** |
| Kraken WebSocket | Production provider start/stop | `proxy rejected connection: HTTP 403`; DEGRADED | No ticker frame or freshness | Retry attempted; evidence version advanced on health/provenance | **ENVIRONMENT BLOCKED** |
| CoinGecko simple-price HTTP | Production `poll_once` + safe endpoint | ProxyError | No accepted response/schema/freshness | No live recovery demonstrated | **ENVIRONMENT BLOCKED** |

The cloud network policy file omitted these provider destinations; the runtime policy status was unknown, but actual proxy rejection was unambiguous. These are environmental results, not implementation failures. No public, authenticated or signed provider was accepted. Deterministic adapters/reference tests establish protocol handling against fixtures only. Blocked retry/teardown proves some local failure handling, not resubscription after a successful live connection.

## Reference Integrity

Provider hierarchy is coherent: RedStone one primary oracle identity across Live/HTTP transports; native Hyperliquid oracle/mark/mid are venue-related roles; Kraken independent exchange reference; CoinGecko tertiary aggregator. Transport changes are part of provenance, not another independent vote for RedStone. Confidence reflects availability, agreement, freshness and transport quality; fixture disagreement/outlier/disappearance/recovery paths passed in the full suite.

The reference service exposes latest source-price timestamp while independently stabilizing semantic changes. Same price with changed provenance updates appropriate identity; receiving an unchanged/retained price does not invent a fresh source observation. Source ages are recomputed at terminal emission. External consensus gates risk, not an unbounded quote center. Empirical independence and actual source uptime remain acceptance/calibration questions, especially venue-related correlated evidence.

## Risk & FinalQuoteAuthorization

Risk states NORMAL/WIDEN/REDUCE/HALT use reference confidence/deviation, inventory/projected exposure, liquidation availability, uncertainty, PnL drawdown and accounting/capital consistency. Restrictions suppress sides/levels without restoring upstream liquidity. Hysteresis/recovery confirmations reduce immediate oscillation. Kill remains separate and reachable during research/Redis failure.

Exposure groups desired by side/index and rejects duplicate desired slots. Resting OPEN/PARTIALLY_FILLED/UNKNOWN quantities for a slot are summed; independent conservative maxima combine current/resting and desired quantity/notional. Cancel-before-create and uncertain cancellation guards support that interpretation. Same-price different slots count separately, as the direct collapse probe confirmed.

Final authorization is rechecked at pre-transmission, including expiry/evidence versions and accounting identity. TESTNET final venue normalization recomputes actual distance and rejects crossed ladders. The neutral PAPER validator trusts stored `distance_bps`, so compiler raw-distance retention can bypass its intended distance limit for an extreme valid tick (A2-001). This merits hardening despite final price/size/notional and TESTNET protections.

## Execution / Reconciliation

PAPER CREATE/KEEP/REPLACE/CANCEL were exercised through domain reconciliation and runtime lifecycle. PAPER matches deterministic crossing at limit price, without queue priority, hidden liquidity, latency model or partial depth. Its quality metrics are simulated economics, not exchange performance.

Guarded TESTNET requires explicit enable, key and exact TESTNET trading endpoint; MAINNET enum is rejected. Adapter normalization uses conservative price/size rules, requires exact authorized quote membership and round-trip SDK wire equality. UNKNOWN resting state/cancel uncertainty blocks new exposure. Retained active/pending evidence is pinned rather than silently discarded to meet a display cap. Venue reconcile/reconnect tests passed with fixtures; no signed venue acceptance occurred.

SDK teardown owns websocket/ping threads and drains cancellation-sensitive initialization. Application config teardown is serialized and restart-gated after failure. Denied provider starts stopped successfully, but successful socket/thread churn and signed cancel confirmation remain gates A1-003/004/006.

## Agent Expansion

Source, APIs, simulator and UI confirm **Regime v2, Toxic Flow v2, Execution Quality v2, Liquidity Quality, Perp Crowding**, plus nonmaterial **Predictive Adverse Selection**. Recommendations/evidence are finite bounded typed outputs with versions/fingerprints and explicit confidence/health. `/agents` returns a coherent copied AgentSystemSnapshot. GET observation does not evaluate agents or change execution.

| Agent | Current semantics / independent checks | Remaining limitation |
|---|---|---|
| Regime v2 | Uses momentum/volatility, book imbalance, funding/basis and inventory context. Quiet/normal/trend/volatile/reference/funding stress cases and nondirectional conservative behavior are covered by passing Phase 9/expansion cases. | State labels are heuristic, thresholds/cadence uncalibrated. Direction describes evidence, not BUY/SELL orders. |
| Toxic Flow v2 | 1/5/15s first eligible maturity frozen; pending/unavailable/matured distinct; eviction never rebinds; exact-horizon and irregular observations tested. One fill aggregates available horizons before fill weighting. Decimal quantiles, recency and authoritative fill-notional weighting tested. | Rational recency decay `H/(H+age)`, not exponential. Sparse side confidence/support is explicit; simulated fill bias remains. |
| Execution Quality v2 | Recorded PAPER lifecycle measures first/full fill, lifetime, action-changing cancel/replace/fill ratios, side and level summaries. KEEP does not dilute churn; first-fill time is retained. Unsupported TESTNET timing/partial metrics remain null/unavailable. | Retained-order-window survivor/length bias; not a calibrated venue fill probability. Optimistic PAPER model. |
| Liquidity Quality | Uses actual venue top-N depth in **base units**, spread, imbalance/concentration/instability and reference dislocation; thin/sparse/one-sided cases and cap no greater than available upstream levels tested. | AMM collapsed slots do not directly inflate venue depth; operational order cost is indirect. Fixed market-unit thresholds need calibration. |
| Perp Crowding | Funding alone does not establish LONG/SHORT_CROWDED. Requires aligned funding/basis/momentum with meaningful OI expansion. Basis stress may independently warrant caution. Distinct timestamp/span, single observation, stale/missing trend and unwind cases tested. | Retained OI trend is a bounded heuristic, not account-level positioning proof. |

Signal overlap was inspected explicitly. Regime/Liquidity/Crowding reuse related imbalance, basis, volatility and funding evidence. Supervisor takes MAX spread, MIN BID/ASK sizes and MIN level caps rather than multiplying five recommendations, then clamps global bounds. Existing overlap/agent-failure/upstream restriction tests passed. The running browser observed supervisor 1.15× spread / 0.89× per-side size in a DEMO trend, with other healthy agents neutral. This is conservative composition, not observed runaway amplification. Sequential Phase 6 + agent + risk effects can still reduce quote utility, and thresholds/state transitions can oscillate when inputs hover near boundaries. There is no venue evidence establishing economic benefit or optimal caution; calibrate joint policy, including coverage/churn and state dwell time.

Agent exceptions intentionally replace advice with neutral ERROR outputs. This may relax prior caution across cycles (A1-013 acknowledged design); it is not fail-closed optional supervision. Risk/authorization still govern. No agent submit/cancel endpoint or independent execution authority exists.

## Predictive ML SHADOW

Supported modes are **DISABLED and SHADOW**. ACTIVE/ADVISORY are not accepted runtime modes. Output enforces `affects_quotes=false`; spread/BID/ASK multipliers stay neutral and SHADOW is absent from the supervisor material signature. Changing prediction/provenance cannot invalidate authorization or mutate position, accounting, risk or kill state.

Passing expansion tests explicitly compare changed SHADOW predictions/model identity against material fingerprints/versions/quote transforms, and compare runtime authorization/accounting/kill state. A separate scratch simulation compared the trained artifact with no artifact: orders, fills, metrics and accounting fingerprint were equal; research run fingerprint appropriately changed to record the observation experiment. Promoting model identity/output to quote authority would require a separate reviewed authority change.

No shipped model is fabricated. Missing/invalid artifact or insufficient features visibly produces unavailable/error SHADOW output rather than silently reusing a prior prediction. Public model metadata excludes private filesystem path and raw coefficients/file bytes.

## ML Dataset / Training / Provenance

Canonical `passive-adverse-v1` order is volatility score, book imbalance, momentum/100bps, spread/100bps, BID/ASK depth/100base, mark/oracle and mark/mid basis/100bps, funding/.001rate, inventory ratio, reference deviation/100bps, side sign. Required evidence is rejected when absent; values are finite and clipped to [-1,1]; BID sign +1, ASK -1. Market/source timestamp/schema bounds are checked.

Clipping is an intentional robust-normalization design, not a correctness bug. Depth above 100 base and large basis/momentum saturate, potentially hiding magnitude relevant to quality. Recalibrating units or adding features requires a versioned schema and independent holdout evidence. A linear logistic model also lacks side×momentum interactions unless explicitly encoded; a neural network is not justified by this audit.

Dataset construction selects features at or before fill time and the first eligible maturity observation at/after fill+horizon. It enforces **feature time ≤ fill time < label time**, source time not after observation, mature targets and market identity. Dataset windows include label maturity; fingerprints cover normalized evidence/economics. Conflicting duplicate identity/source evidence and overlapping/reused train-validation data fail deterministically; same economics relabeled under changed fill IDs cannot inflate sample support. Consistent out-of-order inputs are canonically sorted; unsorted input alone is not necessarily invalid. Normalized trusted evidence and hashes are not a complete raw-provider authenticity archive.

Optional sklearn is imported only inside offline training. Training uses bounded LogisticRegression `lbfgs`, C default 1 (0<C≤100), random_state 0, max_iter 200 (10–1000), minimum training 20/validation 10 and both training classes. Nonconvergence fails instead of exporting an unchecked fit. Runtime inference uses inert JSON coefficients, not sklearn or pickle/joblib deserialization.

Artifact loading validates canonical feature order, model type, market, finite bounded coefficient/intercept, schema and SHA-256 content hash; file loading is bounded to 64 KiB. Provenance includes model/schema version, training/validation dataset hashes and disjoint windows/counts, training config hash, sklearn version, market, simulated classification and target horizon. **A content hash is integrity, not a publisher signature**: anyone allowed to author a trusted local artifact can recompute a hash. Current local trusted-artifact boundary is acceptable for SHADOW; promotion would need provenance/trust policy beyond a checksum.

Real optional training exercise used generated artificial ETH evidence: 80 training, 40 validation, 40 disjoint holdout samples; five-second labels, both sides/classes, no live/private data. Six tampering attempts—coefficient, intercept, feature order, hash, market, model type—were rejected; same dataset reused for validation was rejected.

| Partition | Samples | Accuracy | Precision | Recall | ROC AUC | Brier | Calibration error |
|---|---:|---:|---:|---:|---:|---:|---:|
| Training | 80 | .5 | .5 | 1 | .5 | .25 | 0 |
| Validation | 40 | .5 | .5 | 1 | .5 | .25 | 0 |
| Generated holdout | 40 | .5 | .5 | 1 | .5 | .25 | 0 |

Validation BID and ASK each had 20 observations and the same metrics. All probabilities were .5; the [.5,.6) bucket had 40 samples, mean probability .5 and observed adverse frequency .5; the other nine buckets were empty/insufficient. Training/holdout had the corresponding 80/40 populated buckets. Zero calibration error for a balanced constant predictor is not predictive skill. This is functional training/evaluation acceptance, not profitability or venue generalization.

The production simulator's actual fill-bound prediction/maturity path is covered by the passing `test_shadow_simulation_reuses_domain_agents_and_binds_frozen_fill_outcomes`; records bind prediction at order creation, fill time and frozen target. A separate quiet/trend scratch experiment had zero predicted fill outcomes and cannot substantiate outcome metrics.

The trained-artifact HIGH_VOLATILITY run (60 frames) produced 59 PREDICTED frames, 152 fill-bound predictions, 143 matured labels and 9 pending. Orders/fills/metrics/accounting fingerprint remained identical to the no-artifact run; research identity changed. Simulation-cohort accuracy/precision were 0.8531468531, recall 1, ROC AUC .5, Brier .25 and calibration error 0.3531468531. This constant-.5 classifier labels everything adverse at the inclusive .5 threshold; high accuracy reflects the adverse-heavy simulated cohort, not discrimination. Prediction time ≤ fill time and frozen maturity remain explicit. BID simulation metrics: accuracy=0.9714285714285714285714285714, precision=0.9714285714285714285714285714, recall=1, roc_auc=0.5, brier_score=0.25, calibration_error=0.4714285714285714285714285714. ASK simulation metrics: accuracy=0.7397260273972602739726027397, precision=0.7397260273972602739726027397, recall=1, roc_auc=0.5, brier_score=0.25, calibration_error=0.2397260273972602739726027397.

**ML is structurally sound as MVP SHADOW research. There is no evidence to promote beyond SHADOW.** Current metrics, clipping/interaction choices, simulated matching and absent live cohorts all argue for empirical work, not more model architecture.

NumPy remains core-declared (`>=2.1,<3`) even though app runtime has no direct NumPy import. sklearn's NumPy/SciPy dependencies are offline. Retention was an explicit A1-017 compatibility decision; a separate cleanup could move direct NumPy out if compatibility is proven, but this audit does not reopen an acknowledged dependency choice as a new defect. Normal-extra operation before sklearn installation and the skipped offline-training case directly confirm optional training.

## Accounting

One shared `accounting/pnl.py` average-cost authority handles same-direction weighted entry, opposite-side realization, flips and mark-to-market. PAPER runtime/simulator instantiate the same AccountingService; legacy gross-PnL helper delegates rather than duplicating live formulas. Fees/funding are explicit optional research assumptions, with intervals/IDs preventing repeat consumption. Equity, peak equity/drawdown and conservative capital reservation are bound into risk/authorization.

Ledger entries are append-only and fingerprinted/idempotent. Ledger capacity HALT_WHEN_FULL protects consumed economic receipts instead of evicting correctness history. Active/pending evidence is pinned; this trades bounded operational admission for integrity. Consistency state reports mismatch and blocks unsafe authorization. ML/agents only observe it.

The vault remains in-memory, noncustodial, current-session research accounting. TESTNET account/position evidence is partial; unsupported realized fees/funding/cash is null/unavailable rather than made up. No deposit/withdrawal/transfer/share/custody operations exist. Redis does not change this boundary. Durable cross-restart recovery is required for future production scope, not a prerequisite to claim a local research MVP.

## Simulation & Optimization

Simulation reuses QuoteEngine, policies, expanded agents, RiskFirewall, authorization, OrderManager, PAPER and shared accounting under a deterministic clock. Scenario/frame identities, engine version, config/dataset/run fingerprints support reproducibility. Service forcibly converts detached research strategies to DEMO/PAPER; it does not borrow live execution/accounting state.

Run bounds: 2–5000 frames, plus simulation max_frames. Optimize bounds: 2–1000 frames, hard candidate cap, bounded top-N and at most eight training/validation scenarios. Grid candidate schemas/allowed parameters and holdout relationships are validated before work. Optimizer results are proposals; no deploy/promote hook exists. Reusing a validation scenario is explicitly qualified rather than called independent out of sample.

One lifespan-owned ThreadPoolExecutor worker has no unbounded job queue: concurrent admission rejects busy work. Request cancellation shields the bounded worker, retains busy ownership until actual completion and retrieves detached errors; shutdown drains it without blocking the event loop directly. This is bounded completion, not interruptible process isolation. Real Redis coordinates optional research admission only. Local run/optimization HTTP and browser buttons both returned 200; synthetic browser 503 displayed an error without deploying anything.

## Redis Infrastructure

**FAKEREDIS ACCEPTED with a teardown reliability caveat; REAL REDIS ACCEPTED for the exercised local scope.** No installed redis-server/redis-cli was available. Existing usable Docker was used next, as requested; no system packages or repository Docker files were added. Ephemeral loopback container Redis **7.4.11**, image `redis:7-alpine`, digest `sha256:858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499`, persistence disabled, port 6381.

Infrastructure uses bounded async operations/connections, sanitized diagnostic URL/credential handling, namespace keys, TTL cache, server-time leases and renewal that cannot resurrect expired ownership. Relay validates current process/session identity, freshness and sequence; local one-slot queues limit fanout backlog. Heartbeat/health are observations, not authorization.

Direct real-server results: ping/server INFO, research first admission accepted/second denied, release/reacquire, Pub/Sub exact payload/sequence identity, latest-cache TTL **10s**, clean client unsubscribe and worker heartbeat all passed. Real application results:

| State | Health Redis | Simulation | Kill | Terminal |
|---|---|---:|---:|---|
| Healthy | CONNECTED | 200 | 200 | Sequences 363/364/365, same process/session |
| Container paused | DEGRADED | 503 | 200 | Research fails closed; trading authority independent |
| Unpaused/recovered | CONNECTED | 200 | 200 | New connection sequence 371, same process/session |

An outage timeout diagnostic was an empty error string; health still accurately showed DEGRADED. Better timeout naming is minor observability housekeeping, not authority loss. A1-009 local/single-worker guards remain enforced; Redis is not a multi-worker trading architecture, durable ledger or restart recovery. The failed TestClient teardown is detailed as A2-005 rather than hidden by later successes.

## API Surface

Discovered from current routers and the running `/openapi.json`, not guessed. All HTTP rows below share the **loopback peer + loopback Host + local/absent Origin boundary; no operator login/RBAC**. Schema-valid mutation is authorization within a single local operator trust model, not remote security. WebSocket applies the same middleware boundary and resource admission.

Initial API probe made **65 requests: 39×200, 4×403, 2×404, 20×422; no 500**. Every safe OpenAPI GET was exercised, with ETH substituted for market. Additional config/adversarial probes are reported separately so counts are not conflated.

| Method | Path | Purpose / read or mutation | Authority impact | Validation / boundary | Local result |
|---|---|---|---|---|---|
| GET | `/api/v1/health` | Runtime/provider/Redis health; read-only | None; observation | No query inputs; local boundary | 200/403 |
| GET | `/api/v1/markets/{market}` | Normalized market; read-only | None; observation | known market; ETH accepted; local boundary | 200 |
| GET | `/api/v1/markets/{market}/book` | Normalized L2 book; read-only | None; observation | known market; ETH accepted; local boundary | 200 |
| GET | `/api/v1/strategy` | Current config/run state; read-only | None; observation | No query inputs; local boundary | 200 |
| PUT | `/api/v1/strategy` | Save/transition configuration; mutation | Config/lifecycle mutation; A2-002 | StrategyConfig bounds; finite Decimal/enum; local boundary | 200/422 |
| POST | `/api/v1/strategy/start` | Start local strategy; mutation | Running permission, kill-gated | No request body; local boundary | 200; 403 while killed |
| POST | `/api/v1/strategy/stop` | Stop/cancel local strategy; mutation | Remove quoting permission/cancel | No request body; local boundary | 200 |
| GET | `/api/v1/amm/state` | Pool/fair/inventory state; read-only | None; observation | No query inputs; local boundary | 200 |
| GET | `/api/v1/amm/curve` | Current curve/lineage; read-only | None; observation | No query inputs; local boundary | 200 |
| GET | `/api/v1/amm/quotes` | Current quote levels; read-only | None; observation | No query inputs; local boundary | 200 |
| GET | `/api/v1/market-adaptation` | Current adaptation observation; read-only | None; observation | No query inputs; local boundary | 200 |
| GET | `/api/v1/perp-context` | Current perp/reference observation; read-only | None; observation | No query inputs; local boundary | 200 |
| GET | `/api/v1/orders` | Retained orders; read-only | None; observation | limit 1–1000; local boundary | 200 |
| GET | `/api/v1/fills` | Retained PAPER fill evidence; read-only | None; observation | limit 1–1000; local boundary | 200 |
| GET | `/api/v1/risk` | Risk/kill state; read-only | None; observation | No query inputs; local boundary | 200 |
| GET | `/api/v1/references` | Current provider/consensus evidence; read-only | None; observation | No query inputs; local boundary | 200 |
| GET | `/api/v1/risk/evidence` | Risk evidence snapshot; read-only | None; observation | No query inputs; local boundary | 200 |
| GET | `/api/v1/risk/events` | Risk transitions; read-only | None; observation | No query inputs; local boundary | 200 |
| GET | `/api/v1/risk/authorization` | Final authorization observation; read-only | None; observation | No query inputs; local boundary | 200 |
| POST | `/api/v1/risk/kill` | Latch kill/cancel; mutation | Block execution/cancel | No request body; local boundary | 200 |
| POST | `/api/v1/risk/resume` | Clear manual kill; mutation | Clear manual latch; other gates remain | No request body; local boundary | 200 |
| GET | `/api/v1/positions` | Current position evidence; read-only | None; observation | No query inputs; local boundary | 200 |
| GET | `/api/v1/agents` | Coherent six-agent snapshot; read-only | None; observation | No query inputs; local boundary | 200 |
| GET | `/api/v1/agents/events` | Bounded filtered events; read-only | None; observation | limit 1–250; agent validated enum/null; local boundary | 200 |
| GET | `/api/v1/agents/evidence` | Normalized evidence metadata; read-only | None; observation | No query inputs; local boundary | 200 |
| GET | `/api/v1/agents/models` | Sanitized model provenance; read-only | None; observation | No query inputs; local boundary | 200 |
| GET | `/api/v1/simulation/scenarios` | Research scenario catalog; read-only | None; observation | No query inputs; local boundary | 200 |
| POST | `/api/v1/simulation/run` | Run isolated PAPER research; mutation | Detached research only | Run schema; extra forbidden; frames/max_frames; local boundary | 200/422 |
| POST | `/api/v1/simulation/optimize` | Bounded proposal-only optimization; mutation | Detached research only | Grid/scenario/candidate/frame schemas; local boundary | 200 |
| GET | `/api/v1/vault` | Current research vault; read-only | None; observation | No query inputs; local boundary | 200 |
| GET | `/api/v1/accounting/pnl` | Shared PnL breakdown; read-only | None; observation | No query inputs; local boundary | 200 |
| GET | `/api/v1/accounting/position` | Accounting position; read-only | None; observation | No query inputs; local boundary | 200 |
| GET | `/api/v1/accounting/ledger` | Read-only ledger entries; read-only | None; observation | limit 1–500; local boundary | 200 |
| GET | `/api/v1/accounting/events` | Accounting events; read-only | None; observation | limit 1–500; local boundary | 200 |
| GET | `/api/v1/terminal/history` | Bounded current-session observations; read-only | None; observation | limit 1–1000; range enum; local boundary | 200 |
| GET | `/api/v1/terminal/events` | Bounded structured events; read-only | None; observation | limit 1–500; category validated enum/null; local boundary | 200 |
| GET | `/` | Root; read-only | None; observation | No query inputs; local boundary | 200 |
| WS | `/ws/terminal` | Cached terminal stream; read-only | None; observation/admission | Identity/schema/fanout/lease; local boundary | Real frames and reconnect; caveat A2-004/005 |

Negative tests: agent event limits 0/251/noninteger and unknown agent; negative order limit, excessive fill/ledger limit, invalid history range; unknown market and route; malformed JSON, plain-text body, negative/excess levels, MAINNET, NaN, Infinity and invalid Decimal all returned appropriate 422/404/403 without application stack traces. `{}` strategy PUT intentionally loads schema defaults and returned 200; this is not a missing-required-field failure. Extra simulation fields are forbidden. A 64 KiB unexpected string field returned 422 with a 65,652-byte validation response: schema rejection exists, but a hard request/response byte budget does not. Current local trust boundary remains essential; remote scope needs body/rate/time limits.

Three economically infeasible but schema-valid strategy configs returned 200 (A2-002). PUT is schema validation/config transition, not proof that a ladder can compile at the current venue. Safe start/stop/kill/resume passed; starting while killed returned 403. All probes restored original DEMO/PAPER configuration and stopped strategy. No order-submission API was discovered.

Agent endpoints remained read-only and coherent, with 1–250 validated event limits/name filter and sanitized copied snapshots. Evidence/model routes publish metadata rather than private artifact paths/raw bytes. Invalid enums/nonfinite nested values are rejected by output/client contracts as covered by tests and browser module probes.

## Terminal / WebSocket Contracts

Current wire contract is **phase12-v1** (field `contract_version`, not `schema_version`). Process/session UUID, positive sequence and aware emission timestamp scope observations separately from domain authority. Two real non-Redis WS connections received advancing 73/74/75 and 75/76/77 sequences with matching session; real Redis identity/recovery also passed. Shared publication cadence is about one second; readers do not cause repeated assembly or independent sequence churn.

Nested frontend validator rejects malformed displayed financial/agent fields, NaN/Infinity and unsupported ML authority mode. Same-identity duplicate/regressive sequence yields visible error. In an actual browser, the socket utility with a synthetic malformed open socket/controlled clock entered ERROR, watchdog closed it after last-valid timeout, and reconnect created a new socket. Previous-socket callbacks are ownership guarded. This is controlled socket acceptance, not a provider network-failure soak.

**Additional gap A2-004:** actual Vite-loaded validator/store accepted advancing frames emitted in 2001 and 2099 as connected, and accepted a replay from the original session after a new session. Validation checks parseable timestamp and sequence only for matching identity. Arrival time refreshes last-valid freshness. The normal trusted publisher and Redis current-identity/five-second freshness checks mitigate this; it is an observation hardening finding, not execution-authority compromise.

History/events are bounded current-session observations; missing source evidence creates null/gaps, not zeros. Current source freshness is distinct from last decision/transport freshness. Chart merge preserves newer live points and fits on session/range rather than every poll. History GET bounds and event categories are validated.

## Frontend / UX / Responsive Acceptance

Actual Vite React frontend connected to DEMO/PAPER backend. All twelve pages rendered: Dashboard, Markets, Strategy, AMM Settings, Execution, Risk, Supervisory Agents, Vault, Analytics, Simulation & Optimization, Logs, Settings. No fatal page errors, perpetual loading or document horizontal overflow were observed.

Design matches the requested structure: navy/near-black terminal, left navigation, perp header with price/mark/oracle/funding/OI, connection/mode/execution/run/risk truth badges and immediate KILL SWITCH. Dashboard prioritizes price/authorized liquidity, L2 and controls, then KPIs, distribution/transformation/inventory, agents/execution/health. No external mockup was supplied, so acceptance is against actual source and documented structure.

Actual controls: start/stop, immediate kill and confirmed resume passed. A dirty max-distance edit survived WebSocket updates for 1.2s; Reset restored it. Simulation and bounded grid search returned 200 from real buttons; an intercepted synthetic 503 was visibly reported. History 1m/5m/Session switching passed; 15m/1h were correctly disabled because the session was too short. Settings preference controls and logs/category schemas were inspected; no claim that every persisted preference was exhaustively browser-tested.

Five Dashboard widths **1600, 1200, 900, 600, 390** had scrollWidth equal viewport width; KILL remained visible and navigation had all 12 accessible labels. All twelve pages were additionally checked at 900/390 with no horizontal document overflow. Tables have internal horizontal scrolling and may extend inside clipped wrappers; this is expected, not document overflow. At 390px navigation collapses to icons, header wraps and panels stack. Mobile is dense and vertically long; small muted labels could benefit from usability/contrast review. No formal WCAG/axe certification is claimed.

Keyboard Tab produced focus on a kill control; CSS focus-visible styles and aria labels are present. Disabled states prevent unavailable research/history/lifecycle actions. DEMO MARKET DATA / SIMULATED / PAPER labels were visible, and six-agent view clearly showed ML SHADOW **NO QUOTE AUTHORITY**. Guarded TESTNET/LIVE/stale/unavailable semantics were source/fixture checked; no actual signed TESTNET/browser LIVE acceptance occurred. Current-source UI suppresses stale source prices separately from retained decisions.

## Screenshot Acceptance

**SCREENSHOT ACCEPTANCE: PASS — actual rendered Chromium.** First practical browser mechanism (installed Python Playwright with installed `/usr/bin/chromium`) succeeded. No need to exhaust three mechanisms after success. An initial artifact-directory write failed because the requested output filesystem was read-only, then scratch output worked; this was an artifact-path issue, not rendering failure.

| Screenshot | Viewport / state | Checks |
|---|---|---|
| Dashboard desktop | 1600×1000 viewport, stopped and running captures | Loaded chart/book/panels, truth labels/navigation/kill, no document overflow |
| Supervisory Agents desktop | 1600×1000, stopped/running | All six cards, no-quote-authority label, insufficient-data truth, no fatal error |
| Risk | 1600×1000 | Risk/evidence/authorization display loaded |
| AMM Settings | 1600×1000 | Real editable config form loaded |
| Dashboard tablet | 900×1000 | Wrapped/stacked layout, visible kill/nav, no document overflow |
| Dashboard mobile | 390×1000 | Icon rail, wrapped header, stacked panels, internally scrollable tables |
| Simulation & Optimization | 1600×1000 | Research-only controls and empty-result state loaded |
| Vault | 1600×1000 | Simulated noncustodial accounting/ledger display loaded |

Ten full-page PNGs were generated outside the repository; desktop and mobile/agent renders were visually inspected. Full-page dimensions exceed viewport height by design. Screenshot checks share zero fatal page errors and actual rendered data. Initial console contained a nonfatal React StrictMode/WebSocket early-close message and a resource 404 whose specific request was not identified; later monitored page acceptance had no unexpected failed HTTP response. The synthetic research-error response is intentionally 503.

The task-output directory was not writable in the managed execution environment and no artifact upload tool was available. Screenshots were therefore generated/inspected in scratch, **not attached or committed**. Do not interpret the absence of committed images as blocked screenshot rendering, or treat scratch files as durable PR attachments.

## Security & Deployment Boundary

Loopback peer, Host and local/absent Origin are checked for HTTP/WS. Common CLI/environment worker/host launch settings reject remote and multi-worker use. X-Forwarded-For does not bypass these checks. CORS is not authentication. A loopback proxy/tunnel can change the trust model and is unsupported; arbitrary programmatic deployments are not a sandbox against a local operator.

No credentials were exposed, printed or used to trade. Diagnostics sanitize outward payloads; artifact loading uses a private trusted local path with inert bounded JSON, and APIs disclose sanitized provenance only. No pickle/joblib execution path was found. Optional Redis URL/password handling is sanitized. New routes did not weaken A1-009.

No operator authentication/roles, TLS/public deployment design or remote rate/body/time policy is implemented. This is a documented local research boundary, not a claim of secure internet exposure. Public mainnet market data would not authorize mainnet execution; signing is TESTNET-only opt-in, and was disabled in all runtime probes.

## Performance / Resource Bounds

This was not an HFT benchmark. Measured non-Redis wire examples ranged from about **24–25 KiB stopped** to **132,272 bytes** with retained orders/quotes in the initial acceptance frame. Expanded agent/lineage/order data can materially enlarge observations; there is no proof these are maximum byte sizes. UI/terminal responses exclude the full ledger/history; execution views indicate truncation.

Publisher serializes once per cadence and uses one-slot latest-only fanout queues plus a 32-client local cap; optional relay adds lease admission/TTL. Frontend rerenders on accepted frames, bounds chart points and polls history/events independently. Retained events: supervisor 250, terminal 500; agent telemetry fills/orders/reconcile 1000; perp observations 120. Markout horizons are bounded, histories use binary search, and runtime ML inference is twelve-coefficient arithmetic plus bounded sigmoid, not training.

Multi-horizon markout evaluation repeatedly builds/searches retained observations; execution-quality level metrics scan bounded retained records. This is bounded but not constant-time, and should be profiled at worst-case retention/cadence. Classification AUC avoids an unnecessary quadratic pair comparison. Research has one actual worker and candidate/frame bounds, but cancellation does not interrupt CPU computation; maximum-size requests can monopolize the admitted worker until completion.

Authoritative active/uncertain orders and unconsumed fills are intentionally pinned and may exceed presentation caps; admission/ledger-full halts protect economics. SDK callback ingress uses an asyncio queue without an explicit capacity, so feed bursts remain a profiling/hardening item. No sustained load or memory-leak claim is supported by this short audit. Tick-collapsed slots increase request/serialization work without adding price diversity.

## Documentation Accuracy

README/Summary/roadmap reflect the twelve-page integrated system, existing authority protections, research limitations and deferred operational infrastructure. Agent expansion addenda accurately describe five material agents, nonmaterial SHADOW, optional logistic research and added evidence/model APIs. Historical counts/payload sizes are milestone records, not current test totals/bounds.

A remaining older sentence at the start of `docs/ACCOUNTING.md` says Phase 12 remains planned despite the implemented terminal. Its accounting/custody boundary remains correct. Some long-form historical sections describe original three-agent interfaces before later expansion addenda. Small housekeeping is warranted, but no regression of A1-018's listed repaired summary files was established. This report supplies current evidence without modifying historical documentation or declaring calibration/live gates closed.

## Test Results & Warnings

| Directly executed check | Result |
|---|---|
| Normal `.[test]` complete backend | **990 passed, 1 failed, 1 skipped, 1 warning, 29.42s** |
| Initial isolated Redis lifespan suite | **4 passed, 1 failed, 1 warning, 1.09s**; same failing teardown |
| After optional `.[test,ml,redis]` complete backend | **992 passed, 0 failed, 0 skipped, 1 warning, 27.94s** |
| Focused AMM/Agent Expansion/execution/integration/authorization/Redis/WS suite | **270 passed, 1 warning, 13.53s** |
| Later Redis lifespan repeat, Redis client 6.4.0 | **5 passed, 1 warning, .97s** |
| Diagnostic repeat, Redis client 8.1.0 | **5 passed, 1 warning, .72s** |
| Backend compileall | Passed |
| pip check after declared extra install | No broken requirements |
| Frontend tests | **75 passed, 0 failed, 0 skipped**, four files, **14326.774093ms** |
| Frontend typecheck | Exit 0 |
| Frontend production build | Exit 0, **144 modules, 4.03s**; main 417.94KB / gzip 107.33KB |

The initial failure is `tests/test_redis_lifespan.py::test_redis_websocket_relay_and_research_keep_existing_contracts`: nested TestClient WS teardown raises `concurrent.futures.CancelledError` through Starlette TestClient. One offline-training case initially skipped because sklearn was absent. With optional ML it ran. Installing Redis extra also moved the transitive Redis client from 8.1.0 to 6.4.0, but later 8.1.0 repeat passed: **dependency root causality is not established**. This is not an all-green normal-extra acceptance record (A2-005).

| Warning / diagnostic | Owner / classification | Assessment |
|---|---|---|
| `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead` | Dependency-owned deprecation / future compatibility | FastAPI TestClient imports trigger it. Not a trading runtime warning; investigate compatibility deliberately, do not silently add undeclared httpx2. |
| TanStack Query module-level `use client` directives ignored during Vite bundling | Dependency-owned build notice | Build succeeds; ordinary library packaging directive, no observed application failure. |
| Initial npm/pip cache permission messages | Environmental | Redirected cache to scratch; installation then succeeded, no manifest changes. |
| Provider ProxyError / CONNECT 403 | Environmental outbound restriction | Correctly degraded/unavailable; not successful live acceptance. |
| Redis timeout while container deliberately paused | Expected injected failure / application diagnostic | DEGRADED + research 503, kill works; timeout text could be clearer. |
| Browser initial early WebSocket close | Development React StrictMode / transport diagnostic | Nonfatal, subsequent stream/UI accepted; no page error. |
| Initial unidentified resource 404 | Browser resource diagnostic | Not diagnosed as application defect; later page monitoring found no unexpected failed API call. |

## Verified Strengths

1. Conservative deterministic authority binds economics and independently rechecks them before transmission; SHADOW stays outside it.
2. Natural reserve-delta AMM profile survives concentration and downstream lineage rather than being replaced by a generic ladder.
3. Same-price slots and duplicate same-slot orders are distinguished; conservative exposure/cancel handling prevents A1-006 undercount behavior.
4. First eligible markouts freeze across horizons/eviction; source/economic identities prevent easy cohort inflation.
5. One accounting formula and fail-closed retention protect economics instead of evicting correctness history.
6. Research execution is detached, bounded and proposal-only; real offline training exports inert validated JSON.
7. Local deployment and optional Redis boundaries remain explicit; real Redis outage did not disable kill.
8. All twelve actual terminal pages are responsive and display simulated/unavailable/SHADOW truth states.

## Findings A2-001–A2-005

### A2-001 — Raw distance metadata can bypass the neutral PAPER distance limit after tick rounding

- **Severity / subsystem:** 🟡 MEDIUM / HARDENING; AMM compiler, structural risk validation and observation.
- **Summary:** `compile_quotes` stores raw curve `distance_bps` rather than distance of normalized price. Neutral inventory/adaptation/agent/risk paths preserve it; PAPER `validate_quotes` trusts it.
- **Evidence:** `backend/app/amm/discretizer.py`, `strategy/{inventory,market_adaptation}.py`, `agents/supervisor.py`, `risk/{firewall,limits}.py`. Direct pipeline probe accepted prices 2000/4000 around fair 3000, reported distance .2 bps, actual distance 3333.333… bps above RiskStatus 2500.
- **Reproduction:** StrategyConfig 50 levels, `.2` bps, tick `2000`, budget 5, floor `.05`, precision 4; market book 2999/3001; flat PAPER inventory; disable optional inventory/adaptation/perp/agent effects or use neutral branches. QuoteEngine → neutral transformations → `validate_quotes(..., RiskStatus())` succeeds. NORMAL risk transform also preserves that field. No signed venue order was sent.
- **Why it matters:** Price-distance truth and configured PAPER risk band can disagree. Tests of the stored metadata alone miss it; simulation can exercise the same neutral path.
- **Current protection:** Positive prices/sizes/notional/exposure/capital gates; zero-price coarse ticks rejected; **TESTNET normalization recomputes final distance before validation/authorization**. Restrictive transforms generally recompute it too.
- **Missing protection:** Universal final-price-derived distance validation independent of intermediate metadata, with a clearly defined fair/reference center.
- **Recommended remediation:** Compute normalized distance at compilation and independently derive/check actual final distance at the common final validation boundary; retain raw mathematical distance in a separate lineage field if useful. Add a coarse-tick neutral-path counterexample.
- **Authority semantics change?:** Tightens validation against the already intended price-distance limit; no new authority actor, but previously accepted PAPER ladders may now be rejected.
- **Priority:** P1 hardening, before policy selection for collapse. **Blocks MVP:** no, qualified ordinary-config research scope. **Blocks TESTNET:** not the currently protected final-normalized path; require regression coverage before stronger claims. **Blocks future production:** yes, resolve final economic validation/observation consistency.
- **Related prior finding:** A1-001 (final wire protection remains), A1-024 (budget semantics); not an established regression of their scoped fixes.

### A2-002 — Strategy schema accepts economically/numerically uncompileable configurations

- **Severity / subsystem:** 🟡 MEDIUM / HARDENING; strategy configuration / Decimal AMM compiler.
- **Summary:** Positive finite and raw floor-budget validation does not guarantee precision-feasible reserve movement, normalized floor budget or executable size.
- **Evidence:** Direct 120-case matrix failed all 40 `1e-26` distance cases; accepted `.10001` floor ×4 with `.40004` budget/precision2 fails rounded `.44` requirement; `1e30` size fails quantize. Actual PUT requests for all three returned 200.
- **Reproduction:** Construct or PUT those fields over otherwise default StrategyConfig, then compile quotes at fair3000; observe ValueError/InvalidOperation instead of a usable ladder. Transition GET while stopped reports no quotes; HTTP acceptance alone is not compilation acceptance.
- **Why it matters:** Operators can save a schema-valid strategy that cannot quote; Decimal precision 28 cannot distinguish arbitrarily tiny successive movements. Default tests do not close this domain.
- **Current protection:** Compiler checks finite monotonic positive movement, rounded floor budget and positive QuoteLevel sizes; runtime catches invalid quote work/fails closed rather than inventing liquidity or emitting zero orders.
- **Missing protection:** Early rounded-budget feasibility and sensible precision/magnitude/representability limits or explicit compilation preflight for accepted venue/config pairs.
- **Recommended remediation:** Validate rounded floor ×levels against budget at config boundary; bound or explicitly reject unrepresentable numeric ranges; surface deterministic 422 with precise reason. Preserve compiler defensive checks. Do not silently inflate the budget.
- **Authority semantics change?:** Narrows accepted config domain/earlier rejection; no additional execution authority.
- **Priority:** P1/P2 alongside A2-001. **Blocks MVP:** no for validated ordinary configurations. **Blocks TESTNET:** acceptance/config robustness gate for arbitrary configuration, not evidence of unsafe signed transmission. **Blocks future production:** yes for operational config guarantees.
- **Related prior finding:** A1-016 is numerical/cadence hardening, still partial for calibration; this is additional strategy feasibility scope.

### A2-003 — Collapsed ticks preserve redundant slots without an explicit effective-price policy

- **Severity / subsystem:** 🟡 MEDIUM / HARDENING; CLOB compiler / reconciliation / liquidity visualization.
- **Summary:** 100 mathematical slots can become two prices; each remains a distinct intended order, and chart bars overlap.
- **Evidence / Reproduction:** Exact fair3000/50 levels/.2bps/.1tick/5budget/.05floor case in the investigation table. 100 CREATE, then 100 KEEP, correct 4.9975 per-side exposure and 100 unique client IDs. Coarse out-of-tolerance movement caused 100 REPLACE; within-tolerance `.1` movement stayed KEEP.
- **Why it matters:** More slots/venue requests/serialization than price diversity implies; overlapping bars understate aggregate same-price depth. Queue/cancel cost is plausible but not signed-venue measured. Collapse alone does not establish perpetual churn or an exposure defect.
- **Current protection:** Stable side/index identities, correct summed exposure/capital, duplicate-same-slot reconciliation, outward rounding and replacement tolerances.
- **Missing protection:** Explicit accepted policy for number of effective prices, aggregate-at-tick display and venue cost limits.
- **Recommended remediation:** First expose unique-tick count and aggregate display. Then choose explicit reject/trim/coalesce/preserve policy based on venue requirements. Coalescing must preserve budget/lineage and define stable reconciliation identity; do not silently merge in this audit.
- **Authority semantics change?:** Observability-only changes need not; reject/trim changes ladder acceptance and coalescing changes slot/authorization economics, requiring separate review.
- **Priority:** P2 after final-distance/config hardening and acceptance reliability. **Blocks MVP:** no. **Blocks TESTNET:** an explicit operational policy/limit is advisable before many-level coarse-tick deployment, not an existing signed safety escape. **Blocks future production:** yes until policy/cost/visual truth are accepted.
- **Related prior finding:** A1-006 is surplus same-slot orders, not these intentional different slots; A1-024 confirms unchanged per-side budget.

### A2-004 — Frontend freshness uses arrival time and accepts timestamp/session replay edge cases

- **Severity / subsystem:** 🟡 MEDIUM / HARDENING; terminal validator/store/socket observation.
- **Summary:** Parseable ancient/future emission times and retired-session frames can be accepted as connected when sequence is admissible for the presented identity.
- **Evidence:** Actual Chromium imports of Vite `validateTerminal` and `useTerminalStore` accepted `emitted_at=2001-01-01` / `2099-01-01` with advancing sequence. New session then original session replay also accepted. Same-identity duplicate/regressive and malformed nested frames were correctly rejected.
- **Reproduction:** Start from an actual current runtime frame, advance sequence and replace only emitted_at; validate/store and inspect wsState/payloadError. For replay, accept a different session frame then the older original identity. No trading state or backend authorization was changed.
- **Why it matters:** A stale/replayed observation could reset terminal last-valid arrival time and make old/future chart data appear connected. Source-age truth helps but does not validate the envelope itself.
- **Current protection:** Trusted local publisher emits current ordered frames; Redis validates current identity/age; old-socket callbacks are ownership guarded; source staleness and last-valid-frame watchdog work. This is not a demonstrated remotely exploitable execution path.
- **Missing protection:** Envelope age/future-skew tolerance and retired-session/process-aware monotonicity policy at client boundary.
- **Recommended remediation:** Reject or visibly stale excessive emitted age/future skew with explicit clock tolerance. Track current process sequence and retired sessions, allowing a deliberate process restart reset without accepting a prior session again. Test reconnect/restart recovery as well as rejection.
- **Authority semantics change?:** No; observational frontend handling only.
- **Priority:** P2. **Blocks MVP:** no under current publisher trust. **Blocks TESTNET:** observation acceptance gap to close before operator reliance, not backend authorization failure. **Blocks future production:** yes for trustworthy terminal freshness.
- **Related prior finding:** A1-012 nested validation/watchdog and A1-022 source freshness remain verified; additional temporal-envelope scope.

### A2-005 — Normal declared test-extra acceptance has an unresolved WebSocket teardown failure

- **Severity / subsystem:** 🟡 MEDIUM / HARDENING; Redis WebSocket lifecycle test / dependency acceptance.
- **Summary:** Complete normal-extra suite and its initial isolated Redis lifespan repeat failed closing nested TestClient sockets; later complete/focused repeats passed.
- **Evidence / Reproduction:** Fresh Python3.12 environment, `pip install -e '.[test]'`, `python -m pytest -q`: 990 pass/1 fail/1 skip; isolated Redis lifespan: 4 pass/1 fail. Stack terminates in Starlette TestClient close with `concurrent.futures.CancelledError`. Optional-extra full run: 992 pass; later Redis6 and Redis8 focused runs both pass.
- **Why it matters:** Cannot claim reproducible normal-install acceptance based on a later optional-extra green run. Cancellation/race behavior needs diagnosis; a passing real server probe does not prove TestClient teardown stability.
- **Current protection:** Application detach-before-await cleanup and lease TTL; successful real Redis shutdown/recovery probes and later fixture runs. No observed economic-state corruption.
- **Missing protection:** Stable supported dependency/test lifecycle acceptance and diagnosed cancellation ownership/root cause.
- **Recommended remediation:** Reproduce repeated nested WS close/cancellation under a fresh normal-extra environment, retain scheduler/versions, inspect handler/TestClient cancellation contract, and fix the responsible lifecycle or explicitly supported dependency constraint with focused acceptance. Do not assume Redis8 is causal: its diagnostic rerun passed. Do not hide the failure by skipping/weakened tests.
- **Authority semantics change?:** Expected no; lifecycle/test/dependency hardening. Any runtime cleanup change needs cancellation/lease regression checks.
- **Priority:** **P1 acceptance reliability, first non-feature work**. **Blocks MVP:** no implementation completeness, but **blocks an unqualified all-green normal-extra acceptance claim**. **Blocks TESTNET:** reliable lifecycle acceptance should precede serious operational reliance. **Blocks future production:** yes until diagnosed.
- **Related prior finding:** A1-003/004 live lifecycle still partial; this is a new test/Redis boundary, not proven regression of those SDK fixes.

## Subsystem Grades

Grades judge engineering within the documented scope; traffic lights judge exercised acceptance. Yellow can accompany strong code with incomplete external proof.

| Area | Engineering grade | Acceptance | Evidence / limitation |
|---|---|---|---|
| AMM mathematics | A- | 🟢 ordinary domain / 🟡 full allowed extremes | Natural deltas/invariant/concentration tested; precision feasibility A2-002. |
| CLOB compiler | B | 🟡 | Correct neutral budgets/identity, A2-001/002/003. |
| Inventory | A- | 🟢 local / 🟡 venue calibration | Hard-side and lineage guards; intentional reducing-side variable growth. |
| Market adaptation | A- | 🟡 | Finite bounded math; cadence/threshold empirical acceptance pending. |
| Perp context | A- | 🟡 | Bounded pre-AMM reference and provenance; public source blocked. |
| Live market data | B+ | 🟡 environment blocked | Owned lifecycle/fixtures; no successful public feed acceptance. |
| Reference integrity | A- | 🟡 | Provider/transport identities and timestamp truth; real providers unaccepted. |
| RiskFirewall | A- | 🟡 | Exposure/hysteresis/accounting gates; neutral structural distance gap. |
| FinalQuoteAuthorization | A | 🟢 fixtures / 🟡 signed | Exact economics/version/wire checks, signed gate untouched. |
| Execution/reconciliation | A- | 🟢 PAPER / 🟡 venue | Correct slots/duplicates; signed cancels/recovery unexercised. |
| Agents | A- | 🟢 deterministic / 🟡 calibration | Expanded bounded conservative advice, soft failure/overlap accepted only structurally. |
| ML research | A- | 🟢 structure / 🟡 model quality | Real optional fit/tamper/leakage tests; chance artificial model, no promotion. |
| Accounting | A- | 🟢 research / 🟡 operations | Shared economics/fail-closed ledger, no durability/custody. |
| Simulation | A- | 🟢 local / 🟡 realism | Shared domains/isolated worker; optimistic PAPER model. |
| Redis infrastructure | B+ | 🟢 real local / 🟡 reliability | Real TTL/admission/recovery passed; A2-005 teardown unresolved. |
| API contracts | B+ | 🟢 local / 🟡 config domain | Every safe GET, mutations/negatives; feasibility/body budgets remain. |
| Terminal backend observation | A- | 🟢 local / 🟡 scale | Cached coherent bounded publication; no load certification. |
| Frontend | B+ | 🟢 browser / 🟡 temporal edge | Twelve responsive pages; A2-004/overlapping bars/mobile density. |
| Testing | B+ | 🟡 | Broad 992/75 successes; initial declared-install teardown failed. |
| Documentation | B+ | 🟡 minor housekeeping | Current addenda accurate; historical/one stale planning sentence. |
| Operational readiness | C+ | 🟡 research / 🔴 production gate | Local tools accepted; public/signed/durable/remote scope incomplete. |

## MVP Readiness

**Already done as an MVP AMM: yes.** Core mathematics and reserve-delta concentration are sufficiently complete, and the full local research/operator implementation is present. More AMM models or agents would not address the observed defects or acceptance gaps. The five material agents are sophisticated enough for this scope; SHADOW infrastructure is sufficient to begin honest research.

**Local runtime acceptance passed; overall acceptance is qualified.** The initial normal-extra test command failed and should remain a visible gate. No claim of complete all-green clean-install acceptance is made. Compiler edge cases and observation gaps warrant small hardening work, not a new feature phase.

## Production / TESTNET Readiness Boundaries

Public provider success/reconnect/teardown acceptance is blocked here. Signed TESTNET is unexercised; current fixtures protect exact requests but do not establish actual venue cancellation, reconciliation, partial fills, latency or thread/failure soak. Separate authorization would be needed for signed acceptance outside this audit.

Production additionally needs durable journals/restart/order/account recovery, operator security/deployment design, resource/load and failure-soak acceptance, empirical policy/ML calibration and venue accounting reconciliation. PostgreSQL could support a later explicitly designed recovery scope, but adding a database now would not automatically solve these contracts. No production-ready HFT, custody, multi-worker trading, institutional certification or profitability claim is made.

## Current Priority Order

1. **C — diagnose/fix A2-005 acceptance reliability first**, with fresh normal-extra repeated WS teardown coverage; retain the original failure record.
2. **B — one bounded AMM Core Hardening PR**, final actual distance + precision/rounded-floor feasibility (A2-001/002). Select an explicit collapse policy/display only after preserving budget/identity semantics (A2-003); it is not an emergency exposure patch.
3. Harden terminal envelope time/session acceptance (A2-004); refresh minor outdated documentation separately.
4. **A — freeze feature work and focus on acceptance/calibration**: reachable public providers, successful reconnect/teardown, joint agent threshold/state/churn evaluation, independent SHADOW cohorts. Then separately authorized signed TESTNET lifecycle acceptance.
5. **D — durable infrastructure only when recovery semantics are explicitly scoped**. Design journal/account reconciliation/restart behavior first; a PostgreSQL phase is not the immediate MVP prerequisite.

## What NOT To Build Yet

Do not add AMM models, more agents, neural networks, autonomous optimizer deployment, ACTIVE/ADVISORY ML, custody/withdrawals, remote multi-worker trading or mainnet execution. Do not mistake Redis or SHA-256 metadata for durable authority/authenticity. Do not call fixture/live-attempt tests provider or signed acceptance. Do not force a tick-coalescing PR without deciding identity and venue-cost policy.

## Validation Summary — Exact Commands & Results

All commands below were executed unless explicitly marked source inspection. Scratch probe code/logs/JSON stayed outside the repository. Paths are reproducibility records, not committed fixtures or durable attachments.

```bash
git ls-remote origin refs/heads/main
git fetch origin main
git switch -c audit/full-system-2-0 FETCH_HEAD
git status --short
python3.12 --version
node --version
npm --version
python3.12 -m venv /workspace/work/audit2/venv
/workspace/work/audit2/venv/bin/python -m pip install -e '/workspace/hyperamm/backend[test]'
```

Main SHA and versions match the baseline table; initial status empty; normal install succeeded. In backend, using that environment:

```bash
python -m pytest -q
python -m pytest tests/test_redis_lifespan.py -q
python -m pip install -e '.[test,ml,redis]'
python -m pytest -q
python -m pytest tests/test_amm.py tests/test_agent_expansion.py tests/test_execution.py tests/test_integration.py tests/test_phase8_authorization.py tests/test_redis_infrastructure.py tests/test_redis_lifespan.py tests/test_phase12_websocket.py -q
python -m compileall -q app
python -m pip check
python -m pytest tests/test_redis_lifespan.py -q
python -m pip install --cache-dir /workspace/work/audit2/pip-cache redis==8.1.0
python -m pytest tests/test_redis_lifespan.py -q
python -m pip install --cache-dir /workspace/work/audit2/pip-cache redis==6.4.0
```

Counts/durations in the test table. The Redis8 diagnostic is explicitly a temporary diagnostic, not the supported declared Redis-extra installation; Redis6.4 was restored. Selected resolved packages: FastAPI0.143.0, Starlette1.7.0, httpx0.28.1, Pydantic2.14.0, pytest8.4.2, pytest-asyncio0.26.0, fakeredis2.39.0, SDK0.24.0, NumPy2.5.3, optional sklearn1.9.1. Initial fakeredis resolved Redis8.1.0 without the Redis extra; declared Redis extra constrains `<7` and selected6.4.0. No manifest/lock change was made.

Frontend:

```bash
npm ci --cache /workspace/work/audit2/npm-cache
npm test
npm run typecheck
npm run build
```

Install succeeded; tests75/0/0, typecheck0, build0 as above. Runtime startup commands (backend directory, environment's python):

```bash
MARKET_DATA_MODE=DEMO EXECUTION_MODE=PAPER ENABLE_HYPERLIQUID_TESTNET_ORDERS=false REDIS_ENABLED=false python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# frontend directory
npm run dev -- --host 127.0.0.1
# second backend, ephemeral optional Redis acceptance
MARKET_DATA_MODE=DEMO EXECUTION_MODE=PAPER ENABLE_HYPERLIQUID_TESTNET_ORDERS=false REDIS_ENABLED=true REDIS_REQUIRED=true REDIS_RESEARCH_ENABLED=true REDIS_URL=redis://127.0.0.1:6381/0 REDIS_NAMESPACE=hyperamm_audit2_app python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Both backends started, health/API/WS served, Vite served the real React terminal. Safe loopback scripts used `trust_env=False`/`proxy=None`; public probes used the configured outbound proxy. Production adapter provider probes were not replaced with successful unrelated network samples.

```bash
PYTHONPATH=/workspace/hyperamm/backend /workspace/work/audit2/venv/bin/python /workspace/work/audit2/api_probe.py
PYTHONPATH=/workspace/hyperamm/backend /workspace/work/audit2/venv/bin/python /workspace/work/audit2/provider_probe.py
PYTHONPATH=/workspace/hyperamm/backend /workspace/work/audit2/venv/bin/python /workspace/work/audit2/domain_probe.py
PYTHONPATH=/workspace/hyperamm/backend /workspace/work/audit2/venv/bin/python /workspace/work/audit2/additional_domain.py
PYTHONPATH=/workspace/hyperamm/backend /workspace/work/audit2/venv/bin/python /workspace/work/audit2/ml_probe.py
python /workspace/work/audit2/browser_probe.py
python /workspace/work/audit2/frontend_contract_probe.py
python /workspace/work/audit2/browser_extra.py
python /workspace/work/audit2/socket_watchdog_probe.py
```

Results: API65/WS two connections as above; providers blocked/credentials absent; AMM120-case matrix and collapse/distance counterexamples; ML80/40/40 and six rejected tampers; screenshots10/all pages; all pages900/390 no overflow; simulation/optimizer buttons200, synthetic503 visible; malformed socket watchdog/reconnect passed. Additional HTTP config/64KiB probes and trained-model simulator comparisons were executed as inline Python; they did not add tracked tests. Static source conclusions are identified in their sections rather than misreported as successful live acceptance.

Real Redis commands used the installed daemon explicitly (proxy Docker environment cleared):

```bash
command -v redis-server
command -v redis-cli
env -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH docker --host=unix:///var/run/docker.sock version
env -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH docker --host=unix:///var/run/docker.sock pull redis:7-alpine
env -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH docker --host=unix:///var/run/docker.sock run -d --rm --name hyperamm-audit2-redis -p 127.0.0.1:6381:6379 redis:7-alpine redis-server --save '' --appendonly no
PYTHONPATH=/workspace/hyperamm/backend /workspace/work/audit2/venv/bin/python /workspace/work/audit2/redis_probe.py
PYTHONPATH=/workspace/hyperamm/backend /workspace/work/audit2/venv/bin/python /workspace/work/audit2/redis_app_probe.py
```

Native Redis executables unavailable; Docker28.4.0 usable. Probe script deliberately paused/unpaused the scratch container, with unpause in finally; results in the Redis table. No Docker implementation was added to the repository. Backend/Vite processes and the scratch container were stopped after acceptance.

Final report-only verification:

```bash
git hash-object AUDIT_REPORT_1.0.md
git add AUDIT_REPORT_2.0.md
git diff --cached --check
git diff --cached --name-only
git diff HEAD --name-only
git diff --check
```

Prior audit blob unchanged; whitespace checks exit0; staged/HEAD diff contains **only `AUDIT_REPORT_2.0.md`**. Before staging a new untracked file, `git diff --name-only` alone does not list it, so staged and HEAD comparisons were also used. No fix, test/dependency/schema/config/roadmap change or screenshot is included.

Audit evidence collection completed on 2026-10-08 (America/Los_Angeles); report publication/commit time is recorded by GitHub.

## Final Verdict

**HyperAMM is done as a local research MVP AMM and integrated MVP implementation.** Its virtual math and concentrated allocation are coherent, agents preserve deterministic authority, SHADOW research is structurally sound, APIs/terminal are usable and real Redis remains non-authoritative. New features are not the next bottleneck.

Next work should diagnose normal-install test reliability, fix final-distance/config feasibility, decide collapsed-slot observability/policy, and obtain external acceptance/calibration. Current evidence does not justify ML promotion, signed TESTNET acceptance, durable/custodial/remote deployment or production readiness. No previously closed A1 defect was proven regressed; partial external/operational gates remain partial.
