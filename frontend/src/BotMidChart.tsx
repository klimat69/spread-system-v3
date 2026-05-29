import { ComposedChart, Line, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from "recharts";
import type { ChartTradeMarker } from "./paperAnalytics";
import { TradeMarkerShape } from "./tradeMarkerShape";

type MidPoint = { t: string; mid: number };

export function BotMidChart({ data, markers }: { data: MidPoint[]; markers: ChartTradeMarker[] }) {
  return (
    <ResponsiveContainer width="100%" height={180}>
      <ComposedChart data={data}>
        <XAxis dataKey="t" hide />
        <YAxis domain={["auto", "auto"]} width={60} tick={{ fontSize: 11 }} />
        <Tooltip
          formatter={(value, _name, item) => {
            const row = item?.payload as ChartTradeMarker | MidPoint | undefined;
            if (row && "kind" in row) {
              const label = row.kind === "entry" ? "Вход" : "Выход";
              return [`${Number(value).toFixed(4)} (${label} ${row.side.toUpperCase()})`, "Цена"];
            }
            return [Number(value).toFixed(4), "Mid"];
          }}
        />
        <Line type="monotone" dataKey="mid" stroke="#60a5fa" strokeWidth={2} dot={false} isAnimationActive={false} />
        <Scatter data={markers} dataKey="price" shape={<TradeMarkerShape />} isAnimationActive={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
