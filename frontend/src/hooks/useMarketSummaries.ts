import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { marketSummaryLifetimeMs, marketSummaryRefreshMs, type MarketSummary, type MarketSummaryScope } from '../utils/marketSummaries';
import { marketUniverseKey } from '../utils/marketUniverse';

export function useMarketSummaries(scope: MarketSummaryScope | null, active: boolean) {
  const refreshRequested = useRef(false);
  const [, tick] = useState(0);
  const enabled = active && !!scope?.markets.length;
  const query = useQuery({
    queryKey: ['market-summaries', scope],
    queryFn: async ({ signal }) => {
      const requestedAt = performance.now();
      const refresh = refreshRequested.current;
      refreshRequested.current = false;
      return { wire: await api.marketSummaries(scope!, refresh, signal), requestedAt };
    },
    enabled,
    retry: false,
    refetchInterval: enabled ? marketSummaryRefreshMs : false,
    staleTime: marketSummaryRefreshMs / 2,
    gcTime: marketSummaryLifetimeMs * 2,
  });
  useEffect(() => {
    if (!enabled || !query.data) return;
    const { wire, requestedAt } = query.data;
    const receivedAge = Date.parse(wire.evaluated_at);
    const deadlines = wire.results.flatMap(row => row.status === 'CURRENT' && row.valid_until
      ? [Date.parse(row.valid_until)] : []);
    const notify = () => tick(previous => previous + 1);
    const expirations = [...new Set(deadlines)].map(expiry => window.setTimeout(notify,
      Math.max(0, Math.min(expiry - Date.now(), requestedAt + expiry - receivedAge - performance.now()))));
    const timer = window.setInterval(notify, 1000);
    window.addEventListener('pageshow', notify);
    document.addEventListener('visibilitychange', notify);
    return () => {
      expirations.forEach(clearTimeout);
      window.clearInterval(timer);
      window.removeEventListener('pageshow', notify);
      document.removeEventListener('visibilitychange', notify);
    };
  }, [enabled, query.data]);

  const rows = new Map(query.data?.wire.results.map(row => [marketUniverseKey(row.identity), row]));
  function current(row: MarketSummary | undefined): MarketSummary | undefined {
    if (!enabled || query.isError || row?.status !== 'CURRENT' || !row.valid_until || !query.data) return;
    const expires = Date.parse(row.valid_until);
    const elapsed = performance.now() - query.data.requestedAt;
    if (Date.now() < expires && elapsed < expires - Date.parse(query.data.wire.evaluated_at)) return row;
  }
  return {
    rows, current, isFetching: query.isFetching, error: query.error?.message,
    refresh: () => {
      if (!enabled || query.isFetching) return;
      refreshRequested.current = true;
      void query.refetch();
    },
  };
}
