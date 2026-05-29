import { useMemo } from "react";
import { ComposedChart, Line, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ChartTradeMarker } from "./paperAnalytics";
import { TradeMarkerShape } from "./tradeMarkerShape";

type MidPoint = { t: string; ts: number; mid: number };

export function BotMidChart({ data, markers }: { data: MidPoint[]; markers: ChartTradeMarker[] }) {
  const visibleMarkers = useMemo(() => {
    if (data.length === 0) return [];
    const minTs = data[0].ts;
    const maxTs = data[data.length - 1].ts;
    return markers.filter((marker) => marker.ts >= minTs && marker.ts <= maxTs);
  }, [data, markers]);

  return (
    <ResponsiveContainer width="100%" height={180}>
      <ComposedChart data={data}>
        <XAxis dataKey="ts" type="number" domain={["dataMin", "dataMax"]} hide scale="time" />
        <YAxis domain={["auto", "auto"]} width={60} tick={{ fontSize: 11 }} />
        <Tooltip
          formatter={(value) => Number(value).toFixed(4)}
          labelFormatter={(_label, payload) => {
            const row = payload?.[0]?.payload as MidPoint | undefined;
            return row?.t ?? "";
          }}
        />
        <Line
          type="monotone"
          dataKey="mid"
          stroke="#60a5fa"
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
        />
        {visibleMarkers.map((marker) => (
          <ReferenceDot
            key={`${marker.kind}-${marker.ts}-${marker.side}`}
            x={marker.ts}
            y={marker.price}
            r={0}
            isFront
            shape={(props) => <TradeMarkerShape cx={props.cx} cy={props.cy} payload={marker} />}
          />
        ))}
      </ComposedChart>
    </ResponsiveContainer>
  );
}
