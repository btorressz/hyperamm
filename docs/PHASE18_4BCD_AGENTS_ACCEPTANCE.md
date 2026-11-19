# Phase 18.4B–D advisory agents

The implementation starts at merged PR #93 (`f7cc7e783881b6ef538e76103ca84a38fe70a892`). The baseline review followed the first-parent merges for #84–#93 and inspected the Audit 3.0 remediation, canonical market discovery, financial evidence normalization, Generalized PAPER worker, six-agent supervision and final quote authorization in source. Financial compatibility is measured against merged PR #92 (`bb07f717e707ec21b005b9692992b5bd90bdac07`). [PR #93](https://github.com/btorressz/hyperamm/pull/93) · [Audit 3.0](../AUDIT_REPORT_3.0.md) · [Market universe](PHASE18_0_MARKET_UNIVERSE_ARCHITECTURE.md) · [PAPER hardening](PHASE18_2G_FINAL_HARDENING_ACCEPTANCE.md) · [Market risk](PHASE18_3_MARKET_RISK_ARCHITECTURE.md) · [Phase 18.3 acceptance](PHASE18_3_FINAL_ACCEPTANCE.md)

## Architecture and files

| Target | Delivered |
| --- | --- |
| Reuse 45% | Canonical Core/HIP-3 discovery, catalog generation and PAPER assessor, synthetic scenario fingerprints and references, Phase 18.3 risk and asset units, SDK session ownership and response limits, basis math, PAPER fees and funding, and the existing markout implementation. |
| Enhance 35% | Additive source clock, expiry and component reconciliation under the existing immutable `phase184a-v1` contracts, an explicit `phase184bcd-v1` binding and analysis version, and a public transport entry point shared with discovery. |
| Add 20% | Three independently callable agents, a bounded observation adapter, a pure capture and binding helper, and adversarial tests. Percentages are architecture targets. |

| Files | Scope |
| --- | --- |
| `backend/app/agents/advisory_contracts.py`, `advisory_evidence.py` | Optional extension fields, fingerprint binding, snapshot publication expiry, canonical discovery reference and PAPER frame lookup. |
| `backend/app/agents/market_eligibility.py` | Operation-specific eligibility based on discovery and existing PAPER assessment. |
| `backend/app/agents/funding_basis.py` | Separate official and simulated funding and basis modes. |
| `backend/app/agents/quote_economics.py` | Selected PAPER quote cohort, fees, carry, inventory, adverse selection and edge. |
| `backend/app/market_data/market_universe_discovery.py`, `advisory_market_observations.py` | Shared bounded SDK transport and separately owned on-demand public acquisition. |
| `backend/tests/test_phase184b_market_eligibility.py`, `test_phase184c_funding_basis.py`, `test_phase184d_quote_economics.py` | Core, HIP-3 and Testnet fixtures, provider and timing failures, provenance and financial cases, and snapshot and zero-authority assertions. |
| `docs/PHASE18_4BCD_AGENTS_ACCEPTANCE.md`, `docs/PHASE18_4_ADVISORY_ARCHITECTURE.md`, `CHANGELOG.md` | Implementation, validation and handoff. |

The original 18.4A suite passed before implementation. Review identified three gaps for concrete evaluators. Official current context has a receipt clock and no event timestamp. Value-level source evidence must be recomputed from backend captures before it can be consumed. A published snapshot must be revalidated against the current clock as its context or sources expire. The extension covers those cases and preserves the original authority fields. Unset extension fields are omitted from legacy serialization. A comparison of representative v1 context, snapshot and quote fingerprints against the original PR #93 tree matched exactly.

## Market Eligibility

| Operation | Applicable evidence |
| --- | --- |
| `DISCOVERY` | Verified, currently listed metadata, canonical network and DEX, exact market identity and size precision, and a bounded age. |
| `STANDARD_PAPER` | A standard scenario assessed by the existing PAPER preflight, with matching catalog, profile and configuration bindings. |
| `HYPOTHETICAL_RISK` | A PAPER assessment for the hypothetical mode with accepted inputs and a bound Phase 18.3 model. |
| `SOURCE_CONSTRAINED_RISK` | A PAPER assessment with current public collateral and margin observations, supported tiers and policy, and compatible declared valuation and leverage. The existing risk binder checks these conditions. |
| `FUNDING_BASIS` | A complete funding rate and aligned prices from one of the supported evidence modes. Missing supplemental observations can yield conditional suitability. |
| `QUOTE_ECONOMICS` | A complete, reconciled PAPER quote cohort and explicit costs. Suitability is conditional on the modeled cohort and assumptions. |

`PaperEligibilityCapture.from_assessment` calls the existing `assess()` with server-owned metadata, optional catalog deadline, financial observation and expected binding. An eligible result uses confidence 0.85. Discovery uses 1.00. The funding and quote operations retain the relevant evaluator's confidence and source digests. Missing applicable evidence yields `UNKNOWN` with zero confidence. A definite incompatible profile, delisting or unsupported research policy yields `NOT_SUITABLE`. Stale evidence uses `STALE`. A cross-market, cross-network or contradictory binding raises a validation error. The server's existing admission and worker still decide whether PAPER can run.

## Funding and basis

`AdvisoryMarketObservations` uses the official SDK URL for its configured network. The pinned SDK 0.24.0 does not accept a DEX parameter on `meta_and_asset_ctxs()`, so this adapter sends the scoped `metaAndAssetCtxs` payload over the existing bounded SDK `/info` transport. Its `funding_history()` and `l2_snapshot()` methods map the exact canonical coin, including the HIP-3 prefix. Current contexts must match the selected universe row's position, coin, listing and precision. The transport uses an explicit allowlist, skips WebSocket startup and closes the SDK session on success and failure.

Each cache miss makes at most three requests. A collection has a 12-second wait budget and the shared transport uses a per-request timeout of at most five seconds, a 1 MiB response limit, and strict JSON and depth limits. Three market acquisitions can run concurrently. Calls for the same metadata capture share an in-flight task. A cancelled waiter detaches from that task and the owner drains active work on close. There are no retries. An HTTP 429 sets a 30-second adapter backoff. A 64-entry cache holds successful captures for up to ten seconds.

| Observation | Clock and convention |
| --- | --- |
| Current funding, mark, oracle and open interest | One scoped context response. Each field carries the local receipt time and no provider event timestamp. A positive hourly rate means longs pay shorts. Prices use the market's reported quote per base. Open interest is in base units. |
| Midpoint | Arithmetic mean of the two valid top prices from the exact market's `l2Book`. Its provider event must be at most ten seconds old and within ten seconds of the current-context receipt. The adapter excludes `allMids` because it can fall back to the last trade. |
| Realized funding history | Up to 24 hours and 24 distinct hourly records, sorted by millisecond provider time. Identical duplicates collapse. Conflicting observations for an hour invalidate the history. The summary is the arithmetic mean of available historical per-hour rates. |
| Synthetic PAPER | The last frame of the existing scenario generator, with its content verified against the completed run's dataset fingerprint. It uses the configured PAPER interval and a separate scenario clock. A missing schedule cannot supply a carry signal. |

The public rate is per hour. Historical rates describe settled intervals. Current rates can change before settlement. The implementation excludes the first-DEX-only predicted-funding endpoint. It makes no annualization or observed payment projection. PAPER carry is modeled separately under the simulation's mark-notional convention. This preserves the distinction from venue funding, which uses oracle notional under the public product specification. [Perpetuals API](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals) · [Info API](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint) · [Funding](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/funding) · [Rate limits](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits)

Signed basis is `10,000 × (price − reference) / reference` using positive, aligned Decimal inputs. Mark/oracle basis is required. The adapter and agent can omit mid-based basis, history and open interest independently. Results round basis to eight decimal places and history means to 18, nearest with ties to even. The existing crowding basis threshold marks basis stress. Direction remains explicit even when the state is `BASIS_STRESSED`. Complete official and PAPER evidence use confidence 0.90 and 0.60, respectively. These values score evidence completeness. They do not estimate future rates.

### Live provider check

The official Mainnet public API and installed SDK returned the following data on November 18, 2026. The capture and book event columns show Pacific time. Both validated snapshots were READY with `EXCHANGE_OBSERVED` provenance. Each market returned 24 hourly history rows. The most recent provider history timestamp for both was `2026-11-19T06:00:00.026Z`.

| Canonical market | Current receipt | Book event | Hourly rate | Mark / oracle / midpoint | Mark–oracle / mark–mid (bps) | Open interest (base) |
| --- | --- | --- | --- | --- | --- | --- |
| `HYPERLIQUID:MAINNET:CORE_PERP::BTC` | 10:48:24.761919 p.m. | 10:48:25.275 p.m. | 0.0000009591 | 63508.0 / 63538.8 / 63506.5 | −4.84743181 / 0.23619629 | 39085.8632799999 |
| `HYPERLIQUID:MAINNET:HIP3_PERP:xyz:XYZ100` | 10:48:30.236642 p.m. | 10:48:31.157 p.m. | 0.0000227395 | 27572.0 / 27552.0 / 27573.5 | 7.25900116 / −0.54400058 | 10451.8144 |

The SDK fixture tests separately instrument session cleanup, timeouts, rate limits, empty and malformed data, Testnet routing and inactive or mismatched evidence. An instrumented repeat of the live check closed all eight SDK sessions across the two discovery lookups and six advisory requests. It recorded zero operational SDK constructor or key derivation calls. The GitBook documentation host returned HTTP 403 through the workspace proxy. Verification used the pinned SDK source, the repository's source convention documentation and the actual public responses.

## Quote Economics

The caller selects a retained scenario frame of a completed Generalized PAPER run. The cohort consists of the submitted simulated orders created in that frame, and the associated fills reconcile by order ID, side and exact quantity. The gross quote spread uses the best submitted bid and ask against the quote-frame accepted synthetic consensus. It needs a two-sided submitted ladder. One-sided or partial fills on this ladder contribute only their actual simulated quantities. Retained receipts and the existing scenario reference policy supply the accepted reference at each fill. The existing telemetry code supplies a synthetic matured markout for each attributed fill. Missing references, maturities, fills or an explicit funding schedule produce `INDETERMINATE`.

All amounts use the exact network-scoped `HYPOTHETICAL_QUOTE` unit. The following components are normalized to bps on the sum of attributed fill size times fill-time reference. Each side's capture also has a separate side-notional result.

| Component | Calculation |
| --- | --- |
| Quoted spread and notional | `10,000 × (best submitted ask − best submitted bid) / quote-frame consensus`. Submitted notional sums limit price times original size. |
| Attributed capture | For a bid use `size × (reference − fill price)`. Reverse the sign for an ask. Sum using retained fills. |
| Fees | Existing PAPER maker/taker fee function for each fill's execution notional. An explicit maker or taker assumption applies to a modeled close of the net unpaired base. Its assumed adverse slippage adjusts its fee notional. |
| Funding carry | Hold the final attributed fill frame's mark and scenario rate constant for the declared horizon. Apply the existing PAPER funding calculation to the signed residual base at each scheduled boundary in `(start, end]`. Payments are positive costs, and modeled receipts are negative costs. |
| Inventory | Positive expansion in absolute base position attributable to the cohort at the latest fill frame, times that frame's mark, scenario peak inventory utilization and the declared inventory charge in bps. |
| Adverse selection | Use the adverse portion of the move from accepted fill-time reference to the matured synthetic midpoint, times fill size. The fill-to-reference move is already included in attributed capture. |
| Slippage | Explicit assumed residual-close slippage against the last attributed fill's accepted reference. Entry slippage is reflected in the actual simulated fill price. |
| Break-even and edge | Break-even capture is the sum of fees, carry, inventory, adverse selection and slippage. Modeled edge is attributed capture minus break-even. |

Capture rounds down and costs round up to eight places in bps. The displayed components reconcile exactly, including at break-even. Confidence grows from 0.1 per matured attributed fill, capped at 0.75. The model uses the selected Risk Firewall state, retirement indicators and modeled headroom where available. The headroom keeps its original denomination, including when it differs from the PAPER accounting unit. A HALT, retired quote frame or insufficient modeled headroom yields unsupported economics. Positive modeled edge refers to the explicit PAPER cohort and cost model. Fill probabilities, observed venue markouts and exchange fee tiers are outside this implementation.

## Binding, fault isolation and authority

The server creates each source digest over the exact metadata record, evidence value, source ID, clock, unit and provenance. Each evaluator revalidates the context and independently regenerates the source references from its captures. Identity includes the canonical network and case-sensitive DEX. PAPER uses the configuration, run and optional risk fingerprints and verifies reconstructed scenario frames against the dataset digest. The assembler uses the existing `AdvisorySnapshot`, checks which sources actually contribute, and calls `validate_at(as_of=…)` before later publication. Expiry requires a new evaluation.

Expected provider, stale and insufficient-evidence failures produce bounded independent outputs with zero confidence. Binding and validation errors propagate to the caller and identify inconsistent evidence. The back-end coordinator can retain successful unrelated outputs after a bounded provider or evaluator failure. The evaluators have no dependency on the material agent lifecycle. No route or live cycle instantiates them.

Focused tests instrument SDK order submission, cancellation, leverage update, wallet signing and key derivation, and the guarded TESTNET execution adapter. They record zero calls. All three recommendation models enforce `affects_quotes=false`, `can_override_risk=false`, `can_authorize_paper=false`, `execution_eligible=false` and `authority=NONE`. A snapshot round trip rejects forged authority and a recommendation cannot validate as `FinalQuoteAuthorization`. The existing supervisor, predictive SHADOW evaluator, quote ladder, Risk Firewall, authorization and ledger implementation retain their original call sites.

## Compatibility and regression

The native probe compared 39 datasets, three 40-frame BTC/ETH/SOL simulations and the aggregate portfolio against PR #92. It includes risk decisions and references, quote output, fees, funding, fills, inventory, P&L and ledger. It reproduced the historical combined checksum `22eed4a5c0d67fa94b0e8780e9cbfd3af50276cab4e2b5e2a22e581b449a34ad` and portfolio checksum `e51a1579d079429ed6ee123e120a7d46bc38f4ebd73e7c90283ff97ab53c9417`. All 240 direct final-authorization captures, including their supervisor fingerprints, matched the published checksum `ef990233ca2afd8d2662db40bb3e346908f378fddf43d275ece2ccfb344b65a9` after removing the wall-clock creation field. [Native reproduction probe](PHASE18_2G_FINAL_HARDENING_ACCEPTANCE.md#native-btcethsol-compatibility)

All 38 Generalized PAPER results matched PR #92 byte for byte in a fixed-clock comparison. The matrix includes 26 risk-disabled runs across all 13 scenarios for Core `DOGE` and HIP-3 `xyz:GOLD`, plus 12 hypothetical and source-constrained runs across three representative scenarios per market. Each run used 40 frames, 7/13 bps maker/taker assumptions and two-second funding. The comparison covered datasets, configuration, full results, accounting and risk decisions. Its combined digest is `9b82ad883b63a737fc22be0105dd6f7d9e69ea5bcec75776ad46432e2579b219`.

| Check | Result |
| --- | --- |
| Original 18.4A before edits | 38 passed, 0 failed, 0 skipped, 3 existing Pydantic deprecation warnings. |
| Focused 18.4A–D | 88 passed, 0 failed, 0 skipped, 3 existing Pydantic deprecation warnings. |
| Targeted backend | 797 passed, 0 failed, 1 skipped for optional scikit-learn, 4 existing warnings. Covers six agents and supervisor/snapshot, perpetual context, discovery, risk, Generalized PAPER, synthetic references, accounting, Firewall, final quote authorization and guarded TESTNET. |
| Full backend `python -m pytest -q -rs --tb=short` | 3,783 passed, 0 failed, 1 skipped for optional scikit-learn, 5 existing warnings in 625.15 seconds. |
| Optional ML test rerun | 1 passed, 0 failed, 0 skipped, 0 warnings with isolated scikit-learn 1.9.1. This is the test skipped in the standard workspace environment. |
| Frontend locked install, typecheck, tests and build | All four commands passed. 864 tests passed, zero failed, skipped or cancelled. Tests reported two Zustand storage notices. Build reported 15 dependency directive warnings and one chunk-size warning. |

## Phase 18.4E–F handoff

Phase 18.4E owns the adapter for the application's configured network and closes it on shutdown. It resolves one active catalog generation and captures the existing PAPER assessment or completed result only from server-owned storage. Use `capture_context` and each capture's `source_evidence()` with the applicable catalog, risk and PAPER fingerprints. Set the context deadline to the active generation's usable window. Pass the current server time to evaluation and revalidate the active generation and snapshot at publication. Pass one funding mode per recommendation and keep scenario prices synthetic. A stale optional source can be dropped by evaluating again.

Phase 18.4E also owns the bounded read-only API, observational coordinator, TypeScript contract and runtime validation, and three panels in the existing Generalized PAPER workspace. The quote panel needs the retained frame selection and explicit carry horizon, residual liquidity, slippage and inventory assumptions. It should show quoted spread, attributed capture and break-even separately. The funding panel needs separate receipt and provider event times and must label current, realized history and synthetic intervals.

Phase 18.4F retains cross-agent API and browser integration acceptance, full accessibility coverage, expanded provider and concurrency soak, final cross-market end-to-end evidence, and the Phase 18.4 completion report. This milestone supplies the three isolated B–D research evaluators and their backend acceptance evidence.
