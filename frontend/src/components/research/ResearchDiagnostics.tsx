import { diagnoseResearchError } from '../../utils/researchStatus';

export function ResearchDiagnostics({error}:{error:unknown}){
  if(!error)return null;
  const diagnosis=diagnoseResearchError(error);
  return <section className="researchDiagnostic" role="alert" aria-label="Research diagnostics">
    <strong>{diagnosis.title}</strong>
    <p>{diagnosis.action}</p>
    <small>Diagnostic: {diagnosis.kind.toUpperCase()} · local PAPER research only</small>
  </section>;
}
