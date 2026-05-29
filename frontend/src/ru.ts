export const ru = {
  loading: "Загрузка терминала MEXC… Первый запуск может занять до 60 секунд.",
  title: "Spread System v3 · Терминал MEXC",
  wsConnected: "WS подключён",
  wsDisconnected: "WS отключён",
  feed: "Поток",
  autoTrade: "Автоторговля",
  start: "Старт",
  stop: "Стоп",
  markets: "Рынки",
  marketType: "Тип рынка",
  spot: "Спот",
  swap: "Фьючерсы (бессрочные)",
  searchPair: "Поиск пары (BTC, ETH, XAUT…)",
  popular: "Популярные на MEXC",
  allPairs: "Все пары",
  syncHint: "Список синхронизирован с MEXC через API биржи.",
  goldFutures: "GOLD Futures (MEXC)",
  goldFuturesHint:
    "Бессрочный контракт GOLD(XAUT)USDT на MEXC — стакан и лента подключаются к XAUT_USDT (как на сайте биржи).",
  goldFuturesUsdcHint:
    "Во фьючерсах MEXC нет GOLD/USDC — выберите GOLD Futures ниже (USDT) или спот GOLD(XAUT)/USDC.",
  realtimeMetrics: "Метрики в реальном времени",
  liveBroadcast: "Трансляция (TradingView)",
  openOnMexc: "Открыть на MEXC",
  bestBid: "Лучший bid",
  bestAsk: "Лучший ask",
  spread: "Спред",
  imbalance: "Дисбаланс",
  mode: "Режим",
  auto: "Авто",
  blocked: "Блокировка",
  none: "нет",
  orderBook: "Стакан",
  asks: "Продажи",
  bids: "Покупки",
  liveTrades: "Лента сделок",
  settingsConnection: "Подключение MEXC",
  apiKey: "API Key",
  apiSecret: "API Secret",
  apiPassword: "API Password",
  tradingMode: "Режим торговли",
  paper: "Paper (симуляция)",
  live: "Live (реальные ордера)",
  enableLiveOrders: "Разрешить live-ордера",
  orderSize: "Размер ордера (базовая монета)",
  saveConfig: "Сохранить настройки",
  saving: "Сохранение…",
  scalp: "Скальп (simple_scalp)",
  spreadMin: "Мин. спред",
  imbalanceMin: "Мин. дисбаланс",
  aggressionMin: "Мин. агрессия ленты",
  staleOrderSec: "Отмена устаревшего ордера (сек)",
  replaceMoveBps: "Перестановка при сдвиге (bps)",
  strategy: "Стратегия",
  maxHoldingSec: "Макс. удержание (сек)",
  maxOpenOrders: "Макс. открытых ордеров",
  entryCooldownSec: "Пауза между входами (сек)",
  imbalanceExit: "Выход по дисбалансу",
  tapeAggressionEntry: "Порог агрессии входа",
  marketStaleSec: "Устаревание стакана (сек)",
  risk: "Риск",
  maxDailyLoss: "Макс. дневной убыток",
  maxPositionSize: "Макс. размер позиции",
  maxInventory: "Макс. экспозиция",
  cooldownAfterLoss: "Пауза после убытка (сек)",
  paperAnalytics: "Аналитика Paper",
  paperAnalyticsHint: "Вход, выход и P/L по симуляции (не сделки на MEXC).",
  noPaperTrades: "Пока нет сделок — включите Старт и автоторговлю.",
  paperSessionPnl: "Сессия",
  paperClosed: "закрыто",
  paperWins: "в плюс",
  paperLosses: "в минус",
  paperOpen: "открыта",
  paperColTime: "Время",
  paperColSide: "Сторона",
  paperColEntry: "Вход",
  paperColExit: "Выход",
  paperColPnl: "P/L",
  botChartLegend: "На графике выше: ▲ buy · ▼ sell (яркие — вход, бледные — выход)",
  botMetricsHint: "Линия — mid стакана MEXC; маркеры — входы и выходы бота (Paper).",
  feedOk: "OK",
  feedUnhealthy: "Проблема",
  feedWarming: "прогрев ленты",
  feedRecovering: "Восстановление",
  feedDelayed: "Задержка",
  feedDesync: "Рассинхрон",
  updateBanner: "Обновление",
  checkUpdates: "Проверить обновления",
  updateReadyRestart: "Перезапустить",
  updateDismiss: "Скрыть",
  chartInterval: "График (обзор)",
  chart1s: "1 сек",
  chart5s: "5 сек",
  chart1m: "1 мин",
  chartHint:
    "График TradingView — только обзор: у него своя задержка, это не поток бота. Торговля идёт по стакану и ленте справа.",
  feedLatency: "Задержка потока MEXC → экран",
  whySilent: "Почему бот молчит",
  whySilentHint: "Проверьте по порядку:",
  whySilentStart: "Нажмите «Старт» (не только автоторговлю).",
  whySilentAuto: "Включите «Автоторговля».",
  whySilentFeed: "Дождитесь «Поток: OK» и цен bid/ask ≠ 0.",
  whySilentDemo: "Paper-сделки — в таблице «Аналитика Paper» справа, не на бирже MEXC.",
  demoRelaxed: "Мягкие сигналы (демо)"
} as const;

export interface UpdaterStatusPayload {
  state: "checking" | "available" | "downloading" | "ready" | "idle" | "error";
  version?: string;
  currentVersion?: string;
  percent?: number;
  message?: string;
}

export function feedStatusRu(status: string): string {
  const key = status.toUpperCase();
  if (key === "OK") return ru.feedOk;
  if (key === "UNHEALTHY") return ru.feedUnhealthy;
  if (key === "RECOVERING") return ru.feedRecovering;
  if (key === "DELAYED") return ru.feedDelayed;
  if (key === "DESYNC") return ru.feedDesync;
  return status;
}

const feedReasonLabels: Record<string, string> = {
  tape_not_ready: "нет сделок с MEXC",
  tape_warming_up: "ожидание ленты сделок",
  sequence_warming_up: "ожидание версии стакана с MEXC",
  orderbook_not_ready: "стакан не готов",
  sequence_not_available: "нет номера версии стакана",
  orderbook_stale: "стакан устарел",
  tape_stale: "лента сделок устарела",
  websocket_silent: "нет данных по WebSocket MEXC",
  websocket_tls_verification_failed_using_insecure_fallback: "TLS MEXC, повторное подключение",
  connecting_websocket: "подключение к MEXC",
  websocket_synchronized: "поток синхронизирован"
};

export function feedReasonRu(reason: string): string {
  const key = reason.split(":")[0];
  return feedReasonLabels[key] ?? reason.replaceAll("_", " ");
}

const blockedReasonLabels: Record<string, string> = {
  auto_trade_disabled: "автоторговля выключена",
  market_data_unhealthy: "поток MEXC не готов",
  live_validation_required: "нужна проверка биржи для live",
  invalid_order_book: "пустой стакан",
  stale_order_book: "стакан устарел",
  volatility_too_high: "слишком высокая волатильность",
  liquidity_insufficient: "мало ликвидности",
  tape_insufficient: "мало сделок в ленте",
  orderflow_not_aligned: "сигналы стакана и ленты не совпали",
  resistance_wall_blocks_long: "стена продавцов мешает покупке",
  support_wall_blocks_short: "стена покупателей мешает продаже",
  reconciliation_blocked: "блокировка сверки",
  max_open_orders_reached: "слишком много открытых ордеров"
};

export function blockedReasonRu(reason: string | null | undefined): string {
  if (!reason) return ru.none;
  if (reason.startsWith("market_data_unhealthy:")) {
    const sub = reason.split(":", 2)[1] ?? "";
    return `${blockedReasonLabels.market_data_unhealthy}: ${feedReasonRu(sub)}`;
  }
  const key = reason.split(":")[0];
  return blockedReasonLabels[key] ?? reason.replaceAll("_", " ");
}
