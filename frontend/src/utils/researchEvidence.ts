import type { AccountingLedgerState, AgentEvent, TerminalState } from '../types';
import { terminalEnvelopeFailure } from './terminalIntegrity';
import { exactDecimal } from './orderView';

export const agentNames = ['REGIME', 'TOXIC_FLOW', 'EXECUTION_QUALITY', 'LIQUIDITY_QUALITY', 'PERP_CROWDING', 'PREDICTIVE_ADVERSE_SELECTION', 'SUPERVISOR'] as const;
export type AgentName = typeof agentNames[number];
export type EvidenceState = { terminal: TerminalState | null; wsState: string };
export function sessionCurrent(expected: TerminalState, current: EvidenceState, now = Date.now()) {
  return current.wsState === 'connected' && current.terminal?.process_id === expected.process_id &&
    current.terminal.session_id === expected.session_id && !terminalEnvelopeFailure(current.terminal.emitted_at, now);
}
export function ledgerMatches(data: AccountingLedgerState, t: TerminalState) {
  return data.mode === t.vault.mode && data.market === t.vault.market &&
    data.ledger_version === t.vault.ledger_version && data.ledger_fingerprint === t.vault.ledger_fingerprint;
}
export function ledgerKey(t: TerminalState) {
  const v = t.vault;
  return [t.process_id, t.session_id, v.mode, v.market, v.ledger_version, v.ledger_fingerprint] as const;
}
export function checkedLedger(data: AccountingLedgerState, expected: TerminalState, current: EvidenceState) {
  if (!sessionCurrent(expected, current) || !ledgerMatches(data, expected) || !ledgerMatches(data, current.terminal!))
    throw new Error('Ledger evidence changed during request; waiting for matching terminal evidence.');
  if (data.order !== 'newest-first' || !Array.isArray(data.entries) || data.entries.length > 100 ||
      data.entries.some(e => e.market !== data.market || e.sequence > data.ledger_version))
    throw new Error('Ledger response is incompatible with current evidence.');
  return data;
}
export function checkedAgentEvents(data: unknown, agent?: AgentName, limit = 100): AgentEvent[] {
  if (!Array.isArray(data) || data.length > 250 || data.some(e => !e ||
    !agentNames.includes(e.agent) || typeof e.new_state !== 'string' ||
    (e.previous_state !== null && typeof e.previous_state !== 'string') ||
    !Number.isFinite(Date.parse(e.timestamp)) || !Number.isInteger(e.version) || e.version < 0 ||
    !Array.isArray(e.reasons) || e.reasons.some((r: unknown) => typeof r !== 'string')))
    throw new Error('Agent event response is incompatible with the current contract.');
  return data.filter(e => !agent || e.agent === agent).slice(-Math.min(250, Math.max(1, limit)));
}
// Keep financial strings exact. Percent scaling is display-only and never feeds economics.
export function accountingValue(value: unknown, percent = false) {
  const raw = exactDecimal(value);
  if (raw === '—') return 'Unavailable';
  if (!percent) return raw;
  const negative = raw.startsWith('-');
  const [integer, fraction = ''] = raw.replace(/^[+-]/, '').split('.');
  const digits = integer + fraction.padEnd(2, '0');
  const point = integer.length + 2;
  const whole = digits.slice(0, point).replace(/^0+(?=\d)/, '');
  const rest = digits.slice(point);
  return `${negative ? '-' : ''}${whole}${rest ? '.' + rest : ''}%`;
}
export const evidenceTime = (value: unknown) => typeof value === 'string' && Number.isFinite(Date.parse(value))
  ? `${new Date(value).toLocaleString()} · ${value}` : 'Unavailable from current evidence';
