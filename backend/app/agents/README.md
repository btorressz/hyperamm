# Supervisory agents and predictive shadow research

Agents recommend. Phase 8 decides. FinalQuoteAuthorization controls execution.

The governing rule remains: **Agents recommend. Deterministic infrastructure decides and executes.**

```text
Strategy / AMM → deterministic/heuristic agents → AgentSupervisor
→ bounded conservative quote transformation → Phase 8 RiskFirewall
→ structural validation → FinalQuoteAuthorization → execution

Historical/simulated evidence → offline dataset → optional offline training
→ validated JSON logistic artifact → SHADOW inference → observability only
```

No agent or ML model receives execution, signing, risk, kill, accounting, position
or FinalQuoteAuthorization authority. No agent can restore suppressed liquidity.
Training is offline, with no runtime training imports or automatic promotion.

## Implemented agents

| Agent | Type | Evidence and behavior |
|---|---|---|
| Regime v2 | Heuristic | Phase 6 volatility, momentum, book pressure, funding, both mark bases, references and inventory context. Existing states and symmetric bounded caution. |
| Toxic Flow v2 | Deterministic | Immutable first-eligible post-fill observations for configurable 1/5/15 second horizons plus the legacy primary horizon. Side toxicity, quantiles, recency, notional weighting and persistence. |
| Execution Quality v2 | Heuristic | Existing capture/markout/churn plus recorded PAPER first/completed-fill durations, terminal quote lifetime, partial-fill incidence, side and level quality. |
| Liquidity Quality | Heuristic | Actual top-N base depth, BBO spread, depth imbalance/concentration, book span, accepted midpoint instability and dislocation. Healthy/thin/imbalanced/unstable/dislocated states. |
| Perp Crowding | Heuristic | Distinct source-timestamped funding/OI observations; aligned funding, basis, momentum and OI expansion for long/short crowding. Funding alone is insufficient. |
| Predictive Adverse Selection | ML SHADOW | A single configurable-horizon conditional adverse-fill classifier, with BID/ASK probabilities. No expected-markout or PnL claims. |

Regime reuses Phase 6's per-observation RMS volatility rather than recomputing a
volatility estimator. Momentum uses the existing accepted observation window.

## Regime v2 scores

Every score is a finite Decimal in [0,1]. Funding stress is
`clip(abs(funding_rate) / funding_threshold)`. Basis stress is
`clip(max(abs(mark_oracle_basis_bps), abs(mark_mid_basis_bps)) / basis_threshold)`.
Book pressure is `abs(book_imbalance)`; trend strength is
`clip(abs(momentum_bps) / (3 * trend_threshold_bps))`. Inventory stress is
`clip(abs(inventory_ratio))`. Funding and basis combine by their mean. Aligned
book/momentum pressure is book pressure times trend strength. The maximum of
these and the existing regime risk score is multiplied by
`1 + inventory_stress / 5`, then clipped. Combined full basis stress with at
least half funding stress can classify DISLOCATED. QUIET additionally requires
low funding/basis/book stress. This describes conditions, not BUY/SELL advice.

## Multi-horizon toxic flow

The default configured horizons are 1, 5 and 15 seconds; at most three strictly
increasing horizons may be configured. The legacy primary horizon (default 5s)
remains the contract for legacy matured-fill metrics, quantiles and execution
quality. It is included separately if absent from the horizon set (maximum four
agent horizons). Telemetry supports at most eight distinct registered horizons,
including explicitly supplied research model targets.

For a BID fill the sign is +1, for an ASK fill -1:

```text
signed_markout_bps = sign * (future_mid - fill_price) / fill_price * 10000
severity = clip(-signed_markout_bps / adverse_threshold_bps, 0, 1)
horizon_toxicity = (indicator(markout < 0) + severity) / 2
fill_toxicity = mean(available horizon toxicities)
recency_weight = H / (H + max(0, observation_time - fill_time in seconds))
side_toxicity = sum(fill_toxicity * recency_weight) / sum(recency_weight)
overall_toxicity = max(BID toxicity, ASK toxicity)
```

Here H is the configured recency half-life in seconds. Notional toxicity uses
`fill_price * fill_size` from normalized fills and is observational; it is not an
extra multiplier. Weighted severity averages available horizons per fill, then
fills. Side adverse rates count a fill once if any available horizon is adverse.
Persistence is the fraction adverse across **all configured horizons**, among
fills with every horizon mature. Side confidence is clipped unique matured-fill
count / (2 * minimum fills), multiplied by mean available-horizon coverage.
The supervisor never counts one fill as several independent fills. Quantiles
(10th/median/90th) use linear interpolation on sorted Decimal primary markouts.

For each fill/horizon, the **first accepted normalized midpoint at or after
maturity** is selected once. Sequence, source timestamp, target time, price and
markout remain frozen. Later prices cannot rebind it. History eviction/clear
before selection produces terminal UNAVAILABLE. A fill evicted before a
registered horizon resolves increments `evicted_unavailable_markouts` before its
bounded retained state is removed. Pending, unavailable and mature counts remain
distinct. History selection uses binary search without changing these semantics.

## Lifecycle and book evidence

Recorded PAPER order `created_at`, terminal `updated_at`, normalized fill times
and order side/level/filled quantity support lifecycle metrics. First-fill time
is retained separately for a tracked order so later partial fills or fill-window
eviction cannot become its first fill. Level fill rate is the fraction of
retained orders at that side/level with a positive filled quantity; it is not
queue probability. Partial-fill ratio is retained orders with
`0 < filled_size < size` / retained orders. Cancel/replace-to-fill ratios use
retained terminal status counts / orders with any fill. Fill distance is the
absolute distance to the accepted **fill-time consensus**, not an invented mid.

Venue acknowledgment/reconciliation latency remain null. TESTNET fill-based
lifecycle, spread capture and markouts remain unavailable because TESTNET lacks
an authoritative normalized fill ledger. PAPER evidence is explicitly SIMULATED.

The liquidity level cap is bounded by the available upstream level count when supplied; transformation still only removes existing slots.

Book depth sums the configured top-N levels in base units. Depth concentration
is the largest retained level / total BID+ASK depth; imbalance is
`(bid_depth - ask_depth) / total_depth`. Spread and book span use midpoint bps.
Instability is the largest absolute consecutive midpoint move in the bounded
momentum history, not top-of-book churn. The thin-depth threshold is in market
base units and should be configured for the selected market; it is a heuristic,
not a universal empirical calibration.

Perp telemetry retains at most 120 observations. Duplicate or backward source
timestamps do not produce observations. Market/source changes reset history.
A configured count window (default 30) and age bound (900s) select observations;
a change needs two distinct source timestamps spanning at least 5s. OI change
is `(latest - earliest) / earliest`, unavailable for zero initial OI. Funding
delta is in funding-rate units. Stale perp evidence cannot supply crowding advice.

## Supervisor, failure and identity

The five deterministic/heuristic agents compose with MAX spread, MIN BID size,
MIN ASK size, and minimum non-null level cap. Configuration clamps spread to
[1, maximum] and size to [minimum, 1]. Transformation only visits upstream slots,
rounds conservatively, and rejects tightening, crossing or invalid values.

Individual exceptions publish fresh ERROR/neutral advice while other agents
continue. Stale advice is never reused; neutral failure can relax an earlier
agent recommendation within the upstream ladder. Phase 8 and final authorization
remain authoritative. ML contract/load errors publish ERROR with no prediction
or quote effect. Error diagnostics do not expose local artifact paths.

**SHADOW identity is observational.** Predictions, inference timestamps,
feature schema and model fingerprints are visible in agent output, but excluded
from material supervisor version/fingerprint and final quote authorization.
Changing a shadow model cannot invalidate quote authority. Simulation run
identity includes the observational model hash for research reproducibility.
A future ADVISORY promotion would require separately reviewed independent
validation, sample support, calibration and explicit operator configuration;
ADVISORY/ACTIVE are not implemented and no model can promote itself.

## Feature and artifact contract

`ml_features.py` defines `FeatureSchema` / `FeatureVector` and the canonical
`passive-adverse-v1` order: volatility score, book imbalance, momentum/100 bps,
spread/100 bps, BID and ASK depth/100 base, mark-oracle and mark-mid basis/100 bps,
funding/0.001, inventory ratio, reference deviation/100 bps, and side sign.
Values are clipped to [-1,1]. Required missing features reject inference;
there is no silent reshape, zero imputation or arbitrary dictionary input.
Any ordering/normalization change requires a new schema version.

The model is one transparent logistic classifier. Its bounded JSON artifact
contains exactly twelve finite coefficients (each [-100,100]), a bounded
intercept, feature schema and strict provenance. Maximum local artifact size is
64 KiB. The SHA-256 identifies the canonical full artifact contents **excluding
only its own hash field**, including coefficients, schema and provenance;
formatting whitespace is non-material. Altering parameters or metadata without
resealing fails verification. No pickle/joblib deserialization is used.
Provenance includes train/validation identities, non-overlapping time bounds,
config fingerprint, sample support, library version, validation metrics,
market, target horizon and simulated classification. Public metadata contains
no artifact paths or raw model coefficients/bytes.

Runtime inference has twelve multiplies and one sigmoid per side with a logit
clamp of [-60,60]. It uses standard-library math only and has no extensible model
callback or unbounded inference backend. Float math is confined to observational
probabilities; AMM, accounting, risk, sizing and authorization retain Decimal.

## Offline usage

Normal operation remains `pip install -e '.[test]'` without sklearn. The existing
core NumPy declaration is retained as previously documented; it is not used by
these deterministic agents. Optional research uses:

```sh
pip install -e '.[test,ml]'
python -m app.research.ml.training --training train.json --validation validation.json \
  --artifact shadow-model.json --report validation-report.json
```

`app.research.ml.dataset.build_dataset` accepts typed evidence, normalized
fills and ordered midpoint observations. It selects features at/before the
fill; future observations construct labels only. Duplicate observations/fills
cannot inflate sample counts; conflicting identities are rejected. Dataset
fingerprints cover samples, target, source fingerprints and classification.
Bounds include label maturity, preventing a training label from overlapping the
claimed independent validation window. Training and validation cannot reuse
sample identities or the same dataset fingerprint. The CLI consumes these
serialized `OfflineDataset` contracts, not raw provider dictionaries.

`train_logistic_model` is offline only, lazily imports sklearn, fits a bounded
LogisticRegression, rejects non-convergence, and exports inert coefficients.
NumPy/SciPy use is transitive through optional sklearn here only. Classification
reports distinguish training/validation/holdout/simulation, side results, target
horizon, accuracy/precision/recall/AUC/Brier and calibration error. Ten probability
buckets show counts and flag inadequate support (default fewer than 10 samples).
These metrics establish neither profitability nor empirical venue validity.

To explicitly load a trusted local artifact at runtime startup, set
`PREDICTIVE_MODEL_ARTIFACT_PATH` in server configuration. The setting is excluded
from public snapshots. Loading happens once at setup/reset, never in API GET or
quote evaluation. No model is shipped or silently enabled with fabricated data;
default mode is SHADOW with visible UNAVAILABLE output until an artifact is supplied.

## API and simulation

`AgentSystemSnapshot` deep-copies config, evidence, outputs, decision and bounded
telemetry together when a successful strategy cycle publishes. Read-only GETs
serialize that publication; newer fill telemetry cannot mix with older advice.
The existing `/api/v1/agents` and `/agents/events` shapes remain; new agent fields
are additive. `/agents/evidence` and `/agents/models` expose bounded observations.
Events support a validated agent filter and `1 <= limit <= 250`; all endpoints
retain public diagnostic sanitization and perform no network/model work.

Simulation uses the same production agents/evidence builders. Supply
`SimulationEngine.run(..., predictive_model=validated_artifact)` explicitly for
shadow research. Predictions bind at order creation, then to actual PAPER fills;
labels use the same frozen maturity contract. The report retains at most 1000
fill predictions and 1000 order bindings, exposes eviction counts and names its
bounded cohort. Pending labels remain pending at the end, without invented
future prices. Trace records inference probabilities; side/horizon calibration
reports compare retained predictions with matured signed markouts. Quote,
fill, accounting and risk outcomes are invariant to supplying a shadow artifact.
