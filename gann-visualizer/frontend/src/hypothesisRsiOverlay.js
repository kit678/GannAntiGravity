import { buildHypothesisCandleLookup } from './hypothesisRunContext.js';

const toNumberOrNull = (value) => {
  if (value == null || value === '') {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

function buildChartPoint(candle, lineValue, rsi = null) {
  if (!candle || !Number.isFinite(candle.time)) {
    return null;
  }

  const time = candle.time / 1000;
  if (!Number.isFinite(time) || time <= 0) {
    return null;
  }

  const point = {
    barIndex: candle.bar_index ?? candle.barIndex ?? null,
    time,
    lineValue: toNumberOrNull(lineValue),
  };

  const normalizedRsi = toNumberOrNull(rsi);
  if (normalizedRsi != null) {
    point.rsi = normalizedRsi;
  }

  return point;
}

export function buildHypothesisRsiOverlayModel(event, candles) {
  if (!event || !Array.isArray(candles) || candles.length === 0) {
    return null;
  }

  const candleLookup = buildHypothesisCandleLookup(candles);
  const getCandle = (barIndex) => candleLookup.getByBarIndex(toNumberOrNull(barIndex));

  const windowPoints = (Array.isArray(event.rsi_window) ? event.rsi_window : [])
    .map((point) => {
      const candle = getCandle(point?.bar_index);
      if (!candle) {
        return null;
      }
      const chartPoint = buildChartPoint(candle, point?.line_value, point?.rsi);
      if (!chartPoint || !Number.isFinite(chartPoint.rsi)) {
        return null;
      }
      return chartPoint;
    })
    .filter(Boolean);

  const lineStartBarIndex = toNumberOrNull(event.line_start_bar_index);
  const lineEndBarIndex = toNumberOrNull(event.line_end_bar_index);
  const breakBarIndex = toNumberOrNull(event.bar_index ?? event.break_bar_index);

  const lineStartPoint = Number.isFinite(lineStartBarIndex)
    ? buildChartPoint(getCandle(lineStartBarIndex), event.line_start_rsi)
    : null;
  const lineEndPoint = Number.isFinite(lineEndBarIndex)
    ? buildChartPoint(getCandle(lineEndBarIndex), event.line_end_rsi)
    : null;
  const breakPoint = Number.isFinite(breakBarIndex)
    ? buildChartPoint(getCandle(breakBarIndex), event.line_value_at_break, event.rsi_value)
    : null;

  const trendlinePoints = [lineStartPoint, lineEndPoint, breakPoint]
    .filter((point, index, allPoints) => {
      if (!point || !Number.isFinite(point.lineValue)) {
        return false;
      }
      const previous = allPoints[index - 1];
      return !(previous && previous.barIndex === point.barIndex && previous.lineValue === point.lineValue);
    });

  if (!windowPoints.length && trendlinePoints.length < 2 && !breakPoint) {
    return null;
  }

  return {
    windowPoints,
    trendlinePoints,
    lineStartPoint,
    lineEndPoint,
    breakPoint,
  };
}
