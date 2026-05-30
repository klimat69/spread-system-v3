import type { BotFill, BotOrder } from "./types";

export interface LiveOrderRow {
  id: number;
  time: string;
  side: "buy" | "sell";
  price: number | null;
  size: number;
  filled: number;
  status: string;
  statusLabel: string;
}

const STATUS_LABELS: Record<string, string> = {
  NEW: "новый",
  SENT: "отправлен",
  OPEN: "на бирже",
  PARTIAL: "частично",
  FILLED: "исполнен",
  CANCELLED: "отменён",
  REJECTED: "отклонён",
  UNKNOWN: "неизвестно"
};

export function liveStatusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

export function applyLiveOrdersSnapshot(existing: BotOrder[], incoming: BotOrder[]): BotOrder[] {
  if (incoming.length === 0) return existing;
  const byId = new Map<number, BotOrder>();
  for (const order of existing) byId.set(order.id, order);
  for (const order of incoming) byId.set(order.id, order);
  return [...byId.values()]
    .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
    .slice(0, 200);
}

export function applyLiveFillsSnapshot(existing: BotFill[], incoming: BotFill[]): BotFill[] {
  if (incoming.length === 0) return existing;
  const byId = new Map<number, BotFill>();
  for (const fill of existing) byId.set(fill.id, fill);
  for (const fill of incoming) byId.set(fill.id, fill);
  return [...byId.values()]
    .sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp))
    .slice(0, 200);
}

export function filterBotOrdersForPair(
  orders: BotOrder[],
  symbol: string,
  marketType: string,
  exchange: string
): BotOrder[] {
  return orders.filter(
    (order) =>
      order.symbol === symbol && order.market_type === marketType && order.exchange === exchange
  );
}

export function filterBotFillsForPair(
  fills: BotFill[],
  symbol: string,
  marketType: string,
  exchange: string
): BotFill[] {
  return fills.filter(
    (fill) => fill.symbol === symbol && fill.market_type === marketType && fill.exchange === exchange
  );
}

export function buildLiveOrderRows(orders: BotOrder[]): LiveOrderRow[] {
  return [...orders]
    .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
    .map((order) => {
      const filled = order.filled_size ?? 0;
      const useAvg = filled > 0 && order.average_price != null;
      return {
        id: order.id,
        time: order.created_at,
        side: order.side as "buy" | "sell",
        price: useAvg ? order.average_price : order.requested_price,
        size: order.requested_size,
        filled,
        status: order.status,
        statusLabel: liveStatusLabel(order.status)
      };
    });
}

export function sessionLiveStats(orders: BotOrder[], fills: BotFill[]) {
  const filled = orders.filter((o) => o.status === "FILLED").length;
  const open = orders.filter((o) => ["NEW", "SENT", "OPEN", "PARTIAL", "UNKNOWN"].includes(o.status)).length;
  const cancelled = orders.filter((o) => o.status === "CANCELLED").length;
  const rejected = orders.filter((o) => o.status === "REJECTED").length;
  const totalFees = fills.reduce((sum, fill) => sum + (fill.fee ?? 0), 0);
  const fillVolume = fills.reduce((sum, fill) => sum + fill.size, 0);
  return {
    orderCount: orders.length,
    filled,
    open,
    cancelled,
    rejected,
    fillCount: fills.length,
    totalFees,
    fillVolume
  };
}
