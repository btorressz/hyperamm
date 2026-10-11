"""Reproducible actual PAPER summary + normalized observation fixtures, never venue data."""
import asyncio,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'));sys.path.insert(0,str(ROOT/'backend/tests'))
from phase154_helpers import result_summary,market_profile
from app.simulation.service import SimulationService
from app.simulation.config import SimulationConfig
from app.strategy.models import StrategyConfig
from app.agents.config import AgentConfig
from app.risk.firewall import RiskFirewallConfig
from app.market_data.live_stream_models import LiveStreamSnapshot
from app.research_comparison.models import ResearchMarketComparisonRequest
from app.research_comparison.comparison import compare
from test_phase152_live_streams import create,eventually
from decimal import Decimal as D
async def main():
    service,sdk,clock=create()
    for m in ['BTC','ETH','SOL']:
        step={'BTC':D('10'),'ETH':D('1'),'SOL':D('.01')}[m]
        if m=='SOL':
            sdk.books[m]['levels'][0][0].update(px='150.12',sz='1.23')
            sdk.books[m]['levels'][1][0].update(px='150.13',sz='2.34')
        for side,sign in [(0,-1),(1,1)]:
            first=sdk.books[m]['levels'][side][0]
            sdk.books[m]['levels'][side]=[dict(px=str(D(first['px'])+sign*step*i),sz=str(D(first['sz'])+i),n=2) for i in range(5)]
    await service.start()
    await eventually(lambda:all(s.context is not None and s.barrier for s in service.states.values()))
    clock.advance(.5)
    for m in ['BTC','ETH','SOL']:
        sdk.books[m]['time']=int(clock().timestamp()*1000)
        sdk.emit(m,'l2Book');sdk.emit(m,'activeAssetCtx')
    await eventually(lambda:all(service.snapshot(m).observation_status=='AVAILABLE' for m in ['BTC','ETH','SOL']))
    raw={m:{'snapshot':service.snapshot(m).model_dump(mode='json')} for m in ['BTC','ETH','SOL']}
    await service.close()
    out={}
    for m in ['BTC','ETH','SOL']:
        result=await SimulationService().run_scenario(scenario='QUIET',frames=3,strategy=StrategyConfig(),
            agents=AgentConfig(),risk=RiskFirewallConfig(),simulation=SimulationConfig(max_frames=3),market_profile=market_profile(m))
        r=result_summary(result);req=ResearchMarketComparisonRequest(market=m,research=r)
        out[m]={'request':req.model_dump(mode='json'),'response':compare(req,LiveStreamSnapshot.model_validate(raw[m]['snapshot'])).model_dump(mode='json')}
    (ROOT/'frontend/tests/phase154-fixtures.json').write_text(json.dumps(out,indent=2)+'\n')
if __name__=='__main__':asyncio.run(main())
