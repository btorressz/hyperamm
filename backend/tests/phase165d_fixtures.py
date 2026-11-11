"""Generated boundary fixtures; no genuine exchange observations or licensing."""
from copy import deepcopy
from datetime import timedelta
import json

from app.research_replay.validation import validate_bytes
from test_phase162_replay import capture
from test_phase161a_contracts import T


def bounded_dataset(frames=1000, segments=1, missing=0, crossing=False):
    raw = capture(native=False, times=(0, .001)).model_dump(mode='json')
    templates = {p['kind']: p for p in raw['observations'][:2]}
    raw.update(dataset_id=f'phase165d-{frames}-{segments}-{missing}-{int(crossing)}', dataset_fingerprint=None,
               observations=[], gaps=[])
    raw['source']['source_id'] = 'local-acceptance:' + raw['dataset_id']
    def append(kind, timestamp, partial=False):
        point = deepcopy(templates[kind])
        point.update(sequence=len(raw['observations']) + 1, received_at=timestamp.isoformat(), source_timestamp=None)
        if partial:
            point['perp_context'] = {'mark_price': '60000'}
        elif crossing:
            price = (60000, 62400, 57600, 63000)[len(raw['observations']) // 2 % 4]
            if kind == 'L2':
                point['order_book'] = dict(bids=[dict(price=str(price-1), size='0.0001', order_count=1)],
                    asks=[dict(price=str(price+1), size='0.0001', order_count=1)], truncated=True)
            else:
                point['perp_context'].update(mark_price=str(price), oracle_price=str(price))
        raw['observations'].append(point)
    for i in range(missing):
        append('PERP_CONTEXT', T + timedelta(milliseconds=i), partial=True)
    offset = missing
    per_segment, remainder = divmod(frames, segments)
    for segment in range(segments):
        count = per_segment + (segment < remainder)
        assert count >= 2
        if segment:
            before = raw['observations'][-1]['received_at']
            offset += 2000
            raw['gaps'].append(dict(start_at=before, end_at=(T+timedelta(milliseconds=offset)).isoformat(), reason='DISCONNECT'))
        for i in range(count + 1):
            append('PERP_CONTEXT' if i % 2 == 0 else 'L2', T + timedelta(milliseconds=offset))
            offset += 1
    raw['coverage_start'] = raw['observations'][0]['received_at']
    raw['coverage_end'] = raw['observations'][-1]['received_at']
    return validate_bytes(json.dumps(raw).encode())
