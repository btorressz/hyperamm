# Phase 17.1A — Portfolio Research Contracts & Provenance Foundation

**Status: native 17.1A.5 acceptance; see [acceptance report](PHASE171A_ACCEPTANCE.md) for actual gates and limitations.** Based on merged Phase 16.6D (`d21f66978ea83384e1bc07d3d53bacd355a23a94`) and the user-supplied Phase 16–17 roadmap, pages 10–11. This is a **research-only contract foundation**, not portfolio simulation, synchronized PnL, operational risk enforcement or a new API.

## REUSE

- `app.simulation.market_profiles.ResearchPerpMarketId`, `MARKETS`, validated research market metadata and `research_strategy` to preserve exact BTC/ETH/SOL identities.
- `app.research_replay.comparison.ComparisonConfigSnapshot`: existing canonical detached strategy, agents, risk, simulation/accounting and market-profile capture; revalidated even if constructed via `model_copy(update=...)`.
- `app.simulation.models.stable_fingerprint` for deterministic SHA-256 configuration identity and `app.research_replay.models.Fingerprint` for validated hash shape.
- `app.accounting.config.bounded_exact_decimal`, `app.accounting.models.canonical` and `app.market_data.live_models.Evidence` for finite exact input, numerical identity and frozen/extra-forbid contracts. Portfolio models additionally revalidate nested instances, including copied/constructed models.
- Existing strategy, agent, risk, SimulationConfig and ResearchVault accounting settings without changing their live or operational behavior.

## ADD

`backend/app/portfolio_research/`:

| File | Ownership |
| --- | --- |
| `__init__.py` | Explicit exported portfolio contract API |
| `config.py` | 18-place, finite, bounded, non-float exact Decimal with canonical JSON strings |
| `allocation.py` | Pure allocation reconciliation and duplicate/unsupported market rejection |
| `models.py` | Versioned budget/allocation/scenario/risk/config/evidence placeholder types |
| `provenance.py` | Self-verified configuration fingerprints and source-trust limitations |

Five focused suites plus a reusable local fixture builder:

- `backend/tests/phase171a_fixtures.py`
- `backend/tests/test_phase171a_contracts.py`
- `backend/tests/test_phase171a_allocation.py`
- `backend/tests/test_phase171a_provenance.py`
- `backend/tests/test_phase171a_isolation.py`
- `backend/tests/test_phase171a_hardening.py`

## Contract version and semantics

`phase17-portfolio-research-v1` restricts the universe to BTC, ETH and SOL, one to three unique selected markets, USDC quote denomination, one shared **hypothetical** total capital, explicit per-market amounts and nonnegative unallocated reserve. Input values may be exact JSON decimal strings or integers, never binary floats, NaN, infinity, exponent bombs or excessive precision. Total capital is capped at 1,000,000,000,000 USDC purely as a local research input bound, and portfolio money is limited to 18 fractional places. Decimals are normalized for identity and financial accumulation occurs at high enough precision to preserve small residuals alongside large budgets.

Each per-market scenario carries an existing `ComparisonConfigSnapshot` that separately binds:
- DEMO/PAPER strategy and configured market;
- agents, risk and simulation inputs;
- matching validated market profile and identity;
- requested frame count (2–5,000);
- exact per-market simulation starting equity and accounting starting equity equal to its portfolio allocation;
- per-market accounting utilization not exceeding the portfolio configured ceiling.

`PortfolioRiskLimits` defines *configuration ceilings*, not authorized operational enforcement: gross/net quote exposure, research session loss, drawdown fraction, capital utilization, inventory concentration and modeled leverage. A later phase must compute and enforce meaningful aggregate research risks under a coherent shared-quote/time model.

`PortfolioResearchConfig.canonical_payload()` revalidates the configuration and fixes market ordering using existing `MARKETS`; equivalent orderings and numerically equivalent money give the same fingerprint. Different allocations, budget, scenario identity, captured strategy/agents/risk/accounting/market profile or execution assumptions change configuration identity. Validated captures normalize exact Decimal spellings with the existing accounting canonicalizer and existing domain serializers before rebuilding ComparisonConfigSnapshot. This applies only at the portfolio boundary; existing single-market snapshot algorithms and fingerprints are unchanged. Earlier draft portfolio receipts must be regenerated. The provenance receipt revalidates embedded model instances and self-rechecks configuration, allocations and per-market capture fingerprints, but makes **no claim** of signed engine results, authenticated market sources, source license, synchronized economic windows or executable portfolio orders.

`PortfolioExposureSnapshot` is a single per-market source-identified observation, with `portfolio_aggregate_verified=False` enforced. `PortfolioResearchResult` is a deliberately non-executable placeholder with `status=NOT_EXECUTED` and `aggregate_equity_quote=None` / `aggregate_pnl_quote=None`, until later phases provide coherent orchestration and evidence.

## Scope limits

**Not implemented in 17.1A**:
- Multi-market execution/worker orchestration (17.2).
- Portfolio-wide exposure/economic aggregation and enforcement (17.3).
- Correlated stress analysis (17.4).
- React portfolio terminal (17.5).
- Full end-to-end browser/external acceptance (17.6).
- Backend routes, persistence, background workers, additional databases, exchange ingestion or portfolio trading/signing.

Separate Phase 16.6B lifecycle/recovery remains deferred; this contract does not imply durable jobs or progress telemetry.

## Native integration and acceptance — 17.1A.5

The original four suites passed natively (48 tests) before corrections. The expanded portfolio acceptance suite passes 115 tests, including copied-model bypasses, exact residuals, all market permutations, changed capital/AMM/agent/risk/fee/funding/utilization inputs, forged receipts and operational isolation. The [acceptance report](PHASE171A_ACCEPTANCE.md) records full backend/frontend counts, exact commands, independent main-versus-branch economic parity, existing-module enhancement decisions and deferred gates.

No temporal-window or historical-dataset inputs exist in this version. Phase 17.2 must bind admitted source/dataset identity and establish any claimed window compatibility. This phase supplies no historical synchronization, portfolio performance, aggregate accounting or operational authority. Physical Redis acceptance and Phase 16.6B lifecycle/recovery remain separate gates.
