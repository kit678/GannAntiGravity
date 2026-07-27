const toNumberOrNull = (value) => {
  if (value == null || value === '') {
    return null;
  }

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const toBooleanOrNull = (value) => {
  if (value == null || value === '') {
    return null;
  }

  if (typeof value === 'boolean') {
    return value;
  }

  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase();
    if (normalized === 'true') {
      return true;
    }
    if (normalized === 'false') {
      return false;
    }
  }

  return Boolean(value);
};

const parseTimestamp = (value) => {
  if (Number.isFinite(value) && value > 0) {
    return value;
  }

  if (typeof value !== 'string' || value.trim() === '') {
    return null;
  }

  const parsed = new Date(value.replace(/,/g, '')).getTime();
  return Number.isFinite(parsed) ? Math.floor(parsed / 1000) : null;
};

const formatHypothesisDatetime = (timestamp, timeString) => {
  if (timeString) {
    return timeString;
  }

  if (!Number.isFinite(timestamp)) {
    return '-';
  }

  return new Date(timestamp * 1000).toISOString();
};

const normalizeRsiWindowPoint = (point) => ({
  ...point,
  bar_index: toNumberOrNull(point?.bar_index ?? point?.barIndex),
  rsi: toNumberOrNull(point?.rsi ?? point?.rsi_value ?? point?.value),
  line_value: toNumberOrNull(point?.line_value ?? point?.lineValue),
});

export function normalizeHypothesisEvent(event, index = 0) {
  const timeString = event?.time || event?.datetime || '';
  const timestampSource = Number.isFinite(event?.timestamp) && event.timestamp > 0
    ? event.timestamp
    : timeString;
  const timestamp = parseTimestamp(timestampSource);
  const smaValue = toNumberOrNull(event?.sma_200 ?? event?.sma200 ?? event?.sma_value);

  return {
    ...event,
    event_id: event?.event_id ?? index + 1,
    event_type: event?.event_type || event?.type || '-',
    event_type_display: event?.event_type_display || event?.event_type || event?.type || '-',
    datetime: formatHypothesisDatetime(timestamp, timeString),
    timestamp,
    fan_display: event?.fan_display || event?.fan || event?.fan_identity || 'Unknown',
    price: toNumberOrNull(event?.price ?? event?.target_price),
    mfe: toNumberOrNull(event?.mfe ?? event?.mfe_10),
    mae: toNumberOrNull(event?.mae ?? event?.mae_10),
    outcome: event?.outcome || event?.status || null,
    fan_geometry: event?.fan_geometry || null,
    rsi_value: toNumberOrNull(event?.rsi_value),
    sma_200: smaValue,
    sma_value: smaValue,
    trend_filter_passed: toBooleanOrNull(event?.trend_filter_passed),
    pivot_a_bar_index: toNumberOrNull(event?.pivot_a_bar_index),
    pivot_a_rsi: toNumberOrNull(event?.pivot_a_rsi),
    pivot_a_kind: event?.pivot_a_kind || null,
    pivot_a_time: event?.pivot_a_time || null,
    pivot_b_bar_index: toNumberOrNull(event?.pivot_b_bar_index),
    pivot_b_rsi: toNumberOrNull(event?.pivot_b_rsi),
    pivot_b_kind: event?.pivot_b_kind || null,
    pivot_b_time: event?.pivot_b_time || null,
    break_bar_index: toNumberOrNull(event?.break_bar_index ?? event?.bar_index),
    line_start_bar_index: toNumberOrNull(event?.line_start_bar_index),
    line_end_bar_index: toNumberOrNull(event?.line_end_bar_index),
    line_start_rsi: toNumberOrNull(event?.line_start_rsi),
    line_end_rsi: toNumberOrNull(event?.line_end_rsi),
    line_value_at_break: toNumberOrNull(event?.line_value_at_break),
    best_r: toNumberOrNull(event?.best_r),
    stop_price: toNumberOrNull(event?.stop_price),
    entry_price: toNumberOrNull(event?.entry_price),
    exit_price: toNumberOrNull(event?.exit_price),
    entry_side: event?.entry_side || event?.direction || null,
    rsi_window: Array.isArray(event?.rsi_window) ? event.rsi_window.map(normalizeRsiWindowPoint) : [],
  };
}

const formatNumber = (value, digits = 2) => {
  if (value == null || value === '' || Number.isNaN(Number(value))) {
    return '-';
  }
  return Number(value).toFixed(digits);
};

export const FAN_COLUMNS = [
  { key: 'fan', label: 'Fan' },
  { key: 'fraction', label: 'Frac' },
  { key: 'target', label: 'Target' },
  { key: 'price', label: 'Price' },
  { key: 'breach', label: 'Breach' },
  { key: 'outcome', label: 'Outcome' },
  { key: 'mfe', label: 'MFE' },
  { key: 'mae', label: 'MAE' },
];

export const RSI_COLUMNS = [
  { key: 'direction', label: 'Dir' },
  { key: 'entry', label: 'Entry' },
  { key: 'stop', label: 'Stop' },
  { key: 'r_multiple', label: 'R' },
  { key: 'rsi', label: 'RSI' },
  { key: 'sma', label: 'SMA' },
  { key: 'outcome', label: 'Outcome' },
  { key: 'exit_reason', label: 'Exit' },
  { key: 'net_pnl', label: 'PnL' },
];

const isRsiEvent = (event) => {
  if (!event) return false;
  const type = String(event.event_type || event.type || '');
  if (type.startsWith('RSI_TRENDLINE_BREAK_')) return true;
  if (Array.isArray(event.rsi_window) && event.rsi_window.length > 0) return true;
  if (event.rsi_window_bars != null) return true;
  return false;
};

const renderRsiRow = (event, column) => {
  switch (column.key) {
    case 'direction':
      return event.entry_side || event.direction || '-';
    case 'entry':
      return formatNumber(event.entry_price ?? event.price);
    case 'stop':
      return formatNumber(event.stop_price);
    case 'r_multiple': {
      if (event.best_r != null) return `${formatNumber(event.best_r, 2)}R`;
      return '-';
    }
    case 'rsi':
      return formatNumber(event.rsi_value);
    case 'sma':
      return formatNumber(event.sma_200 ?? event.sma_value);
    case 'outcome':
      if (event.outcome) return event.outcome;
      if (event.status) return String(event.status).replace(/_/g, ' ');
      return '-';
    case 'exit_reason':
      return event.exit_reason || '-';
    case 'net_pnl':
      return formatNumber(event.net_pnl);
    default:
      return '-';
  }
};

const renderFanRow = (event, column) => {
  switch (column.key) {
    case 'fan':
      return event.fan_display || event.fan || 'Unknown';
    case 'fraction':
      return event.fraction != null ? event.fraction : '-';
    case 'target':
      return event.next_angle != null ? event.next_angle : '-';
    case 'price':
      return formatNumber(event.price);
    case 'breach': {
      if (!event.breach_time) return '-';
      const dir = event.breach_direction ? ` ${String(event.breach_direction).toUpperCase()}` : '';
      const frac = event.breach_fraction ? ` @${event.breach_fraction}` : '';
      const px = event.breach_price != null ? ` ${formatNumber(event.breach_price)}` : '';
      return `${event.breach_time}${dir}${frac}${px}`;
    }
    case 'outcome':
      if (event.outcome) return event.outcome;
      if (event.status) return String(event.status).replace(/_/g, ' ');
      return '-';
    case 'mfe':
      return formatNumber(event.mfe);
    case 'mae':
      return formatNumber(event.mae);
    default:
      return '-';
  }
};

export function getEventTableColumns(event) {
  if (isRsiEvent(event)) {
    return RSI_COLUMNS.map((col) => ({
      ...col,
      render: (evt) => renderRsiRow(evt, col),
    }));
  }
  return FAN_COLUMNS.map((col) => ({
    ...col,
    render: (evt) => renderFanRow(evt, col),
  }));
}

export function isRsiTrendlineBreakEvent(event) {
  return isRsiEvent(event);
}

export function normalizeHypothesisEvents(events) {
  return Array.isArray(events) ? events.map(normalizeHypothesisEvent) : [];
}
