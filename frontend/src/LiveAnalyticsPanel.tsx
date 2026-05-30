import { buildLiveOrderRows, sessionLiveStats } from "./liveAnalytics";
import { ru } from "./ru";
import type { BotFill, BotOrder } from "./types";

const money = new Intl.NumberFormat("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 4 });
const sizeFmt = new Intl.NumberFormat("ru-RU", { minimumFractionDigits: 4, maximumFractionDigits: 6 });

function formatTime(iso: string): string {
  const ms = Date.parse(iso);
  if (!Number.isFinite(ms)) return iso;
  return new Date(ms).toLocaleTimeString("ru-RU");
}

export function LiveAnalyticsPanel({ orders, fills }: { orders: BotOrder[]; fills: BotFill[] }) {
  const rows = buildLiveOrderRows(orders);
  const stats = sessionLiveStats(orders, fills);

  return (
    <section className="paper-analytics">
      <h3>{ru.liveAnalytics}</h3>
      <p className="hint">{ru.liveAnalyticsHint}</p>
      <div className="paper-stats">
        <span>
          {ru.liveOrdersTotal}: {stats.orderCount}
          {stats.open > 0 ? ` · ${ru.liveOrdersOpen}: ${stats.open}` : ""}
          {stats.filled > 0 ? ` · ${ru.liveOrdersFilled}: ${stats.filled}` : ""}
          {stats.cancelled > 0 ? ` · ${ru.liveOrdersCancelled}: ${stats.cancelled}` : ""}
        </span>
        {stats.fillCount > 0 ? (
          <span>
            {ru.liveFillsTotal}: {stats.fillCount} · {ru.liveFees}:{" "}
            <strong>{money.format(stats.totalFees)}</strong>
          </span>
        ) : null}
      </div>
      {rows.length === 0 ? (
        <p className="hint">{ru.noLiveOrders}</p>
      ) : (
        <div className="paper-table-wrap">
          <table className="paper-table">
            <thead>
              <tr>
                <th>{ru.paperColTime}</th>
                <th>{ru.paperColSide}</th>
                <th>{ru.liveColPrice}</th>
                <th>{ru.liveColSize}</th>
                <th>{ru.liveColStatus}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>{formatTime(row.time)}</td>
                  <td className={row.side === "buy" ? "side-buy" : "side-sell"}>{row.side.toUpperCase()}</td>
                  <td>{row.price != null ? row.price.toFixed(2) : "—"}</td>
                  <td>
                    {sizeFmt.format(row.filled > 0 ? row.filled : row.size)}
                    {row.filled > 0 && row.filled < row.size ? (
                      <small> / {sizeFmt.format(row.size)}</small>
                    ) : null}
                  </td>
                  <td>{row.statusLabel}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {rows.length > 0 ? (
        <p className="hint">
          {ru.liveTableCount}: {rows.length}
        </p>
      ) : null}
    </section>
  );
}
