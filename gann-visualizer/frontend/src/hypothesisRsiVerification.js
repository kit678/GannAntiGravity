const formatRiskMultiple = (value) => {
  if (!Number.isFinite(value)) {
    return '-';
  }

  return `${value}R`;
};

const interpolateLineValue = (event, barIndex) => {
  const startBar = event?.line_start_bar_index;
  const endBar = event?.line_end_bar_index;
  const startRsi = event?.line_start_rsi;
  const endRsi = event?.line_end_rsi;

  if (!Number.isFinite(startBar) || !Number.isFinite(endBar)
      || !Number.isFinite(startRsi) || !Number.isFinite(endRsi)
      || !Number.isFinite(barIndex)) {
    return null;
  }

  if (startBar === endBar) {
    return endRsi;
  }

  const slope = (endRsi - startRsi) / (endBar - startBar);
  return startRsi + slope * (barIndex - startBar);
};

const resolveLineValue = (event, point) => {
  if (Number.isFinite(point?.line_value)) {
    return point.line_value;
  }

  return interpolateLineValue(event, point?.bar_index);
};

const isRsiTrendlineBreakEvent = (event) => {
  if (!event) return false;
  const type = String(event.event_type || event.type || '');
  if (type.startsWith('RSI_TRENDLINE_BREAK_')) return true;
  if (Array.isArray(event.rsi_window) && event.rsi_window.length > 0) return true;
  if (event.rsi_window_bars != null) return true;
  return false;
};

const buildMinimalModel = (event) => ({
  windowPoints: [],
  breakPoint: {
    barIndex: event.bar_index ?? event.break_bar_index ?? null,
    rsi: event.rsi_value ?? null,
    lineValue: event.line_value_at_break ?? null,
  },
  line: {
    startBarIndex: event.line_start_bar_index ?? null,
    endBarIndex: event.line_end_bar_index ?? null,
    startRsi: event.line_start_rsi ?? null,
    endRsi: event.line_end_rsi ?? null,
  },
  pivots: {
    pivotABarIndex: event.pivot_a_bar_index ?? null,
    pivotBBarIndex: event.pivot_b_bar_index ?? null,
  },
  summary: {
    side: event.entry_side || event.direction || '-',
    trendFilter: event.trend_filter_passed === null || event.trend_filter_passed === undefined
      ? '-'
      : (event.trend_filter_passed ? 'PASS' : 'FAIL'),
    bestRLabel: formatRiskMultiple(event.best_r),
    stopPrice: event.stop_price ?? null,
    tradeResult: event.outcome || event.status || '-',
  },
  isMinimal: true,
});

export function buildRsiVerificationModel(event) {
  if (!event) return null;
  if (!isRsiTrendlineBreakEvent(event)) return null;

  if (!Array.isArray(event.rsi_window) || event.rsi_window.length === 0) {
    if (typeof console !== 'undefined' && console.warn) {
      console.warn(
        '[RSI Verification] rsi_window is empty for event',
        event.event_id ?? event.event_type ?? event,
        '— showing minimal summary only.',
      );
    }
    return buildMinimalModel(event);
  }

  return {
    windowPoints: event.rsi_window.map((point) => ({
      barIndex: point.bar_index,
      rsi: point.rsi,
      lineValue: resolveLineValue(event, point),
    })),
    breakPoint: {
      barIndex: event.bar_index ?? event.break_bar_index ?? null,
      rsi: event.rsi_value ?? null,
      lineValue: event.line_value_at_break ?? null,
    },
    line: {
      startBarIndex: event.line_start_bar_index ?? null,
      endBarIndex: event.line_end_bar_index ?? null,
      startRsi: event.line_start_rsi ?? null,
      endRsi: event.line_end_rsi ?? null,
    },
    pivots: {
      pivotABarIndex: event.pivot_a_bar_index ?? null,
      pivotBBarIndex: event.pivot_b_bar_index ?? null,
    },
    summary: {
      side: event.entry_side || event.direction || '-',
      trendFilter: event.trend_filter_passed === null || event.trend_filter_passed === undefined
        ? '-'
        : (event.trend_filter_passed ? 'PASS' : 'FAIL'),
      bestRLabel: formatRiskMultiple(event.best_r),
      stopPrice: event.stop_price ?? null,
      tradeResult: event.outcome || event.status || '-',
    },
    isMinimal: false,
  };
}

/**
 * Segments whose validity window contains `barIndex`.
 *
 * The backend guarantees at most one active line per direction at any bar, so
 * this returns at most two segments. Filtering by a recorded validity window is
 * what stops the display and the trade signal from diverging - the frontend no
 * longer infers which line was live.
 */
export function selectLiveSegments(timeline, barIndex) {
  if (!Array.isArray(timeline) || !Number.isFinite(Number(barIndex))) return [];
  const bar = Number(barIndex);
  return timeline.filter((segment) => {
    const from = Number(segment?.valid_from_bar);
    const to = Number(segment?.valid_to_bar);
    if (!Number.isFinite(from) || !Number.isFinite(to)) return false;
    return from <= bar && bar <= to;
  });
}
