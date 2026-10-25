"""Bounded framing/parsing and strict financial/research request failures."""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api.research_vault import ResearchBodyLimit
from phase154_helpers import request


async def body_check(chunks,headers=(),limit=65536):
    received=[];sent=[];calls=[];iterator=iter(chunks)
    async def receive():return next(iterator)
    async def send(m):sent.append(m)
    async def endpoint(scope,receive,send):
        calls.append(True);received.append(await receive())
    await ResearchBodyLimit(endpoint,max_bytes=limit)({'type':'http','method':'POST','path':'/api/v1/strategy',
        'headers':list(headers)},receive,send)
    return calls,received,sent


@pytest.mark.parametrize('raw',[b'-1',b'+1',b' 1',b'1 ',b'abc',b'1,1',b'9'*21,b''])
async def test_invalid_content_length_rejected_before_reading(raw):
    calls,_,sent=await body_check([],[(b'content-length',raw)])
    assert not calls and sent[0]['status']==400


@pytest.mark.parametrize('headers',[
    [(b'content-length',b'1'),(b'content-length',b'1')],
    [(b'content-length',b'1'),(b'transfer-encoding',b'chunked')],
])
async def test_ambiguous_framing_rejected(headers):
    assert (await body_check([],headers))[2][0]['status']==400


async def test_content_length_fast_limit_mismatch_and_disconnect():
    assert (await body_check([],[(b'content-length',b'65537')]))[2][0]['status']==413
    assert (await body_check([{'type':'http.request','body':b'abc'}],[(b'content-length',b'2')]))[2][0]['status']==400
    assert (await body_check([{'type':'http.disconnect'}]))==( [],[],[] )


async def test_tiny_chunk_memory_is_coalesced_at_exact_limit_and_overflow_is_rejected():
    chunks=[{'type':'http.request','body':b'x','more_body':i<65535} for i in range(65536)]
    calls,received,_=await body_check(chunks)
    assert calls and len(received)==1 and received[0]['body']==b'x'*65536 and not received[0]['more_body']
    chunks=[{'type':'http.request','body':b'x'*40000,'more_body':True},{'type':'http.request','body':b'x'*30000}]
    calls,_,sent=await body_check(chunks,[(b'transfer-encoding',b'chunked')])
    assert not calls and sent[0]['status']==413


@pytest.fixture
def comparison_client():
    with TestClient(app,raise_server_exceptions=False) as c:
        # Lifespan's disabled production service is safe and opens no SDK clients.
        yield c


@pytest.mark.parametrize('value',['NaN','Infinity','-Infinity','1e999','1e-999','1e-61','1e31',True,{},[],1.25])
def test_invalid_financial_values_cannot_reach_comparison(comparison_client,value):
    data=request().model_dump(mode='json');data['research']['performance']['session_pnl']=value
    response=comparison_client.post('/api/v1/research-market-comparison/compare',json=data)
    assert response.status_code==422
    assert response.headers['cache-control']=='no-store'
    assert all(set(e)=={'loc','msg','type'} for e in response.json()['detail'])


@pytest.mark.parametrize('value',['1e30','-1e30','1e-60','0','9007199254740993.123456789'])
def test_valid_decimal_boundaries_preserve_exact_values(comparison_client,value):
    from decimal import Decimal
    data=request().model_dump(mode='json');data['research']['performance']['session_pnl']=value
    r=comparison_client.post('/api/v1/research-market-comparison/compare',json=data)
    assert r.status_code==200,r.text
    assert Decimal(r.json()['research']['performance']['session_pnl'])==Decimal(value)


@pytest.mark.parametrize('timestamp',['2026-02-30T00:00:00Z','2026-01-01T25:00:00Z','2026-01-01T00:00:00','not-a-date',None])
def test_invalid_research_frame_timestamps(comparison_client,timestamp):
    data=request().model_dump(mode='json');data['research']['assumptions']['representative_frame_timestamp']=timestamp
    assert comparison_client.post('/api/v1/research-market-comparison/compare',json=data).status_code==422


@pytest.mark.parametrize('market',['BTC-PERP','btc','ETH/USD','../../../risk/kill',None,{'market':'BTC'}])
def test_invalid_market_identifiers(comparison_client,market):
    data=request().model_dump(mode='json');data['market']=market
    assert comparison_client.post('/api/v1/research-market-comparison/compare',json=data).status_code==422


@pytest.mark.parametrize('payload',[b'{',b'{"market":',b'\xff',b'['*1500,b'{"market":NaN}',b'{"market":1e9999}'])
def test_malformed_overflowing_and_deep_json_are_safely_rejected(comparison_client,payload):
    r=comparison_client.post('/api/v1/research-market-comparison/compare',content=payload,headers={'content-type':'application/json'})
    assert r.status_code in (400,422),r.text
    assert 'Traceback' not in r.text and 'Internal Server Error' not in r.text


@pytest.mark.parametrize('path,method',[('/api/v1/strategy','put'),('/api/v1/simulation/run','post'),('/api/v1/research-vault/preview','post'),('/api/v1/research-market-comparison/compare','post')])
def test_all_api_write_surfaces_share_body_limit(path,method):
    c=TestClient(app)
    try:assert getattr(c,method)(path,content=iter([b'x'*40000,b'x'*40000])).status_code==413
    finally:c.close()
