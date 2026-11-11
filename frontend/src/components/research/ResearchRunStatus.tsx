import type { ResearchRunState } from '../../utils/researchStatus';

const messages:Record<Exclude<ResearchRunState,'idle'>,{title:string;detail:string}>={
  running:{title:'Research request submitted',detail:'Awaiting the existing single research worker and validated backend response. Per-frame progress and completion time are not available.'},
  complete:{title:'Research result available',detail:'Validated PAPER research evidence is ready to inspect. It does not authorize orders, live execution or paired-performance claims.'},
  retired:{title:'Previous research evidence retired',detail:'Selected inputs or backend session changed. Submit a new request for current evidence; do not reuse previous financial displays.'},
  error:{title:'Research request not completed',detail:'See the diagnostic guidance below. The browser cannot determine whether a disconnected backend worker has stopped.'},
};

export function ResearchRunStatus({state,operation}:{state:ResearchRunState;operation:'Historical replay'|'Scenario comparison'}){
  if(state==='idle')return null;
  const {title,detail}=messages[state];
  return <section className={'researchRunStatus researchState-'+state} role="status" aria-live="polite" aria-label={operation+' research state'}>
    <div className="researchRunHead"><strong>{operation} · {title}</strong><span>{state==='running'?'AWAITING BACKEND':state.toUpperCase()}</span></div>
    <p>{detail}</p>
  </section>;
}
