"""Run unchanged deterministic fixtures against independent clean Git revisions.

The external driver compares every digest, including exact archive strings.
Never adjusts fingerprints or normalizes financial output for comparison.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import tempfile

from app.research_replay.quantitative import compare_quantitative_paper
from app.research_replay.contracts import HistoricalReplayRequest
from app.research_replay.runner import canonical_json
from app.research_replay.storage import HistoricalStorage
from app.simulation.models import SimulationResult, stable_fingerprint
from app.simulation.executor import SimulationExecutor
from app.risk.firewall import RiskFirewallConfig
from phase1641_fixtures import admit, dataset
from test_phase162_replay import inputs
from test_phase165a2_integration import pair
from phase166a_profile import profile


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


async def main(output):
    cases = []
    with tempfile.TemporaryDirectory(prefix='phase166a-parity-') as temp:
        root = Path(temp)
        for market in ('BTC', 'ETH', 'SOL'):
            for kind, modeled in (('complete', False), ('complete', True), ('gap', False), ('gap', True)):
                case_root = root / f'{market}-{kind}-{modeled}'
                (case_root / 'vault').mkdir(mode=0o700, parents=True)
                vault = HistoricalStorage(case_root / 'vault')
                scenario, historical = await pair(vault, case_root, market, kind=kind, modeled=modeled)
                archive_hashes = []
                for segment in historical.segments:
                    for name in ('simulation_result_json', 'baseline_result_json'):
                        wire = getattr(segment, name)
                        if wire is None:
                            continue
                        parsed = SimulationResult.model_validate_json(wire)
                        assert canonical_json(parsed) == wire
                        assert stable_fingerprint(json.loads(wire)) == getattr(segment,
                            'simulation_result_fingerprint' if name == 'simulation_result_json' else 'baseline_result_fingerprint')
                        archive_hashes.append(sha(wire))
                receipts = [compare_quantitative_paper(scenario=scenario, historical=historical,
                    segment_index=i).model_dump_json() for i in range(len(historical.segments))]
                cases.append(dict(market=market, kind=kind, modeled=modeled,
                    scenario_sha256=sha(scenario.model_dump_json()), replay_sha256=sha(historical.model_dump_json()),
                    replay_fingerprint=historical.result_fingerprint, archive_sha256=archive_hashes,
                    segment_receipt_sha256=[sha(wire) for wire in receipts],
                    dataset_fingerprint=historical.provenance.dataset_fingerprint,
                    scenario_run_fingerprint=scenario.result.run_fingerprint,
                    segment_run_fingerprints=[s.run_fingerprint for s in historical.segments]))
            # Nonzero modeled fills in every market, retaining complete baseline
            # and modeled archives rather than only transport projections.
            case_root = root / f'{market}-crossing'
            (case_root / 'vault').mkdir(mode=0o700, parents=True)
            vault = HistoricalStorage(case_root / 'vault')
            admitted = admit(vault, case_root / 'incoming', dataset('crossing', market))
            arguments = inputs(vault, admitted, max_frames=4, trace_max_points=4)
            raw = arguments['request'].model_dump(mode='json')
            raw['execution']['paper'] = dict(mode='MODELED_CROSSING', order_latency_ms=1,
                cancel_latency_ms=2, slippage_bps='1', depth_sensitive=True,
                participation_rate='0.5', max_fill_fraction='0.5')
            arguments.update(request=HistoricalReplayRequest.model_validate(raw), risk=RiskFirewallConfig(enabled=False))
            worker = SimulationExecutor()
            try:
                replay = await worker.execute('replay_history', **arguments)
                assert not worker._busy and sum(s.fill_count for s in replay.segments) > 0
                cases.append(dict(market=market, kind='crossing-with-fills', modeled=True,
                    replay_sha256=sha(replay.model_dump_json()), replay_fingerprint=replay.result_fingerprint,
                    archive_sha256=[sha(getattr(segment, name)) for segment in replay.segments
                        for name in ('simulation_result_json', 'baseline_result_json')],
                    fills=[s.fill_count for s in replay.segments], worker_released=True))
            finally:
                await worker.shutdown()
        # Actual depth-limited partial fills under explicit research-only risk
        # assumptions, in addition to all-market archive/provenance fixtures.
        crossing = await profile(frames=8, segments=2, modeled=True, instrument=False,
            output=root / 'crossing.json')
        cases.append(dict(case='modeled-partial-fill-worker', evidence=crossing['runs'][0]['evidence']))
    Path(output).write_text(json.dumps(dict(status='PASS', cases=cases, temporary_data_cleaned=not root.exists()), indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    asyncio.run(main(parser.parse_args().output))
