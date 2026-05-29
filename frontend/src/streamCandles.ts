export type MidTick = { t: string; ts: number; mid: number };

export type StreamCandle = {
  t: string;
  ts: number;
  o: number;
  h: number;
  l: number;
  c: number;
};

export function midTicksToCandles(ticks: MidTick[], bucketSec: number): StreamCandle[] {
  if (ticks.length === 0 || bucketSec < 1) return [];
  const bucketMs = bucketSec * 1000;
  const buckets = new Map<number, StreamCandle>();

  for (const tick of ticks) {
    const key = Math.floor(tick.ts / bucketMs) * bucketMs;
    const existing = buckets.get(key);
    if (!existing) {
      buckets.set(key, {
        ts: key,
        t: new Date(key).toLocaleTimeString("ru-RU"),
        o: tick.mid,
        h: tick.mid,
        l: tick.mid,
        c: tick.mid
      });
      continue;
    }
    existing.h = Math.max(existing.h, tick.mid);
    existing.l = Math.min(existing.l, tick.mid);
    existing.c = tick.mid;
  }

  return [...buckets.values()].sort((a, b) => a.ts - b.ts).slice(-120);
}
