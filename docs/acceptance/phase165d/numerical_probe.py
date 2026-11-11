"""Independent checks of existing metric projection, including missing Vaults."""
import json
from pathlib import Path
from app.research_replay.quantitative import METRICS, _observation
from app.simulation.models import SimulationResult

root = Path.cwd()
assert (root/'backend/app').is_dir(), 'Run this probe from the repository root'
# The checked-in immutable native fixture contains actual engine archives.
fixture = json.loads((root/'frontend/tests/fixtures/phase1641-native.json').read_text())
checks=[]
for case in fixture['cases']:
    for segment in case['result']['segments']:
        result = SimulationResult.model_validate_json(segment['simulation_result_json'])
        for name, unit, origin in METRICS:
            observed=_observation(result,name,origin)
            owner=result.metrics if origin=='SIMULATION_METRICS' else result.vault
            assert observed.value==getattr(owner,name,None)
        absent=result.model_copy(update={'vault':None})
        for name, unit, origin in METRICS:
            if origin=='PAPER_VAULT':
                observed=_observation(absent,name,origin)
                assert observed.value is None and observed.availability=='NOT_REPORTED'
        checks.append(dict(market=case['summary']['market'],segment=segment['segment_index'],
            projected_metrics=len(METRICS),missing_vault_fields_remain_unavailable=5,status='PASS'))
print(json.dumps(dict(status='PASS',checks=checks),indent=2))
