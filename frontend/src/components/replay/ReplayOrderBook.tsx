import type { ReplayFrame, ReplayLevel } from '../../types/replay';
import { livePrice, liveSize } from '../../utils/format';
import { Panel, Empty } from '../TerminalPrimitives';
export function ReplayOrderBook({frame}:{frame:ReplayFrame|null}) {
  const observation=frame?.book_observation;
  const book=observation?.order_book;
  const side=(levels:ReplayLevel[],reverse:boolean)=>(reverse?[...levels].reverse():levels).map((level,i)=><tr key={i}>
    <td>{livePrice(level.price)}</td><td>{liveSize(level.size,6)}</td><td>{level.order_count}</td></tr>);
  return <Panel title="Historical L2 order book" meta="RETAINED EVIDENCE · NOT LIVE">
    {!book?<Empty>No historical L2 snapshot selected.</Empty>:<>
      <div className="tableWrap replayBook" tabIndex={0} role="region" aria-label="Historical retained L2 book">
        <table><thead><tr><th>Price (quote)</th><th>Size (base)</th><th>Orders</th></tr></thead>
          <tbody><tr><th colSpan={3}>Asks</th></tr>{side(book.asks,true)}
            <tr><th colSpan={3}>Bids</th></tr>{side(book.bids,false)}</tbody></table>
      </div>
      <dl className="replayDetails">
        <div><dt>Book receipt</dt><dd>{observation?.received_at}</dd></div>
        <div><dt>Source time</dt><dd>{observation?.source_timestamp ?? 'Unknown'}</dd></div>
        <div><dt>Verified L2 time label</dt><dd>{observation?.source_event_time_verified?'Recorded native assertion':'No'}</dd></div>
        <div><dt>Observer / generation</dt><dd>{observation?.observer_instance_id} / {observation?.connection_generation}</dd></div>
        <div><dt>Depth truncated</dt><dd>{book.truncated?'Yes':'No'}</dd></div>
      </dl>
    </>}
    <p className="muted panelNote">Retained snapshots do not prove trades between observations, queue priority or executable passive liquidity.</p>
  </Panel>;
}
