"""Rejected input cannot replace accepted evidence or masquerade as another channel."""
import copy
from datetime import timedelta
import pytest
from phase155b_helpers import prepared
from test_phase151_live_markets import book

@pytest.mark.parametrize('kind', ['l2Book', 'activeAssetCtx'])
@pytest.mark.parametrize('mutation', ['channel', 'symbol', 'nested', 'nonfinite', 'zero', 'negative', 'extreme', 'array', 'text', 'timestamp'])
async def test_invalid_update_retains_valid_evidence(kind, mutation):
    service, sdk, clock = await prepared()
    try:
        state = service.states['BTC']
        before = (state.book, state.context, service.history.query('BTC').points)
        raw = {'channel': kind, 'data': book('BTC')} if kind == 'l2Book' else sdk.ctx('BTC')
        if mutation == 'channel': raw['channel'] = 'trades'
        elif mutation == 'symbol': raw['data']['coin'] = 'xyz:BTC'
        elif mutation == 'nested': raw['data'] = {'data': raw['data']}
        elif mutation == 'array': raw = []
        elif mutation == 'text': raw = '{broken json'
        elif mutation == 'timestamp':
            if kind == 'l2Book': raw['data']['time'] = 10**100
            else: raw['data']['coin'] = 'ETH'
        else:
            value = {'nonfinite': 'NaN', 'zero': '0', 'negative': '-1', 'extreme': '9'*81}[mutation]
            if kind == 'l2Book': raw['data']['levels'][0][0]['px'] = value
            else: raw['data']['ctx']['markPx'] = value
        assert not service.accept('BTC', kind, raw, 1, clock())
        assert (state.book, state.context, service.history.query('BTC').points) == before
        assert state.rejected == 1 and state.connection == 'DEGRADED'
        assert service.snapshot('BTC').observation_status != 'AVAILABLE'
        assert kind not in state.seen
    finally: await service.close()

@pytest.mark.parametrize('delta', [-11000, -1, 2000])
async def test_stale_replay_and_future_book_do_not_retime(delta):
    service, _, clock = await prepared()
    try:
        before = service.states['BTC'].book
        raw = book('BTC'); raw['time'] += delta
        assert not service.accept('BTC', 'l2Book', raw, 1, clock())
        assert service.states['BTC'].book == before
        clock.advance(12)
        assert service.snapshot('BTC').status.l2_freshness == 'STALE'
    finally: await service.close()

async def test_conflict_requires_new_valid_delivery_proof():
    service, sdk, clock = await prepared()
    try:
        service.accept('BTC','l2Book',book('BTC'),1,clock())
        service.accept('BTC','activeAssetCtx',sdk.ctx('BTC'),1,clock())
        assert service.snapshot('BTC').observation_status == 'AVAILABLE'
        raw=book('BTC'); raw['levels'][0][0]['sz']='2'
        assert not service.accept('BTC','l2Book',raw,1,clock())
        service.accept('BTC','activeAssetCtx',sdk.ctx('BTC'),1,clock())
        assert service.snapshot('BTC').observation_status != 'AVAILABLE'
        assert service.states['BTC'].book.bids[0].size == 1
    finally: await service.close()
