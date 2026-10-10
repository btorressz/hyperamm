import { useState } from "react";
import type { TerminalState, HistoryRange } from "../types";
import {
  displayRanges,
  displayHistorySizes,
  useDisplayStore,
} from "../stores/display";
import { useTerminalStore } from "../stores/terminal";
import { SystemHealth } from "../components/SystemHealth";
import { ProviderHealthSummary } from "../components/settings/ProviderHealthSummary";
import { Badge } from "../components/Badge";
import {
  Panel,
  Metrics,
  StatusBanner,
  Empty,
} from "../components/TerminalPrimitives";
import { sessionCurrent, evidenceTime } from "../utils/researchEvidence";
import "../phase1333.css";

export function Settings({
  t,
  historical = false,
}: {
  t: TerminalState | null;
  historical?: boolean;
}) {
  const d = useDisplayStore(),
    s = useTerminalStore();
  const current = !!t && !historical && sessionCurrent(t, s);
  const [confirmReset, setConfirmReset] = useState(false);
  const [feedback, setFeedback] = useState("");
  function change(
    action: () => void,
    message = "Display preferences updated.",
  ) {
    action();
    try {
      const stored = JSON.parse(
        localStorage.getItem("hyperamm-display-v1") ?? "null",
      )?.state;
      const state = useDisplayStore.getState();
      const saved =
        stored &&
        ["dense", "sidebarCollapsed", "historySize", "defaultRange"].every(
          (key) => stored[key] === state[key as keyof typeof state],
        );
      setFeedback(
        saved
          ? message + " Saved locally in this browser."
          : message +
              " Local persistence unavailable; preferences apply to this page.",
      );
    } catch {
      setFeedback(
        message +
          " Local persistence unavailable; preferences apply to this page.",
      );
    }
  }
  return (
    <div className="operationsWorkspace settingsPage stack">
      <div className="researchPageTitle">
        <div>
          <h1>Settings & system configuration</h1>
          <p className="muted">
            Browser preferences and read-only operational evidence
          </p>
        </div>
        <Badge tone={current ? "blue" : "warn"}>
          {current ? "CURRENT OBSERVATION" : "HISTORICAL / WAITING"}
        </Badge>
      </div>
      {!current && (
        <StatusBanner>
          Historical or unavailable backend evidence · last-known health and
          authorization do not establish current authority. Browser preferences
          remain editable.
        </StatusBanner>
      )}
      <Panel title="Display preferences" meta="Browser-only · editable here">
        <p className="muted">
          Preferences save locally in this browser. They do not change backend
          trading behavior and are not shared account preferences or
          synchronized across devices.
        </p>
        <fieldset className="preferenceGroup">
          <legend>Layout</legend>
          <div className="formGrid">
            <label>
              Layout density
              <select
                aria-label="Layout density"
                value={d.dense ? "dense" : "comfortable"}
                onChange={(e) =>
                  change(() => d.setDense(e.target.value === "dense"))
                }
              >
                <option value="comfortable">Comfortable</option>
                <option value="dense">Dense</option>
              </select>
            </label>
            <label>
              Sidebar layout
              <select
                aria-label="Sidebar layout"
                value={d.sidebarCollapsed ? "collapsed" : "expanded"}
                onChange={(e) =>
                  change(() =>
                    d.setSidebarCollapsed(e.target.value === "collapsed"),
                  )
                }
              >
                <option value="expanded">Expanded</option>
                <option value="collapsed">Collapsed</option>
              </select>
            </label>
          </div>
        </fieldset>
        <fieldset className="preferenceGroup">
          <legend>Charts</legend>
          <div className="formGrid">
            <label>
              Default chart range
              <select
                aria-label="Default chart range"
                value={d.defaultRange}
                onChange={(e) =>
                  change(() =>
                    d.setDefaultRange(e.target.value as HistoryRange),
                  )
                }
              >
                {displayRanges.map((r) => (
                  <option key={r} value={r}>
                    {r.toUpperCase()}
                  </option>
                ))}
              </select>
            </label>
            <label>
              History view size
              <select
                aria-label="History view size"
                value={d.historySize}
                onChange={(e) =>
                  change(() => d.setHistorySize(Number(e.target.value)))
                }
              >
                {displayHistorySizes.map((n) => (
                  <option key={n} value={n}>
                    {n} observations
                  </option>
                ))}
              </select>
            </label>
          </div>
          <p className="muted panelNote">
            An unavailable saved range remains your preference while Analytics
            temporarily displays SESSION until enough server history is
            retained.
          </p>
        </fieldset>
        <button onClick={() => setConfirmReset(true)}>
          Reset display preferences
        </button>
        {confirmReset && (
          <div
            className="preferenceReset"
            role="group"
            aria-label="Confirm display preference reset"
          >
            <p>
              Reset all four browser preferences: Comfortable density, Expanded
              sidebar, SESSION default chart range and 600 history observations.
            </p>
            <div className="operationsActions">
              <button
                onClick={() => {
                  change(
                    d.resetDisplayPreferences,
                    "Display preferences reset.",
                  );
                  setConfirmReset(false);
                }}
              >
                Confirm display reset
              </button>
              <button onClick={() => setConfirmReset(false)}>
                Cancel reset
              </button>
            </div>
          </div>
        )}
        <p className="localPreferenceFeedback" role="status" aria-live="polite">
          {feedback ||
            "Owned preferences: density, sidebar, default range and history size."}
        </p>
      </Panel>
      {!t ? (
        <Panel title="Runtime & environment" meta="Backend-owned · read-only">
          <Empty>
            Waiting for accepted terminal evidence. Runtime configuration and
            provider health are unavailable.
          </Empty>
        </Panel>
      ) : (
        <>
          <Panel
            title="Runtime & environment"
            meta={
              current
                ? "Backend-owned · read-only · AT EMISSION"
                : "Backend-owned · read-only · HISTORICAL"
            }
          >
            <Metrics
              items={[
                ["Market data mode", t.market.mode],
                ["Execution mode", t.strategy.config.execution_mode],
                [
                  "Signed TESTNET enabled",
                  t.diagnostics.testnet_enabled ? "ENABLED" : "DISABLED",
                ],
                [
                  "Reference firewall enabled",
                  t.diagnostics.reference_firewall_enabled
                    ? "ENABLED"
                    : "DISABLED",
                ],
                ["Terminal contract version", t.contract_version],
                ["Accepted terminal sequence", t.sequence],
                ["WebSocket connection", s.wsState.toUpperCase()],
                ["Reconnect attempts", s.reconnectAttempts],
              ]}
            />
            <details className="researchInset runtimeIdentity">
              <summary>Inspect process, session and emission identity</summary>
              <dl className="operationsDetails">
                <dt>Client-observed process</dt>
                <dd>
                  <code>{t.process_id}</code>
                </dd>
                <dt>Accepted session</dt>
                <dd>
                  <code>{t.session_id}</code>
                </dd>
                <dt>Envelope emitted</dt>
                <dd>{evidenceTime(t.emitted_at)}</dd>
              </dl>
            </details>
            <p className="muted panelNote">
              MARKET_DATA_MODE, EXECUTION_MODE, signing eligibility, provider
              configuration and runtime execution boundaries are controlled by
              the backend. A TESTNET flag does not prove account authentication
              or order acceptance. Redis availability and unreported environment
              values are unavailable here.
            </p>
            <p className="muted panelNote">
              Supported deployment: loopback, one local operator and one backend
              worker. External provider, Redis and signed TESTNET acceptance
              remain separate verification gates.
            </p>
          </Panel>
          <Panel
            title="Operational authority layers"
            meta={
              current
                ? "Reported decisions at emission"
                : "HISTORICAL · last-known decisions"
            }
          >
            <Metrics
              items={[
                ["Transport connection", s.wsState.toUpperCase()],
                [
                  "Market data integrity",
                  t.system_health.subsystems.market_feed?.status ??
                    "Unavailable",
                ],
                [
                  "Reference health",
                  t.reference_consensus?.confidence_state ?? "Unavailable",
                ],
                ["RiskFirewall decision", t.risk_firewall.state],
                [
                  "FinalQuoteAuthorization",
                  t.risk_authorization.authorized
                    ? "REPORTED AUTHORIZED"
                    : "REPORTED BLOCKED",
                ],
                [
                  "Manual kill switch",
                  t.risk.kill_switch_active ? "KILL ACTIVE" : "KILL INACTIVE",
                ],
                [
                  "Accounting consistency",
                  t.accounting.execution_accounting.status,
                ],
              ]}
            />
            <p className="muted panelNote">
              Transport, source integrity, reference consensus, RiskFirewall,
              FinalQuoteAuthorization, manual kill and accounting are separate
              evidence layers. Risk HALT is distinct from manual KILL. SHADOW
              remains observational. Healthy observations do not grant trading
              permission.
            </p>
          </Panel>
          <ProviderHealthSummary t={t} historical={!current} />
          <SystemHealth t={t} historical={!current} />
          <p className="muted panelNote">
            Transport ages, last accepted frame and
            stale/future/replay/schema/order/time rejection counters are shown
            in the shared Terminal observation panel above.
          </p>
        </>
      )}
    </div>
  );
}
