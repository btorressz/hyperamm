import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.portfolio_research.models import PortfolioStressResult
from app.portfolio_research import aggregation
from app.simulation.service import SimulationService
from app.simulation.executor import ResearchBusyError
from app.infrastructure.research import ResearchUnavailableError
from phase174_fixtures import request_for, native174, KINDS
from test_phase14_research_vault import research_client, authority
from test_phase166c2_local_integration import local_server

URL="/api/v1/portfolio-research/stress"


def test_six_routes_return_bounded_native_receipts_and_preserve_authority(research_client,native174):
    client,rt=research_client
    before=authority(rt)
    response=client.post(URL,json=native174.request.model_dump(mode="json"))
    assert response.status_code==200,response.text
    assert response.json()==native174.model_dump(mode="json")
    assert response.headers["cache-control"]=="no-store" and len(response.content)<=200000
    assert authority(rt)==before and not app.state.simulation_executor._busy

@pytest.mark.parametrize("corruption",["result","dataset","execution","fingerprint","shock","extra"])
def test_invalid_inputs_never_admitted(research_client,monkeypatch,corruption):
    client,rt=research_client;raw=request_for().model_dump(mode="json")
    if corruption=="result": raw["baseline"]={"authoritative":True}
    elif corruption=="dataset": raw["_trusted_dataset"]={"frames":[]}
    elif corruption=="execution": raw["config"]["execution_mode"]="TESTNET"
    elif corruption=="fingerprint": raw["config_fingerprint"]="f"*64
    elif corruption=="shock": raw["scenario"]["assumptions"]["price_shocks"][0]["decline_fraction"]=0.06
    else: raw["/private/secret"]="secret"
    async def forbidden(*args,**kwargs): pytest.fail("invalid input entered worker")
    monkeypatch.setattr(app.state.simulation_executor,"execute",forbidden)
    response=client.post(URL,json=raw)
    assert response.status_code==422 and "/private/secret" not in response.text
    assert response.headers["cache-control"]=="no-store"

@pytest.mark.parametrize("headers",[{"Host":"attacker.invalid"},{"Origin":"https://attacker.invalid"},{"Origin":"http://127.0.0.1:5999"},{"X-Forwarded-For":"127.0.0.1"}])
def test_local_http_security_applies(research_client,headers):
    client,_=research_client
    assert client.post(URL,json=request_for().model_dump(mode="json"),headers=headers).status_code==403

@pytest.mark.parametrize("chunked",[False,True])
def test_body_bound_before_parsing(research_client,chunked):
    client,_=research_client
    body=iter([b"x"*40000,b"x"*40000]) if chunked else b"x"*65537
    response=client.post(URL,content=body)
    assert response.status_code==413 and response.headers["cache-control"]=="no-store"

@pytest.mark.parametrize("exception,status",[(ResearchBusyError("/private/secret"),429),(ResearchUnavailableError(),503),
    (ValueError("/private/secret"),422),(RuntimeError("/private/secret"),500)])
def test_errors_are_sanitized(research_client,monkeypatch,exception,status):
    client,_=research_client
    async def broken(*args,**kwargs):raise exception
    monkeypatch.setattr(app.state.simulation_executor,"execute",broken)
    response=client.post(URL,json=request_for().model_dump(mode="json"))
    assert response.status_code==status and "/private/secret" not in response.text
    assert response.headers["cache-control"]=="no-store"


def test_exact_response_limit_and_failure_release(research_client,monkeypatch):
    client,_=research_client
    r=request_for(markets=("BTC",))
    result=asyncio.run(SimulationService().stress_portfolio_research(request=r))
    size=len(result.model_dump_json().encode())
    monkeypatch.setattr(aggregation,"MAX_RESPONSE_BYTES",size)
    assert len(client.post(URL,json=r.model_dump(mode="json")).content)==size
    monkeypatch.setattr(aggregation,"MAX_RESPONSE_BYTES",size-1)
    response=client.post(URL,json=r.model_dump(mode="json"))
    assert response.status_code==413 and not app.state.simulation_executor._busy


def test_concurrent_requests_remain_busy_during_stressed_leg(research_client,monkeypatch):
    client,_=research_client;started,release=Event(),Event()
    original=SimulationService._run_portfolio_dataset
    async def held(self,**kwargs):
        started.set();assert release.wait(15)
        return await original(self,**kwargs)
    monkeypatch.setattr(SimulationService,"_run_portfolio_dataset",held)
    with ThreadPoolExecutor(max_workers=1) as caller:
        first=caller.submit(client.post,URL,json=request_for(markets=("BTC",)).model_dump(mode="json"))
        try:
            assert started.wait(10)
            assert client.post(URL,json=request_for().model_dump(mode="json")).status_code==429
            assert client.post("/api/v1/simulation/run",json={"frames":2}).status_code==429
        finally:release.set()
        assert first.result(timeout=15).status_code==200


def test_actual_uvicorn_all_scenarios_and_security(tmp_path):
    with local_server(tmp_path) as client:
        for kind in KINDS:
            r=request_for(kind,onset=7 if kind=="CONCENTRATION_STRESS" else 4)
            response=client.post(URL,json=r.model_dump(mode="json"))
            assert response.status_code==200,response.text
            assert PortfolioStressResult.model_validate_json(response.content).request==r
            assert response.headers["cache-control"]=="no-store"
        assert client.post(URL,json={}).status_code==422
        assert client.post(URL,content=b" "*65537).status_code==413
        for headers in ({"Host":"attacker.invalid"},{"Origin":"https://attacker.invalid"},{"X-Forwarded-For":"127.0.0.1"}):
            assert client.post(URL,json=r.model_dump(mode="json"),headers=headers).status_code==403


def test_redis_outage_fails_closed_over_actual_http(tmp_path):
    with local_server(tmp_path,redis=True,coordination=True) as client:
        response=client.post(URL,json=request_for().model_dump(mode="json"))
        assert response.status_code==503


def test_remote_peer_cannot_compute():
    with TestClient(app,client=("203.0.113.10",10000)) as client:
        assert client.post(URL,json=request_for().model_dump(mode="json")).status_code==403


def test_existing_operational_orders_kill_switch_and_signing_are_untouched(research_client,monkeypatch):
    from copy import deepcopy
    from decimal import Decimal
    from app.execution.models import OrderRequest
    client,rt=research_client
    asyncio.run(rt.paper.submit_orders([OrderRequest(client_order_id="phase174-existing",market="BTC",side="BID",price=Decimal("1"),size=Decimal(".001"))]))
    rt.risk.kill_switch_active=True
    before,history=authority(rt),deepcopy(rt.market_history.__dict__)
    listeners=tuple(rt.market._listeners)
    signing=(id(rt.testnet),id(rt.testnet.authority),rt.testnet.enabled,id(rt.settings),rt.settings.enable_hyperliquid_testnet_orders)
    def forbidden(*args,**kwargs):pytest.fail("stress accessed operational adapter")
    for adapter in (rt.paper,rt.testnet):
        for name in ("submit_orders","cancel_orders","replace_orders","get_account_state"):
            if hasattr(adapter,name):monkeypatch.setattr(adapter,name,forbidden)
    response=client.post(URL,json=request_for().model_dump(mode="json"))
    assert response.status_code==200,response.text
    assert authority(rt)==before and rt.market_history.__dict__==history
    assert tuple(rt.market._listeners)==listeners
    assert signing==(id(rt.testnet),id(rt.testnet.authority),rt.testnet.enabled,id(rt.settings),rt.settings.enable_hyperliquid_testnet_orders)
