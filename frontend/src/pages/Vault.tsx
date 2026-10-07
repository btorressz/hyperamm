import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { TerminalState } from "../types";
import { VaultSummary } from "../components/VaultSummary";
import { PnlBreakdown } from "../components/PnlBreakdown";
import { AccountingLedger } from "../components/AccountingLedger";
import "../phase11.css";
import { SessionCharts } from "./Analytics";

export function Vault({ t }: { t: TerminalState }) {
  const vault = t.vault;
  const ledger = useQuery({
    queryKey: [
      "accounting-ledger",
      vault.mode,
      vault.market,
      vault.ledger_fingerprint,
    ],
    queryFn: () => api.accountingLedger(100),
    refetchInterval: 5000,
    gcTime: 0,
  });
  return (
    <div className="vaultPage">
      <VaultSummary vault={vault} />
      <SessionCharts />
      <PnlBreakdown pnl={t.accounting.pnl} vault={vault} />
      {ledger.isError && (
        <p className="dangerText" role="alert">
          Accounting ledger could not be loaded.
        </p>
      )}
      {ledger.isPending && <p className="muted">Loading accounting ledger…</p>}
      <AccountingLedger ledger={ledger.data} mode={vault.mode} />
      <section className="panel vaultProvenance">
        <div className="panelHead">
          <b>Accounting Provenance</b>
          <span>Version {t.accounting.accounting_version}</span>
        </div>
        <p className="muted">
          Accounting fingerprint{" "}
          <code>{t.accounting.accounting_fingerprint}</code>
        </p>
        <p className="muted">
          Ledger fingerprint <code>{t.accounting.ledger_fingerprint}</code>
        </p>
        <p className="muted">
          Updated{" "}
          {t.vault.updated_at
            ? new Date(t.vault.updated_at).toLocaleString()
            : "Unavailable"}
        </p>
        <div className="vaultEvents">
          {t.accounting.events.map((event, index) => (
            <p key={index} className="muted">
              <b>{event.category}</b> ·{" "}
              {new Date(event.timestamp).toLocaleTimeString()} · {event.message}
            </p>
          ))}
        </div>
      </section>
    </div>
  );
}
