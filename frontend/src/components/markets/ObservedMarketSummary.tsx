import { useMarketSummaries } from '../../hooks/useMarketSummaries';
import { observedNumber, type MarketSummaryScope } from '../../utils/marketSummaries';

export function ObservedMarketSummary({ scope, active }: {
  scope: MarketSummaryScope | null;
  active: boolean;
}) {
  const observations = useMarketSummaries(scope, active);
  const row = scope && observations.rows.get(scope.markets[0].key);
  const current = observations.current(row || undefined);
  return <div className="selectedMarketObservation">
    <strong>Public market observation</strong>
    {current ? <dl>
      <div><dt>Mark price</dt><dd>{observedNumber(current.mark_price)}{current.mark_price && ' provider quote / base'}</dd></div>
      <div><dt>Funding / hour</dt><dd>{observedNumber(current.funding_rate, '%')}</dd></div>
      {current.observed_at && <div><dt>Server receipt</dt><dd>
        <time dateTime={current.observed_at}>{new Date(current.observed_at).toLocaleTimeString()}</time>
      </dd></div>}
    </dl> : <p className="muted">{observations.isFetching ? 'Updating…' :
      row && (row.status === 'STALE' || row.status === 'CURRENT') ? 'Stale' : 'Unavailable'}</p>}
  </div>;
}
