import type { TerminalState, Quote } from "../types";
export function authorizationLineage(t: TerminalState, q: Quote) {
  const final = t.authorized_quotes.find(x => x.side === q.side && x.level_index === q.level_index);
  const auth = t.risk_authorization;
  if (!auth.authorized || !final) return { status: "SUPPRESSED / NOT AUTHORIZED" };
  if (auth.authorized_quote_count !== t.authorized_quotes.length ||
      !auth.quote_fingerprint || !auth.authorization_fingerprint)
    return { status: "INCONSISTENT / UNAVAILABLE LINEAGE" };
  return { status: "AUTHORIZED", final, ladder: auth.quote_fingerprint, envelope: auth.authorization_fingerprint };
}
