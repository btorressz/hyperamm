import pytest
from app.market_data.live_history import LiveObservationHistory
from app.market_data.live_stream_models import LiveHistoryPoint
from test_phase151_live_markets import NOW
from datetime import timedelta

def point(generation=1,offset=0,kind='L2',market='BTC'):
    return LiveHistoryPoint(market=market,observer_instance_id='owner',connection_generation=generation,
        kind=kind,source='OFFICIAL_SDK_WEBSOCKET',source_timestamp=NOW+timedelta(seconds=offset) if kind=='L2' else None,
        observed_at=NOW+timedelta(seconds=offset),observation_status='PARTIAL',
        **({'midpoint':'100'} if kind=='L2' else {'mark':'100','oracle':'100','funding':'0','open_interest':'1'}))

@pytest.mark.parametrize('kind',['L2','PERP_CONTEXT'])
def test_old_generation_cannot_append_newer_evidence(kind):
    history=LiveObservationHistory('owner',3)
    assert history.append(point(2,0,kind))
    assert not history.append(point(1,1,kind))
    assert history.query('BTC').retained_point_count==1

def test_context_economics_deduplicated_across_reconnect_with_explicit_gap():
    history=LiveObservationHistory('owner',3)
    assert history.append(point(kind='PERP_CONTEXT'))
    history.gap('BTC')
    assert not history.append(point(2,1,'PERP_CONTEXT'))
    assert history.query('BTC').gap_count==1

def test_evictions_isolation_and_stable_ordering():
    history=LiveObservationHistory('owner',3)
    for i in range(8):assert history.append(point(offset=i))
    assert history.query('BTC').evicted_point_count==5
    assert history.query('ETH').retained_point_count==0
    assert [p.observed_at for p in history.query('BTC').points]==[NOW+timedelta(seconds=i) for i in (5,6,7)]
    assert history.query('BTC',2).points==history.query('BTC').points[-2:]
    assert not history.query('BTC').continuous_history_verified
