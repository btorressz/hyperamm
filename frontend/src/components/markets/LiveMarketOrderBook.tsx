import type { LiveStreamSnapshot } from '../../types';
import { livePrice, liveSize, bps } from '../../utils/format';
import { Panel, Empty } from '../TerminalPrimitives';
export function LiveMarketOrderBook({book,decimals,current,age}:{book:LiveStreamSnapshot['order_book'];decimals:number|null;current:boolean;age:number|null}) {
  function rows(side:'bids'|'asks'){
    let total=0;
    const levels=(book?.[side]??[]).map((level,i)=>{total+=Number(level.size);return {level,total,i};});
    return (side==='asks'?levels.reverse():levels).map(({level,total,i})=><tr className={current?(side==='asks'?'liveAsk':'liveBid'):'liveHistorical'} key={`${side}-${i}`}>
      <td>{livePrice(level.price)}</td><td>{liveSize(level.size,decimals)}</td><td>{liveSize(total,decimals)}</td>
    </tr>);
  }
  return <Panel title="Native L2 order book" meta={current?'FRESH SOURCE OBSERVATION':'STALE — LAST OBSERVED'}>
    {book?<>
      <div className="tableWrap liveBook" role="region" aria-label="Live native book levels" tabIndex={0}><table>
        <thead><tr><th scope="col">Price</th><th scope="col">Size (base)</th><th scope="col">Cumulative (base)</th></tr></thead>
        <tbody>{rows('asks')}<tr className="liveMid"><td colSpan={3}>Mid {livePrice(book.midpoint)} · spread {livePrice(book.spread)} / {bps(book.spread_bps)}</td></tr>{rows('bids')}</tbody>
      </table></div>
      <p className="muted panelNote">Best bid {livePrice(book.best_bid)} · best ask {livePrice(book.best_ask)}</p>
      <dl className="liveDetails"><dt>Source</dt><dd>{book.source}</dd><dt>L2 exchange time</dt><dd>{book.source_timestamp}</dd>
        <dt>Source age</dt><dd>{age===null?'Uncertain':`${age.toFixed(1)}s`}</dd><dt>Depth truncated</dt><dd>{book.truncated?'Yes · actual retained levels only':'No'}</dd>
      </dl>
    </>:<Empty>No actual native L2 levels available.</Empty>}
  </Panel>;
}
