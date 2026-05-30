import { buildPaperTradeRows, sessionPaperStats } from "./paperAnalytics";
import { ru } from "./ru";
import type { DryRunOrder } from "./types";

const money = new Intl.NumberFormat("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 4 });
const pct = new Intl.NumberFormat("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 3 });

function formatTime(iso: string): string {
  const ms = Date.parse(iso);
  if (!Number.isFinite(ms)) return iso;
  return new Date(ms).toLocaleTimeString("ru-RU");
}

function pnlClass(value: number | null): string {
  if (value == null || value === 0) return "";
  return value > 0 ? "pnl-pos" : "pnl-neg";
}

export function PaperAnalyticsPanel({ orders }: { orders: DryRunOrder[] }) {
  const rows = buildPaperTradeRows(orders);
  const stats = sessionPaperStats(rows);

  return (
    <section className="paper-analytics">
      <h3>{ru.paperAnalytics}</h3>
      <p className="hint">{ru.paperAnalyticsHint}</p>
      <div className="paper-stats">
        <span>
          {ru.paperSessionPnl}:{" "}
          <strong className={pnlClass(stats.totalPnl)}>{money.format(stats.totalPnl)} USDT</strong>
        </span>
        <span>
          {ru.paperClosed}: {stats.closedCount} · {ru.paperWins}: {stats.wins} · {ru.paperLosses}: {stats.losses}
          {stats.breakeven > 0 ? ` · ${ru.paperBreakeven}: ${stats.breakeven}` : ""}
          {stats.openCount > 0 ? ` · ${ru.paperOpen}: ${stats.openCount}` : ""}
        </span>
      </div>
      <p className="hint">{ru.paperStatsHint}</p>
      {rows.length === 0 ? (
        <p className="hint">{ru.noPaperTrades}</p>
      ) : (
        <div className="paper-table-wrap">
          <table className="paper-table">
            <thead>
              <tr>
                <th>{ru.paperColTime}</th>
                <th>{ru.paperColSide}</th>
                <th>{ru.paperColEntry}</th>
                <th>{ru.paperColExit}</th>
                <th>{ru.paperColPnl}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>{formatTime(row.openedAt)}</td>
                  <td className={row.side === "buy" ? "side-buy" : "side-sell"}>{row.side.toUpperCase()}</td>
                  <td>{row.entry.toFixed(2)}</td>
                  <td>{row.exit != null ? row.exit.toFixed(2) : "—"}</td>
                  <td className={pnlClass(row.pnl)}>
                    {row.pnl != null ? (
                      <>
                        {money.format(row.pnl)}
                        {row.pnlPct != null ? <small> ({pct.format(row.pnlPct)}%)</small> : null}
                      </>
                    ) : (
                      ru.paperOpen
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {rows.length > 0 ? (
        <p className="hint">
          {ru.paperTableCount}: {rows.length}
          {stats.closedCount > 0 ? ` (${ru.paperLosses}: ${stats.losses})` : ""}
        </p>
      ) : null}
      <p className="chart-legend-hint">{ru.botChartLegend}</p>
    </section>
  );
}
