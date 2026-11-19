# Phase 18.4 — Advisory Agents Architecture and Handoff

**Phase 18.4B–D status**

The three evaluators are available as independently invoked backend components. The public observation adapter supports selected Core and HIP-3 markets on its configured network. Phase 18.4E owns runtime and API integration. [Phase 18.4B–D implementation and acceptance](PHASE18_4BCD_AGENTS_ACCEPTANCE.md)

**Phase 18.4A status:** isolated, immutable contract foundation; no running new agent,
provider call, API route, React component, quote transformation, trading authorization
or simulator change. Baseline: Phase 18.3 final acceptance, merged PR #92
(`bb07f717e707ec21b005b9692992b5bd90bdac07`).

## Allocation and constraints

**Total Phase 18.4 plan:** 25% ChatGPT architecture/contract/review, 75% Codex
implementation/testing; approximately 85% backend and 15% frontend over all
A–F workstreams; architecture emphasis **REUSE 45% / ENHANCE 35% / ADD 20%**.
These are design targets, not measured code percentages.

### Existing components to REUSE

| Module | Existing source of truth and future role |
| --- | --- |
| `agents/models.py`, `agents/config.py`, `agents/common.py` | Six existing agent health, telemetry, configuration and fingerprint conventions. **Not** the new agents' inherited order authority. |
| `agents/supervisor.py`, `agents/snapshot.py` | Existing material and observational agent evaluation; do not alter the current five material outputs or predictive SHADOW agent signature. Phase 18.4 agent outputs remain separate. |
| `agents/evidence.py`, `agents/perp_crowding.py`, `agents/execution_quality.py` | Existing funding/basis telemetry, fills, markouts, crowding and uncertainty logic; no duplicate unbounded histories. |
| `market_data/market_universe_contracts.py` | Canonical `MarketInstrumentIdentity`, verified discovery metadata, network, DEX, timestamps and fingerprints. |
| `market_data/market_universe_discovery.py`, `market_data/market_risk_metadata.py` | Existing read-only discovery owner, per-generation financial metadata, collateral policy, provenance and single-flight refresh. |
| `risk/market_risk_contracts.py`, `risk/market_risk_engine.py` | Explicit currency/financial unit, hypothetical vs observed constraints, exposure and bounded modeled margin. No inferred real account balances. |
| `market_data/perp_context.py`, `market_data/live_models.py` | Existing native funding, mark/oracle and basis processing. Native BTC/ETH/SOL observations are **not** a generalized Core/HIP-3 live feed. |
| `simulation/models.py`, `simulation/generalized_market_profiles.py` | Stable deterministic fingerprints, synthetic references, hypothetical accounting, PAPER admission, local worker and result binding. |
| `risk/firewall.py`, `risk/authorization.py`, `agents/supervisor.py` | Existing mandatory risk and order authority; **new advisory results cannot enter or override it**. |
| `frontend/src/components/simulation/GeneralizedPaper.tsx`, `GeneralizedPaperRisk.tsx` | Existing research workflow for future 18.4E read-only panels; no UI work in 18.4A. |

### Changes in 18.4A

**ADD:** `backend/app/agents/advisory_contracts.py`, a focused
`backend/tests/test_phase184a_advisory_contracts.py` suite and this document.

**ENHANCE:** architecture documentation and changelog only. Avoid touching the
current `AgentConfig`, `AgentRecommendation`, `AgentSupervisorDecision`,
`AgentSystemSnapshot`, simulation engine, Risk Firewall or portfolio contracts
in 18.4A. Alter operational code only in a later PR with an independently
demonstrated requirement.

## Versioned advisory contract

Source: `backend/app/agents/advisory_contracts.py`.

All advisory contracts inherit the existing frozen, forbid-extra
`Evidence` foundation and add strict validation, recursive revalidation,
and `contract_version="phase184a-v1"`.

### AdvisorySourceEvidence

An observation *claim* bound to the canonical market/network/DEX, category,
provenance, capture clock and optional financial unit/source fingerprint.

Distinct provenance:
- **EXCHANGE_OBSERVED:** binds a provider event timestamp no later than capture
  or explicitly identifies a local-receipt-only field when the provider supplies
  no event time. The official read-only adapter owns acquisition and exact
  market binding. The source fingerprint identifies the captured content.
- **SCENARIO_SYNTHETIC:** requires scenario time and scenario/PAPER source
  namespace, and cannot declare official metadata, collateral or margin.
- **HYPOTHETICAL_ASSUMPTION:** explicit assumption namespace and fingerprint,
  no simulated timestamp or provider observation.
- **UNAVAILABLE:** no observation timestamp, source fingerprint, financial unit
  or invented provider ID.

A fingerprint is evidence identity, not proof of authenticity. All financial
units must match the market network. A mismatch between a real observation
clock and synthetic scenario clock is rejected.

### AdvisoryContext

One captured metadata record and its matching fingerprint, optional catalog
and risk/model/PAPER binding hashes, evaluation time, optional expiry and at
most 16 unique source references. A ready advisory requires a bounded expiry.

The context fingerprint includes metadata, network, DEX namespace, source
provenance, timestamps, units, source fingerprints and captured bindings.
Cross-market references, duplicate source identities and conflicting source
fingerprints are rejected.

### Agent-specific advisory outputs

All inherit `AdvisoryRecommendation`, which is intentionally **not** a subclass
of `agents.models.AgentRecommendation`.

Every output binds:
- Canonical market identity, context fingerprint, evaluation clock.
- `READY`, `INSUFFICIENT_DATA`, `STALE`, `UNSUPPORTED`, or `ERROR`.
- Decimal confidence (0–1) and bounded reasons.
- Explicit source fingerprint list and synthetic/observed/mixed provenance.
- `affects_quotes=false`, `can_override_risk=false`,
  `can_authorize_paper=false`, `execution_eligible=false`,
  `read_only=true`, `authority="NONE"`.

Non-ready outputs have zero confidence. READY requires positive confidence,
nonempty source evidence, and a valid provenance class. Consumers must
validate each output against the **server-owned context**, not trust a
self-reported READY flag.

| Output | Scope | Important boundary |
| --- | --- | --- |
| **MarketEligibilityAdvisory** | DISCOVERY, STANDARD_PAPER, HYPOTHETICAL_RISK, SOURCE_CONSTRAINED_RISK, FUNDING_BASIS, QUOTE_ECONOMICS; suitability and missing evidence. | Suitability is explanatory; PAPER/portfolio admission remains server-side. |
| **FundingBasisAdvisory** | Funding direction and mark/oracle or mark/mid basis, with explicit unknown state. | Positive/negative funding signal needs a funding-specific source; basis requires basis/mark evidence. No assumed current HIP-3 live quotes. |
| **QuoteEconomicsAdvisory** | Modeled spread, fees, funding, inventory, adverse selection and estimated edge. | A positive edge is modeled, never a profit guarantee; complete modeled decisions require hypothetical PAPER accounting units and source-bound assumptions. |

`AdvisorySnapshot` validates market/context/time, the set of source
fingerprints, evidence provenance and agent-specific data binding. It is a
**sidecar evidence envelope**, not a `FinalQuoteAuthorization`, not an
`AgentSupervisorDecision`, and not a risk-readiness override.

No direct public or privileged endpoint consumes these contracts in 18.4A.

## Implemented advisory entry points

Each evaluator accepts a server-created `AdvisoryContext`, its applicable capture and a current `as_of` time. The recommendations retain `phase184a-v1` and identify their additive fields as `phase184bcd-v1`. Existing v1 payloads keep their representation. Later publication uses `AdvisorySnapshot.validate_at(as_of=…)` to revalidate the nested evidence and reject expired READY inputs.

| Entry point | Capture and scope |
| --- | --- |
| `MarketEligibilityAgent.evaluate` | Verified discovery and a `PaperEligibilityCapture` obtained through the existing server assessor, or the applicable funding or quote evidence. |
| `AdvisoryMarketObservations.observe` | On-demand official SDK acquisition for the exact network, DEX and observed market. The later application owner closes the adapter. |
| `FundingBasisAgent.evaluate` | The official adapter capture or a `PaperFundingObservation` from a completed Generalized PAPER run. Only one mode contributes to a recommendation. |
| `QuoteEconomicsAgent.evaluate` | A `QuoteEconomicsObservation` for one retained PAPER quote cohort with specific hold, exit, slippage and inventory assumptions. |

Use `capture_context` to bind the selected metadata, source evidence, evaluation clock and applicable catalog, risk and PAPER fingerprints. Each source digest includes its value and capture envelope. The worker and discovery continue to own the actual evidence. Phase 18.4E must resolve the current generation server-side when publishing any READY recommendation.

## Codex handoff

| Phase | Owner | Implementation |
| --- | --- | --- |
| **18.4B** | Codex | Implement Market Eligibility Agent via existing canonical discovery, precision, PAPER admission and Phase 18.3 risk evidence. Independently evaluate each research operation; e.g. standard PAPER can be suitable even when source-constrained risk is unavailable. An advisory cannot grant backend eligibility. |
| **18.4C** | Codex | Funding/Basis Agent: reuse native funding/perp-context and telemetry patterns, plus a *bounded read-only* observation adapter for market-qualified Core/HIP-3 public data if supported by official SDK/API. Validate provider source, market, time, freshness and funding interval. Never infer mark/oracle/basis from synthetic scenario fields. Keep hypothetical funding evidence distinct. |
| **18.4D** | Codex | Quote Economics Agent: reuse AMM quote candidates, deterministic fees/funding/inventory, existing execution quality and markout provenance. Clearly differentiate projected spread, uncertain fill probability, hypothetical carry/fees and ex-post realized markouts. Decline to claim positive net edge without complete supported assumptions. |
| **18.4E** | ChatGPT + Codex | Keep a separate advisory sidecar, read-only bounded API, TypeScript runtime evidence validation and three compact panels in existing Generalized PAPER. Avoid new live trading controls, new Market Explorer or new agent supervisor. |
| **18.4F** | Codex | Focused adversarial numerical, source, provenance, clock, identity, stale-data, browser and accessibility tests; full backend/frontend regressions; native BTC/ETH/SOL and 18.3 PAPER fingerprint comparisons; zero exchange signing/cancel/leverage operations. |

**Important implementation rule for B–F:** Neutral advice from missing, stale,
error or unsupported sources must not become favorable funding, eligible
market or profitable-quote evidence. Do not modify the existing five
material-agent spread/size aggregation or existing predictive SHADOW output.
The research result may reference a separate versioned advisory fingerprint,
but must not silently change the historical financial result fingerprint for
risk-disabled native or generalized PAPER runs.

## Source, profitability and capability limitations

- Core/HIP-3 discovery metadata and selected public funding and price fields use
  separate observations. Generalized PAPER uses synthetic scenario pricing.
- The existing Phase 18.3 risk evidence supports single-market PAPER and
  selected public collateral/margin policies. It does not verify an account's
  collateral balance, cross-margin, portfolio netting or liquidation.
- Funding payments and fee schedules must be observed or declared as
  assumptions with explicit currency/interval semantics.
- Funding/basis without time-aligned sources is unknown, not zero.
- Quoted spread is not realized spread capture; modeled positive edge is not
  guaranteed profitability or future P&L.
- Advisory authority cannot turn a rejected PAPER proposal into eligible
  research and cannot reduce an existing HALT severity.

## 18.4A validation and acceptance

Focused suite: `backend/tests/test_phase184a_advisory_contracts.py`.

Tests cover canonical Core/HIP-3 and network isolation; strict observed versus
synthetic clocks; unsupported source impersonation; source fingerprint
ambiguities; missing evidence; authority escalation; confidence and status
invariants; market eligibility suitability; funding/basis input binding;
quote-economics modeled-only state; and unchanged existing supervisor models.

The Phase 18.4B–D implementation ran this original foundation suite before
editing and again with the finished evaluators. Reproduce it with:

```bash
cd backend
python -m pytest -q tests/test_phase184a_advisory_contracts.py
python -m pytest -q -rs --tb=short
```

The acceptance report records the focused, backend and frontend compatibility
results. [Phase 18.4B–D acceptance](PHASE18_4BCD_AGENTS_ACCEPTANCE.md#compatibility-and-regression)

**Exit:** Phase 18.4A contracts are independently validated, have no operational
consumers, and provide a safe source-bound foundation for 18.4B–F. Subsequent
milestones may add new source-backed models with explicit versions, not loosen
the locked 18.4A no-authority fields.
