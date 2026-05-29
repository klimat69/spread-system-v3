import type { ChartTradeMarker } from "./paperAnalytics";

export function TradeMarkerShape(props: { cx?: number; cy?: number; payload?: ChartTradeMarker }) {
  const { cx, cy, payload } = props;
  if (cx == null || cy == null || !payload) return null;
  const up = payload.side === "buy";
  const color = payload.kind === "entry" ? (up ? "#4ade80" : "#f87171") : up ? "#86efac" : "#fca5a5";
  const size = payload.kind === "entry" ? 7 : 6;
  const points = up
    ? `${cx},${cy - size} ${cx - size},${cy + size} ${cx + size},${cy + size}`
    : `${cx},${cy + size} ${cx - size},${cy - size} ${cx + size},${cy - size}`;
  return (
    <g>
      <polygon points={points} fill={color} stroke="#0f172a" strokeWidth={1} />
    </g>
  );
}
