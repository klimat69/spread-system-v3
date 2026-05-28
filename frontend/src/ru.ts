export const ru = {
  loading: "Загрузка терминала MEXC…",
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
  goldFuturesHint:
    "GOLD/USDC во фьючерсах на MEXC обычно нет — используйте спот GOLD(XAUT)/USDC или фьючерс XAUT/USDT.",
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
  dryRun: "События Paper (dry-run)",
  noDryRun: "Пока нет симулированных сделок.",
  feedOk: "OK",
  feedUnhealthy: "Проблема",
  feedRecovering: "Восстановление",
  feedDelayed: "Задержка",
  feedDesync: "Рассинхрон",
  updateBanner: "Обновление",
  checkUpdates: "Проверить обновления",
  updateReadyRestart: "Перезапустить",
  updateDismiss: "Скрыть"
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
