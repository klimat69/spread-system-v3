import type { DryRunOrder } from "./types";

export interface PaperTradeRow {
  id: string;
  openedAt: string;
  closedAt: string | null;
  side: "buy" | "sell";
  entry: number;
  exit: number | null;
  size: number;
  pnl: number | null;
  pnlPct: number | null;
  status: "open" | "closed";
}

export interface ChartTradeMarker {
  t: string;
  price: number;
  kind: "entry" | "exit";
  side: "buy" | "sell";
}

export function formatChartTime(iso: string): string {
  const ms = Date.parse(iso);
  if (!Number.isFinite(ms)) return iso;
  return new Date(ms).toLocaleTimeString("ru-RU");
}

export function paperPnl(side: "buy" | "sell", entry: number, exit: number, size: number): number {
  const delta = side === "buy" ? exit - entry : entry - exit;
  return delta * size;
}

export function buildPaperTradeRows(orders: DryRunOrder[]): PaperTradeRow[] {
  return [...orders]
    .reverse()
    .map((order) => {
      const closed = order.status === "CLOSED";
      const exit = order.exit_price ?? null;
      const pnl = closed && exit != null ? paperPnl(order.side, order.price, exit, order.size) : null;
      const pnlPct =
        closed && exit != null && order.price > 0
          ? (order.side === "buy" ? (exit - order.price) / order.price : (order.price - exit) / order.price) * 100
          : null;
      return {
        id: order.id,
        openedAt: order.timestamp,
        closedAt: order.closed_at ?? null,
        side: order.side,
        entry: order.price,
        exit,
        size: order.size,
        pnl,
        pnlPct,
        status: closed ? "closed" : "open"
      };
    });
}

export function buildChartMarkers(orders: DryRunOrder[]): ChartTradeMarker[] {
  const markers: ChartTradeMarker[] = [];
  for (const order of orders) {
    markers.push({
      t: formatChartTime(order.timestamp),
      price: order.price,
      kind: "entry",
      side: order.side
    });
    if (order.status === "CLOSED" && order.exit_price != null) {
      const exitTs = order.closed_at ?? order.timestamp;
      const exitSide: "buy" | "sell" = order.side === "buy" ? "sell" : "buy";
      markers.push({
        t: formatChartTime(exitTs),
        price: order.exit_price,
        kind: "exit",
        side: exitSide
      });
    }
  }
  return markers;
}

export function sessionPaperStats(rows: PaperTradeRow[]) {
  const closed = rows.filter((row) => row.status === "closed" && row.pnl != null);
  const totalPnl = closed.reduce((sum, row) => sum + (row.pnl ?? 0), 0);
  const wins = closed.filter((row) => (row.pnl ?? 0) > 0).length;
  const losses = closed.filter((row) => (row.pnl ?? 0) < 0).length;
  return { totalPnl, wins, losses, closedCount: closed.length, openCount: rows.filter((row) => row.status === "open").length };
}
