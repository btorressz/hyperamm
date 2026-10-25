"""Credential values can be structured, and validation locations are untrusted."""
import copy,json
import pytest
from fastapi.testclient import TestClient
from app.diagnostics import sanitize_public_text,sanitize_public_diagnostic,sanitize_public_payload
from app.main import app

SENTINEL='SYNTHETIC_CREDENTIAL_SENTINEL'
@pytest.mark.parametrize('key',['api_key','api-key','apiKey','X-API-Key','access_token','refreshToken',
    'Authorization','Proxy-Authorization','private_key','password','client_secret','secret',
    'hyperliquid_private_key','redstone_api_key','coingecko_api_key'])
def test_structured_credentials_are_redacted_as_whole_values(key):
    payload={'error':{'context':[{key:{'nested':[SENTINEL]}}]},'market':'BTC','source_id':'https://domain-identifier.invalid'}
    before=copy.deepcopy(payload);safe=sanitize_public_payload(payload)
    assert SENTINEL not in json.dumps(safe) and '[REDACTED]' in json.dumps(safe)
    assert payload==before and safe['market']=='BTC' and safe['source_id']==payload['source_id']
    assert sanitize_public_payload(safe)==safe
    assert SENTINEL not in json.dumps(sanitize_public_diagnostic({key:SENTINEL}))


@pytest.mark.parametrize('message',[
    'Authorization: Bearer '+SENTINEL,'Proxy-Authorization: Basic '+SENTINEL,
    'https://user:'+SENTINEL+'@provider.invalid/?api_key='+SENTINEL,
    'api_key="'+SENTINEL+' with spaces"','private_key: 0x'+'a'*64,
])
def test_text_redaction_precedes_truncation_and_is_idempotent(message):
    safe=sanitize_public_text(message)
    assert SENTINEL not in safe and '0x'+'a'*64 not in safe
    assert sanitize_public_text(safe)==safe
    assert SENTINEL not in sanitize_public_text('x'*480+' '+message)


@pytest.mark.parametrize('path,payload',[
    ('/api/v1/research-vault/preview',{SENTINEL:'opaque'}),
    ('/api/v1/simulation/run',{'research':{'config':{SENTINEL:'opaque'}}}),
    ('/api/v1/strategy',{'base_spread_bps':SENTINEL}),
])
def test_validation_never_reflects_raw_input_or_unknown_field_names(path,payload):
    with TestClient(app) as c:
        r=(c.put if path.endswith('/strategy') else c.post)(path,json=payload)
        assert r.status_code==422,r.text
        assert SENTINEL not in r.text
        assert all('input' not in e and 'ctx' not in e for e in r.json()['detail'])
        assert r.headers['cache-control']=='no-store'


def test_comparison_internal_error_redacts_response_and_logs(monkeypatch,caplog):
    from phase154_helpers import request
    with TestClient(app) as c:
        def broken(market):raise RuntimeError(SENTINEL+' provider traceback')
        monkeypatch.setattr(app.state.live_market_streams,'snapshot',broken)
        r=c.post('/api/v1/research-market-comparison/compare',json=request().model_dump(mode='json'))
        assert r.status_code==500 and r.headers['cache-control']=='no-store'
        assert SENTINEL not in r.text and SENTINEL not in caplog.text


def test_unknown_strategy_fields_cannot_initiate_a_configuration_transition():
    from test_phase14_research_vault import authority
    with TestClient(app) as c:
        rt=app.state.runtime;before=authority(rt)
        for field in ['base_spread_bps','risk_override','hyperliquid_private_key']:
            result=c.put('/api/v1/strategy',json={field:SENTINEL})
            assert result.status_code==422 and SENTINEL not in result.text
            assert authority(rt)==before
