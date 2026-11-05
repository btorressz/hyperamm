"""Worker-side secure reads and adaptation through the existing engine."""
import json

from app.simulation.config import SimulationConfig
from app.simulation.market_profiles import ResearchPerpMarketMetadata, profile
from app.simulation.models import stable_fingerprint
from .adapter import prepare_replay, segment_dataset
from .contracts import HistoricalReplayRequest, HistoricalReplayResult, ReplaySegmentResult
from .provenance import describe_provenance
from .storage import HistoricalStorage


def canonical_json(value):
    # JSON mode retains all existing native result fields and Decimal strings.
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def catalog(storage_root):
    return HistoricalStorage(storage_root).list_ids()


def provenance(storage_root, dataset_id):
    return describe_provenance(HistoricalStorage(storage_root).read(dataset_id))


async def replay(service, *, storage_root, request, strategy, agents, risk):
    # Revalidate even frozen objects: model_copy(update=...) bypasses validation.
    request = HistoricalReplayRequest.model_validate_json(request.model_dump_json())
    dataset = HistoricalStorage(storage_root).read(request.dataset_id)
    plan, issues, examined = prepare_replay(dataset, request)
    execution = request.execution
    selected = profile(ResearchPerpMarketMetadata(market=request.market,
        sz_decimals=execution.size_decimals, listed=None, asset_index=None,
        metadata_status="DEMO_PROFILE", metadata_source=execution.metadata))
    strategy_copy = service.research_strategy(strategy.model_copy(deep=True), selected)
    agents_copy, risk_copy = agents.model_copy(deep=True), risk.model_copy(deep=True)
    simulation = execution.accounting.to_simulation(SimulationConfig(max_frames=request.max_frames,
        record_trace=request.record_trace, trace_max_points=request.trace_max_points))
    captured = dict(strategy=strategy_copy.model_dump(mode="json"),
        agents=agents_copy.model_dump(mode="json"), risk=risk_copy.model_dump(mode="json"),
        simulation=simulation.model_dump(mode="json"), market_profile=selected.model_dump(mode="json"))
    results = []
    for index, segment in enumerate(plan):
        result = await service.engine.run(dataset=segment_dataset(segment, request),
            strategy_config=strategy_copy, agent_config=agents_copy, risk_config=risk_copy,
            simulation_config=simulation, scenario="historical-replay", market_profile=selected)
        archive = canonical_json(result)
        results.append(ReplaySegmentResult(segment_index=index, reset_reason=segment.reset_reason,
            dataset_fingerprint=result.dataset_fingerprint, run_fingerprint=result.run_fingerprint,
            frames=segment.evidence, frame_count=result.metrics.frame_count,
            starting_equity=result.metrics.starting_equity, ending_equity=result.metrics.ending_equity,
            session_pnl=result.metrics.session_pnl, fill_count=result.metrics.fill_count,
            simulation_result_json=archive, simulation_result_fingerprint=stable_fingerprint(json.loads(archive))))
    values = dict(request=request, request_fingerprint=stable_fingerprint(request),
        modeling_fingerprint=stable_fingerprint((request.policy, request.execution)),
        provenance=describe_provenance(dataset), declared_gaps=dataset.gaps,
        examined_observation_count=examined, frame_count=sum(x.frame_count for x in results),
        issues=issues, segments=tuple(results), captured_configuration_json=canonical_json(captured),
        captured_configuration_fingerprint=stable_fingerprint(captured))
    # Include defaults in the receipt identity as well as material output fields.
    defaults = {name: field.default for name, field in HistoricalReplayResult.model_fields.items()
                if not field.is_required()}
    return HistoricalReplayResult(**values, result_fingerprint=stable_fingerprint({**defaults, **values}))
