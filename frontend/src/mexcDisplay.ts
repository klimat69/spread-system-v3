import type { MarketType, SymbolListResponse, SymbolMeta } from "./types";

export function quoteFromSymbol(symbol: string): string {
  const pair = symbol.split(":")[0];
  return (pair.split("/")[1] ?? "USDT").toUpperCase();
}

function baseQuote(symbol: string): { base: string; quote: string } {
  const pair = symbol.split(":")[0];
  if (!pair.includes("/")) return { base: pair.toUpperCase(), quote: "USDT" };
  const [base, quote] = pair.split("/", 2);
  return { base: base.toUpperCase(), quote: quote.toUpperCase() };
}

export function isGoldOrXaut(symbol: string): boolean {
  const { base } = baseQuote(symbol);
  return base.includes("XAUT") || base.includes("GOLD");
}

/** MEXC futures contract id for WebSocket/URLs (XAUT_USDT, BTC_USDT). */
export function mexcFuturesContractId(symbol: string): string {
  const { base, quote } = baseQuote(symbol);
  if (isGoldOrXaut(symbol)) return `XAUT_${quote === "USDC" ? "USDT" : quote}`;
  return `${base}_${quote}`;
}

export function displaySymbol(symbol: string, catalog: SymbolListResponse | null): string {
  const meta = catalog?.symbols_meta?.[symbol];
  if (meta?.display) return meta.display;
  const { base, quote } = baseQuote(symbol);
  if (isGoldOrXaut(symbol) && catalog?.market_type === "swap") {
    return `GOLD(XAUT)${quote}`;
  }
  return symbol.split(":")[0].replace("/", "");
}

export function mexcPlatformUrl(symbol: string, marketType: MarketType, catalog: SymbolListResponse | null): string {
  if (catalog?.symbols_meta?.[symbol]?.mexc_url) {
    return catalog.symbols_meta[symbol].mexc_url;
  }
  const contract = marketType === "swap" ? mexcFuturesContractId(symbol) : symbol.split(":")[0].replace("/", "_").toUpperCase();
  return marketType === "swap"
    ? `https://www.mexc.com/ru-RU/futures/${contract}`
    : `https://www.mexc.com/ru-RU/exchange/${contract}`;
}

export type ChartInterval = "1S" | "5S" | "1";

export function tradingViewEmbedUrl(
  symbol: string,
  marketType: MarketType,
  catalog: SymbolListResponse | null,
  interval: ChartInterval = "1S"
): string {
  const tv = catalog?.symbols_meta?.[symbol]?.tradingview ?? fallbackTradingView(symbol, marketType);
  return `https://s.tradingview.com/widgetembed/?frameElementId=tv_mexc_realtime&symbol=${encodeURIComponent(tv)}&interval=${interval}&hidesidetoolbar=1&symboledit=0&saveimage=0&toolbarbg=f1f3f6&theme=dark&style=1&timezone=Etc%2FUTC&withdateranges=0&studies=[]&hideideas=1`;
}

function fallbackTradingView(symbol: string, marketType: MarketType): string {
  const { base, quote } = baseQuote(symbol);
  const tvBase = isGoldOrXaut(symbol) ? "XAUT" : base.replace(/[^A-Z0-9]/gi, "");
  const tvQuote = marketType === "swap" && isGoldOrXaut(symbol) ? "USDT" : quote;
  const ticker = `${tvBase}${tvQuote}`;
  return marketType === "swap" ? `MEXC:${ticker}.P` : `MEXC:${ticker}`;
}

export function resolveGoldFuturesSymbol(catalog: SymbolListResponse | null): string {
  if (catalog?.gold_futures_symbol) return catalog.gold_futures_symbol;
  const usdt = catalog?.symbols_by_quote?.USDT ?? catalog?.symbols ?? [];
  const hit = usdt.find((s) => isGoldOrXaut(s));
  return hit ?? "XAUT/USDT:USDT";
}

export function parseLocaleNumber(value: string, fallback: number): number {
  const normalized = value.trim().replace(",", ".");
  if (normalized === "" || normalized === "." || normalized === "-") return fallback;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function orderedSymbolList(catalog: SymbolListResponse | null, quote: string, search: string): string[] {
  if (!catalog) return [];
  const all = catalog.symbols_by_quote?.[quote] ?? catalog.symbols ?? [];
  const popular = catalog.popular_symbols ?? [];
  const popularSet = new Set(popular);
  const pop = popular.filter((s) => all.includes(s));
  const rest = all.filter((s) => !popularSet.has(s));
  const merged = [...pop, ...rest];
  const q = search.trim().toLowerCase();
  if (!q) return merged;
  return merged.filter((symbol) => {
    const display = catalog.symbols_meta?.[symbol]?.display?.toLowerCase() ?? "";
    return symbol.toLowerCase().includes(q) || display.includes(q) || (q.includes("gold") && isGoldOrXaut(symbol));
  });
}

export function symbolNote(symbol: string, catalog: SymbolListResponse | null): string {
  return catalog?.symbols_meta?.[symbol]?.note ?? "";
}

export type { SymbolMeta };
