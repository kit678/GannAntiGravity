const DATAFEED_URL = 'http://localhost:8005';
const HYPOTHESIS_SYMBOL_SEPARATOR = '__HYP__';

export function guessDataSourceForSymbol(symbol) {
  return /^[A-Z0-9]{2,12}USDT$/.test(symbol || '') ? 'binance' : 'yfinance';
}

export function buildHypothesisCandlesUrl(report) {
  if (!report?.symbol || !report?.resolution || !report?.run_id) {
    return '';
  }

  return `${DATAFEED_URL}/api/hypothesis-runs/${encodeURIComponent(report.symbol)}/${encodeURIComponent(report.resolution)}/${encodeURIComponent(report.run_id)}/candles`;
}

export function buildHypothesisSeriesSymbol(symbol, runId) {
  if (!symbol || !runId) {
    return symbol || '';
  }

  return `${stripHypothesisSeriesSymbol(symbol)}${HYPOTHESIS_SYMBOL_SEPARATOR}${runId}`;
}

export function stripHypothesisSeriesSymbol(symbol) {
  if (!symbol) {
    return '';
  }

  const separatorIndex = symbol.indexOf(HYPOTHESIS_SYMBOL_SEPARATOR);
  if (separatorIndex === -1) {
    return symbol;
  }

  return symbol.slice(0, separatorIndex);
}

export function normalizeHypothesisRunCandle(candle) {
  const rawTime = candle?.time ?? candle?.timestamp ?? null;
  const time = typeof rawTime === 'number' && rawTime < 1e12 ? rawTime * 1000 : rawTime;

  return {
    time,
    open: candle?.open,
    high: candle?.high,
    low: candle?.low,
    close: candle?.close,
    volume: candle?.volume ?? 0,
    bar_index: candle?.bar_index ?? candle?.barIndex ?? null,
  };
}

export function buildHypothesisCandleLookup(candles) {
  const byBarIndex = new Map();

  for (const candle of candles || []) {
    const barIndex = candle?.bar_index ?? candle?.barIndex;
    if (!Number.isFinite(barIndex)) {
      continue;
    }
    byBarIndex.set(barIndex, candle);
  }

  return {
    getByBarIndex(barIndex) {
      if (!Number.isFinite(barIndex)) {
        return null;
      }
      return byBarIndex.get(barIndex) ?? null;
    },
  };
}

export function buildLoadedHypothesisReportInfo(report) {
  if (!report?.path) {
    return null;
  }

  const pathParts = String(report.path).split('/');
  const fileName = pathParts[pathParts.length - 1] || report.path;
  const modified = Number(report.modified);
  const generatedAtLabel = Number.isFinite(modified) && modified > 0
    ? new Date(modified * 1000).toLocaleString()
    : '-';

  return {
    fileName,
    generatedAtLabel,
  };
}
