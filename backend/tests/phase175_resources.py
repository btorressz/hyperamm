"""Measure complete/retention-boundary terminal responses in one native job each.
Run from backend: PYTHONPATH=tests python tests/phase175_resources.py
"""
import asyncio,json
from pathlib import Path
from app.portfolio_research.preview import prepare
from app.portfolio_research.terminal_models import TerminalRequest
from app.simulation.service import SimulationService
from app.portfolio_research import aggregation
from test_phase175_terminal import draft,profiles
from phase174_fixtures import request_for

async def main():
    report=[]
    original=aggregation.assemble_stress
    source_sizes=[]
    def measured(*a,**kw):
        result=original(*a,**kw);source_sizes.append(len(result.model_dump_json().encode()));return result
    aggregation.assemble_stress=measured
    try:
      for frames in (250,300,500):
        scenario=request_for(frames=frames,onset=30,duration=60).scenario
        preview=prepare(draft(frames=frames,stress=scenario),profiles())
        q=TerminalRequest(mode='STRESS',config=preview.config,config_fingerprint=preview.config_fingerprint,
            risk_policy=preview.risk_policy,scenario=preview.stress)
        result=await SimulationService().terminal_portfolio_research(request=q)
        wire=result.model_dump_json().encode()
        row={'markets':3,'frames_per_market_per_leg':frames,'request_bytes':len(q.model_dump_json().encode()),
          'original_stress_bytes':source_sizes[-1],'terminal_bytes':len(wire),'workload':preview.workload,
          'classification':result.baseline.temporal.classification,'risk_outcome':result.baseline.risk.outcome,
          'risk_decision':result.baseline.risk.decision,'baseline_points':len(result.baseline.charts.points),
          'stressed_points':len(result.stressed.charts.points),'sampled':result.baseline.charts.sampled}
        assert len(wire)<=200000 and row['request_bytes']<=65536
        assert row['baseline_points']<=120 and row['stressed_points']<=120
        if frames==250:
            assert row['classification']=='MODELED_ALIGNED' and row['sampled']
            assert result.baseline.charts.points[0].sequence==1 and result.baseline.charts.points[-1].sequence==frames
        else:
            assert row['classification']=='FINAL_ONLY' and row['risk_outcome']=='BLOCKED'
            assert not result.baseline.charts.points and not result.stressed.charts.points
        report.append(row);print(json.dumps(row),flush=True)
    finally:aggregation.assemble_stress=original
    target=Path('../work/phase175-resources.json');target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':asyncio.run(main())
