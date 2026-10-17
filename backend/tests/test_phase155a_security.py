"""Adversarial HTTP/WS checks against the real shared local boundary."""
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.config import Settings
from app.deployment import LocalOnlyBoundary
from app.main import app


async def boundary(headers=(), *, kind='http', peer=('127.0.0.1', 123), scheme='http'):
    called, sent = [], []
    async def endpoint(scope, receive, send):called.append(True)
    async def receive():raise AssertionError('boundary must not consume a rejected body')
    async def send(message):sent.append(message)
    await LocalOnlyBoundary(endpoint)({'type':kind,'scheme':scheme,'method':'POST','path':'/',
        'client':peer,'headers':list(headers)},receive,send)
    return bool(called),sent


BAD_HOSTS = ['evil.example','localhost.evil.example','127.0.0.1.evil.example','0.0.0.0','192.168.0.1',
    'user@localhost:8000','localhost:8000/path','localhost:8000?x','localhost:8000#x',' localhost:8000',
    'localhost:8000 ','localhost:','localhost:0','localhost:65536','localhost:abc','localhost\\evil',
    '[::1%lo]:8000','[::1','localhost:8000,evil.example','']
@pytest.mark.parametrize('kind',['http','websocket'])
@pytest.mark.parametrize('host',BAD_HOSTS)
async def test_malformed_remote_and_rebinding_hosts_denied(kind,host):
    called,sent=await boundary([(b'host',host.encode())],kind=kind)
    assert not called
    assert sent[0].get('status',sent[0].get('code')) == (403 if kind=='http' else 1008)


BAD_ORIGINS=['http://localhost:9999','http://127.0.0.1:9999','https://evil.example','null',
    'ftp://localhost','ws://localhost:5173','http://user@localhost:5173','http://localhost:5173/',
    'http://localhost:5173?','http://localhost:5173#','http://localhost:5173/path','http://localhost.evil:5173',
    'http://localhost:5173 https://evil.example','http://[::1%lo]:5173']
@pytest.mark.parametrize('kind',['http','websocket'])
@pytest.mark.parametrize('origin',BAD_ORIGINS)
async def test_unrelated_localhost_and_malformed_origins_denied(kind,origin):
    called,_=await boundary([(b'host',b'127.0.0.1:8000'),(b'origin',origin.encode())],kind=kind)
    assert not called


@pytest.mark.parametrize('kind',['http','websocket'])
@pytest.mark.parametrize('origin',[None,'http://localhost:5173','http://127.0.0.1:5173','http://[::1]:5173','http://127.0.0.1:8000'])
async def test_cli_testclient_and_explicit_vite_origins_preserved(kind,origin):
    headers=[(b'host',b'127.0.0.1:8000')]+([] if origin is None else [(b'origin',origin.encode())])
    assert (await boundary(headers,kind=kind))[0]


@pytest.mark.parametrize('header',[b'host',b'origin',b'sec-fetch-site'])
async def test_duplicate_security_headers_fail_closed(header):
    headers=[(b'host',b'localhost:8000')]
    if header!=b'host':headers.append((header,b'http://localhost:5173' if header==b'origin' else b'same-origin'))
    headers.append((header,dict(headers)[header]))
    assert not (await boundary(headers))[0]


@pytest.mark.parametrize('header',[b'forwarded',b'x-forwarded-for',b'x-forwarded-host',b'x-forwarded-proto',b'x-real-ip'])
async def test_forwarding_headers_never_grant_or_change_access(header):
    assert not (await boundary([(b'host',b'localhost:8000'),(header,b'127.0.0.1')]))[0]


@pytest.mark.parametrize('site',[b'cross-site',b'same-site'])
async def test_browser_requests_without_origin_cannot_use_same_site_localhost_ports(site):
    assert not (await boundary([(b'host',b'localhost:8000'),(b'sec-fetch-site',site)]))[0]


async def test_remote_peer_and_testserver_host_are_not_authorized_by_browser_headers():
    for peer in [('203.0.113.1',12),None]:
        assert not (await boundary([(b'host',b'localhost'),(b'origin',b'http://localhost:5173')],peer=peer))[0]
    assert not (await boundary([(b'host',b'testserver')]))[0]
    assert (await boundary([(b'host',b'testserver')],peer=('testclient',1)))[0]
    assert (await boundary([(b'host',b'[::1]:8000')],peer=('::1',1)))[0]


@pytest.mark.parametrize('origin',['*','https://evil.example','null','file://localhost','http://localhost:5173/path','http://user@localhost:5173'])
def test_cors_settings_cannot_open_remote_or_wildcard_origins(origin):
    with pytest.raises(ValidationError):Settings(_env_file=None,cors_origins=origin)


def test_real_application_preflight_and_boundary_precedence():
    with TestClient(app) as client:
        for origin in Settings(_env_file=None).cors_origin_list:
            result=client.options('/api/v1/health',headers={'Origin':origin,'Access-Control-Request-Method':'GET'})
            assert result.status_code==200 and result.headers['access-control-allow-origin']==origin
        denied=client.post('/api/v1/strategy/start',content=b'x'*65537,headers={'origin':'http://localhost:9999'})
        assert denied.status_code==403 and denied.headers['cache-control']=='no-store'
        assert not app.state.runtime.strategy.running
