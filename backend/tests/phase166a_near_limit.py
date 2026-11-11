"""Reuse the unchanged 16.5D boundary harness, retaining original result IDs.

Select a clean checkout with PYTHONPATH. The tiny in-process observer executes
identically in both revisions; worker timing includes its tuple append/reads.
"""
import argparse
import asyncio
import json
from pathlib import Path
from unittest.mock import patch

from app.simulation.executor import SimulationExecutor
from phase165d_performance import main as boundary_acceptance


async def main(output):
    identities = []
    original = SimulationExecutor.execute
    async def observed(self, operation, **inputs):
        result = await original(self, operation, **inputs)
        identities.append((result.request_fingerprint, result.receipt.receipt_fingerprint,
            result.provenance.dataset_fingerprint, result.receipt.foundation.scenario.run_fingerprint,
            result.receipt.foundation.scenario.simulation_result_fingerprint,
            tuple((s.dataset_fingerprint, s.run_fingerprint, s.simulation_result_fingerprint) for s in result.segments)))
        return result
    with patch.object(SimulationExecutor, 'execute', observed):
        await boundary_acceptance(output)
    path = Path(output)
    report = json.loads(path.read_text())
    report['original_result_identities'] = identities
    report['identity_fields'] = ['request', 'receipt', 'source_dataset', 'scenario_run', 'scenario_result',
        'segments: engine_dataset/run/result']
    report['observer_note'] = 'Same tuple append/field reads in both checkouts, inside reported worker time; no stage timers/cProfile.'
    path.write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    asyncio.run(main(parser.parse_args().output))
