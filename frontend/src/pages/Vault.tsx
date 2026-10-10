import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import type { TerminalState } from '../types';
import { useTerminalStore } from '../stores/terminal';
import { useResearchSession } from '../hooks/useResearchSession';
import { checkedLedger, ledgerKey, ledgerMatches } from '../utils/researchEvidence';
import { VaultSummary } from '../components/VaultSummary';
import { PnlBreakdown } from '../components/PnlBreakdown';
import { AccountingLedger } from '../components/AccountingLedger';
import { AccountingConsistency } from '../components/vault/AccountingConsistency';
import { AccountingProvenance } from '../components/vault/AccountingProvenance';
import { Panel, StatusBanner } from '../components/TerminalPrimitives';
import { SessionCharts } from './Analytics';
import '../phase11.css';
import '../phase1331.css';
export function Vault({t,historical = false}: {t: TerminalState; historical?: boolean}) {
  const v = t.vault, session = useResearchSession(t,historical);
  const ledger = useQuery({
    queryKey: ['accounting-ledger',...ledgerKey(t),session.epoch],
    queryFn: async ({signal}) => {
      session.check();
      const response = await api.accountingLedger(100,signal);
      session.check();
      return checkedLedger(response,t,useTerminalStore.getState());
    },
    enabled: session.enabled && !v.stale && !v.error,
    refetchInterval: false, refetchOnWindowFocus: false, retry: false, gcTime: 0,
  });
  const available = session.enabled && !v.stale && !v.error;
  const visible = available && ledger.data && ledgerMatches(ledger.data,t) ? ledger.data : undefined;
  return <div className="researchWorkspace vaultPage">
    <div className="researchPageTitle"><div><h1>Research vault & accounting</h1><p className="muted">Capital, economics and session ledger provenance</p></div></div>
    {historical && <StatusBanner>Historical financial observations · last accepted snapshot. Current ledger evidence is unavailable while disconnected.</StatusBanner>}
    {!historical && (v.stale || v.error) && <StatusBanner>Accounting evidence is {v.error ? 'in error' : 'stale'}; last-known financial values do not establish current capital authority.</StatusBanner>}
    <VaultSummary vault={v} historical={historical}/>
    <PnlBreakdown pnl={t.accounting.pnl} vault={v}/>
    <AccountingConsistency vault={v} historical={historical}/>
    <section aria-label="Vault session charts"><h2>Session observations</h2><p className="muted">Backend observation history. Gaps and restarts remain separate; missing values are not interpolated.</p><SessionCharts/></section>
    {!available ? <Panel title="Accounting ledger"><p className="muted panelNote" role="status">Current ledger evidence unavailable: waiting for a connected session and usable accounting evidence.</p></Panel>
      : ledger.isError ? <Panel title="Accounting ledger"><p className="inlineError" role="alert">Accounting ledger could not be loaded: {ledger.error.message}</p><button className="researchInset" type="button" onClick={() => void ledger.refetch()}>Retry ledger observation</button></Panel>
      : !visible ? <Panel title="Accounting ledger"><p className="muted panelNote" role="status">Loading / reconciling current ledger evidence…</p></Panel>
      : <AccountingLedger key={`${t.process_id}:${t.session_id}`} ledger={visible} mode={v.mode}/>}
    <AccountingProvenance t={t}/>
  </div>;
}
