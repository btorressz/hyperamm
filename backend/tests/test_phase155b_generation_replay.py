"""Retirement has no side effects, including diagnostic counters and history."""
import pytest
from phase155b_helpers import prepared
from test_phase151_live_markets import book
from app.market_data.live_stream_models import LiveMarketStreamEnvelope

@pytest.mark.parametrize('generation', [0,2,100])
@pytest.mark.parametrize('kind', ['l2Book','activeAssetCtx'])
async def test_retired_or_unowned_generation_is_inert(generation,kind):
    service,sdk,clock=await prepared()
    try:
        before=service.snapshot('BTC');history=service.history.query('BTC')
        raw=book('BTC') if kind=='l2Book' else sdk.ctx('BTC')
        assert not service.accept('BTC',kind,raw,generation,clock())
        assert service.snapshot('BTC')==before and service.history.query('BTC')==history
    finally:await service.close()

async def test_publication_sequence_does_not_reset_on_generation_rollover():
    service,_,_=await prepared()
    try:
        first=service._envelope('BTC')
        service.states['BTC'].generation+=1
        second=service._envelope('BTC')
        assert second.sequence>first.sequence
        assert second.observer_instance_id==first.observer_instance_id
        other,_,_=await prepared()
        try:assert other.instance_id!=service.instance_id and not other.history.query('ETH').gap_count
        finally:await other.close()
    finally:await service.close()
