const DEFAULT_RANGE_WIDTH_SEC = 240 * 60;
const RSI_EVENT_RANGE_WIDTH_SEC = 3 * 24 * 60 * 60; // 3 days — wide enough to show RSI curve + multiple trendlines in context

function isRsiEvent(event) {
  if (!event) {
    return false;
  }

  const type = String(event.event_type || event.type || '');
  if (type.startsWith('RSI_TRENDLINE_BREAK_')) {
    return true;
  }

  return Array.isArray(event.rsi_window) && event.rsi_window.length > 0;
}

function resolveEventTimeSec(event) {
  if (typeof event?.timestamp === 'number' && !Number.isNaN(event.timestamp)) {
    return event.timestamp < 2000000000 ? event.timestamp : Math.floor(event.timestamp / 1000);
  }

  if (event?.time && typeof event.time === 'string') {
    const parsed = new Date(event.time.replace(/,/g, '')).getTime();
    if (!Number.isNaN(parsed)) {
      return Math.floor(parsed / 1000);
    }
  }

  return Math.floor(Date.now() / 1000);
}

function resolveFanOriginTimeSec(event) {
  let originTime = event?.fan_geometry?.origin?.time;
  if ((originTime == null || originTime <= 0) && event?.fan_geometry?.rays?.[0]?.points?.[0]?.time) {
    originTime = event.fan_geometry.rays[0].points[0].time;
  }
  return typeof originTime === 'number' && originTime > 0 ? originTime : null;
}

export function buildHypothesisVisibleRange({ event, visibleRange }) {
  const eventTimeSec = resolveEventTimeSec(event);
  const rsiEvent = isRsiEvent(event);
  const fanOriginTimeSec = resolveFanOriginTimeSec(event);

  let rangeWidth = rsiEvent ? RSI_EVENT_RANGE_WIDTH_SEC : DEFAULT_RANGE_WIDTH_SEC;
  if (!rsiEvent && visibleRange && visibleRange.to - visibleRange.from > 0) {
    rangeWidth = visibleRange.to - visibleRange.from;
  }

  const centerTimeSec = rsiEvent
    ? eventTimeSec
    : fanOriginTimeSec ?? eventTimeSec;

  return {
    from: centerTimeSec - rangeWidth / 2,
    to: centerTimeSec + rangeWidth / 2,
    centerTimeSec,
    rangeWidth,
  };
}

export function shouldApplyRunCandleVisibleRange({ hasSelectedEvent }) {
  return !hasSelectedEvent;
}

export function shouldDeferHypothesisNavigation({ hasCustomData, isLoadingRunCandles }) {
  return isLoadingRunCandles && !hasCustomData;
}

export function shouldLoadHypothesisRunCandles({
  requestedRunPath,
  loadedRunPath,
  hasCustomData,
  isCustomMode,
  isLoadingRunCandles,
}) {
  if (!requestedRunPath || isLoadingRunCandles) {
    return false;
  }

  if (!isCustomMode || !hasCustomData) {
    return true;
  }

  return requestedRunPath !== loadedRunPath;
}
