import type { MarketType, SymbolListResponse, SymbolMeta } from "./types";

export function quoteFromSymbol(symbol: string): string {
  const pair = symbol.split(":")[0];
  return (pair.split("/")[1] ?? "USDT").toUpperCase();
}

export function displaySymbol(symbol: string, catalog: SymbolListResponse | null): string {
  return catalog?.symbols_meta?.[symbol]?.display ?? symbol.split(":")[0].replace("/", "");
}

export function mexcPlatformUrl(symbol: string, marketType: MarketType, catalog: SymbolListResponse | null): string {
  if (catalog?.symbols_meta?.[symbol]?.mexc_url) {
    return catalog.symbols_meta[symbol].mexc_url;
  }
  const contract = symbol.split(":")[0].replace("/", "_").toUpperCase();
  return marketType === "swap"
    ? `https://www.mexc.com/ru-RU/futures/${contract}`
    : `https://www.mexc.com/ru-RU/exchange/${contract}`;
}

export function tradingViewEmbedUrl(symbol: string, marketType: MarketType, catalog: SymbolListResponse | null): string {
  const tv = catalog?.symbols_meta?.[symbol]?.tradingview ?? fallbackTradingView(symbol, marketType);
  return `https://s.tradingview.com/widgetembed/?frameElementId=tv_mexc_realtime&symbol=${encodeURIComponent(tv)}&interval=1&hidesidetoolbar=1&symboledit=0&saveimage=0&toolbarbg=f1f3f6&theme=dark&style=1&timezone=Etc%2FUTC&withdateranges=0&studies=[]&hideideas=1`;
}

function fallbackTradingView(symbol: string, marketType: MarketType): string {
  const pair = symbol.split(":")[0];
  const base = pair.split("/")[0].toUpperCase();
  const quote = (pair.split("/")[1] ?? "USDT").toUpperCase();
  const tvBase = base.includes("XAUT") || base.includes("GOLD") ? "XAUT" : base.replace(/[^A-Z0-9]/gi, "");
  const ticker = `${tvBase}${quote}`;
  return marketType === "swap" ? `MEXC:${ticker}.P` : `MEXC:${ticker}`;
}

export function parseLocaleNumber(value: string, fallback: number): number {
  const normalized = value.trim().replace(",", ".");
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
    return symbol.toLowerCase().includes(q) || display.includes(q);
  });
}

export function symbolNote(symbol: string, catalog: SymbolListResponse | null): string {
  return catalog?.symbols_meta?.[symbol]?.note ?? "";
}

export type { SymbolMeta };
