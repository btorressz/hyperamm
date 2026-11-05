import type { ReplayArchive, ReplaySegment } from '../../types/replay';
import { Panel, Metrics, Empty } from '../TerminalPrimitives';
import { researchMetric } from '../SimulationPanel';
import { livePrice } from '../../utils/format';
export function ReplayComparison({segment,modeled,baseline}:{segment:ReplaySegment;modeled:ReplayArchive;baseline:ReplayArchive|null}) {
  return <Panel title="Baseline vs modeled crossing" meta="SAME SEGMENT · SEPARATE PAPER ENGINE RUNS">
    {!baseline?<Empty>Baseline-only execution selected. Change to modeled crossing to generate the authoritative per-segment baseline comparison.</Empty>:<>
      <div className="replayCompare">
        <div><h3>Baseline crossing-only</h3><Metrics items={[
          ['PAPER PnL',researchMetric('session_pnl',baseline.metrics.session_pnl)],
          ['Fills',String(baseline.metrics.fill_count)],
          ['Drawdown',researchMetric('max_drawdown_pct',baseline.metrics.max_drawdown_pct)]
        ]}/></div>
        <div><h3>Modeled crossing</h3><Metrics items={[
          ['PAPER PnL',researchMetric('session_pnl',modeled.metrics.session_pnl)],
          ['Fills',String(modeled.metrics.fill_count)],
          ['Drawdown',researchMetric('max_drawdown_pct',modeled.metrics.max_drawdown_pct)]
        ]}/></div>
      </div>
      <Metrics items={[
        ['Backend session PnL delta (quote)',segment.session_pnl_delta == null?'Unavailable':livePrice(segment.session_pnl_delta)],
        ['Backend fill count delta',segment.fill_count_delta == null?'Unavailable':String(segment.fill_count_delta)]
      ]}/>
      <p className="muted panelNote">Differences are server-computed from separately executed simulated results under the same segment inputs. No client-side financial delta is authoritative. Results do not forecast actual execution.</p>
    </>}
  </Panel>;
}
