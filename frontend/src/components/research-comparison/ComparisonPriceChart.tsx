import type {MarketResearchComparisonResult} from '../../types';
import {pairedPriceEvidence,comparisonTimestamp} from '../../utils/marketResearchComparison';
import {Panel} from '../TerminalPrimitives';
import {livePrice} from '../../utils/format';
export function ComparisonPriceChart({data}:{data:MarketResearchComparisonResult}) {
  const pair=pairedPriceEvidence(data);
  // Static paired evidence graphic: no common timeline, offsets, candles or interpolation.
  return <Panel title="Price · two independent contexts" meta="STATIC PAIRED CAPTURE">
    <div className="comparisonPair" role="img" aria-label="Observed and hypothetical midpoints with independent source timestamps">
      <div><span>OBSERVED NATIVE MIDPOINT</span><strong>{livePrice(pair.observed.value)}</strong><small>quote / {data.market}</small><p>{pair.observed.label}</p><time>{comparisonTimestamp(pair.observed.time)}</time></div>
      <div><span>HYPOTHETICAL PAPER MIDPOINT</span><strong>{livePrice(pair.research.value)}</strong><small>quote / {data.research.research_market}</small><p>{pair.research.label}</p><time>{comparisonTimestamp(pair.research.time)}</time></div>
    </div>
    <p className="muted">Independent timestamps. These values are not simultaneous market ticks or a historical replay. Missing observations remain unavailable.</p>
  </Panel>;
}
