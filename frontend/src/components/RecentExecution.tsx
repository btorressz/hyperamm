import type { TerminalState, Order } from "../types";
import { Panel } from "./TerminalPrimitives";
import { timestamp, price, quantity } from "../utils/format";
export function OrderTable({
  orders,
  t,
}: {
  orders: Order[];
  t: TerminalState;
}) {
  return (
    <div className="tableWrap">
      <table>
        <thead>
          <tr>
            <th>Time</th>
            <th>Side</th>
            <th className="numeric">Price</th>
            <th className="numeric">Size</th>
            <th className="numeric">Filled</th>
            <th>Source / status</th>
            <th>Reconciliation</th>
          </tr>
        </thead>
        <tbody>
          {orders.length ? (
            orders.map((o) => (
              <tr key={o.client_order_id}>
                <td>{timestamp(o.updated_at)}</td>
                <td className={o.side === "BID" ? "bidText" : "askText"}>
                  {o.side}
                </td>
                <td className="numeric">{price(o.price)}</td>
                <td className="numeric">{quantity(o.size)}</td>
                <td className="numeric">{quantity(o.filled_size)}</td>
                <td>
                  {o.fill_source ?? t.strategy.config.execution_mode} ·{" "}
                  {o.status}
                </td>
                <td>
                  {t.reconciliation.find(
                    (a) => a.existing?.client_order_id === o.client_order_id,
                  )?.action ?? "No current action"}
                </td>
              </tr>
            ))
          ) : (
            <tr>
              <td className="emptyCell" colSpan={7}>
                No order evidence yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
export function RecentExecution({ t }: { t: TerminalState }) {
  return (
    <Panel
      title="Recent execution"
      meta={`${t.strategy.config.execution_mode} · bounded lifecycle records`}
    >
      <OrderTable
        t={t}
        orders={[...t.orders]
          .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at))
          .slice(0, 6)}
      />
    </Panel>
  );
}
