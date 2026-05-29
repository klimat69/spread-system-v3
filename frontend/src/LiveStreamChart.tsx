import { useMemo } from "react";
import { ComposedChart, Line, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from "recharts";
import type { ChartTradeMarker } from "./paperAnalytics";
import { midTicksToCandles, type MidTick } from "./streamCandles";
import { TradeMarkerShape } from "./tradeMarkerShape";
import { ru } from "./ru";

export function LiveStreamChart({
  ticks,
  bucketSec,
  markers
}: {
  ticks: MidTick[];
  bucketSec: 1 | 5;
  markers: ChartTradeMarker[];
}) {
  const candles = useMemo(() => midTicksToCandles(ticks, bucketSec), [ticks, bucketSec]);
  const title = bucketSec === 1 ? ru.chartStream1s : ru.chartStream5s;

  if (candles.length < 2) {
    return (
      <div className="stream-chart-empty">
        <p>{title}</p>
        <p className="hint">{ru.chartStreamWarming}</p>
      </div>
    );
  }

  return (
    <div className="stream-chart">
      <p className="stream-chart-title">{title}</p>
      <ResponsiveContainer width="100%" height={252}>
        <ComposedChart data={candles}>
          <XAxis dataKey="t" tick={{ fontSize: 10 }} minTickGap={28} />
          <YAxis domain={["auto", "auto"]} width={62} tick={{ fontSize: 10 }} />
          <Tooltip
            formatter={(value) => Number(value).toFixed(2)}
            labelFormatter={(label) => `${label}`}
          />
          <Line type="monotone" dataKey="c" stroke="#60a5fa" strokeWidth={2} dot={false} isAnimationActive={false} />
          <Scatter data={markers} dataKey="price" shape={<TradeMarkerShape />} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
