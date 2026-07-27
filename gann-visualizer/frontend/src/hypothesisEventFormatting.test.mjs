import assert from 'node:assert/strict';

import {
  normalizeHypothesisEvent,
  normalizeHypothesisEvents,
  getEventTableColumns,
  isRsiTrendlineBreakEvent,
  FAN_COLUMNS,
  RSI_COLUMNS,
} from './hypothesisEventFormatting.js';

const normalized = normalizeHypothesisEvent(
  {
    type: 'RSI_TRENDLINE_BREAK_LONG',
    time: '2026-07-10T10:15:00',
    timestamp: 1783678500,
    outcome: 'WIN',
    rsi_value: '52.4',
    sma_value: '103455.1',
    trend_filter_passed: 'true',
    pivot_a_bar_index: '88',
    pivot_b_bar_index: '96',
    line_value_at_break: '48.7',
    best_r: '2.5',
    stop_price: '104325.5',
    rsi_window: [
      { bar_index: '92', rsi: '44.1', line_value: '45.0' },
      { bar_index: '93', rsi: '45.6', line_value: '46.2' },
      { bar_index: '94', rsi: '52.4', line_value: '48.7' },
    ],
  },
  0,
);

assert.equal(normalized.event_id, 1);
assert.equal(normalized.event_type, 'RSI_TRENDLINE_BREAK_LONG');
assert.equal(normalized.datetime, '2026-07-10T10:15:00');
assert.equal(normalized.timestamp, 1783678500);
assert.equal(normalized.rsi_value, 52.4);
assert.equal(normalized.sma_200, 103455.1);
assert.equal(normalized.sma_value, 103455.1);
assert.equal(normalized.trend_filter_passed, true);
assert.equal(normalized.pivot_a_bar_index, 88);
assert.equal(normalized.pivot_b_bar_index, 96);
assert.equal(normalized.line_value_at_break, 48.7);
assert.equal(normalized.best_r, 2.5);
assert.equal(normalized.stop_price, 104325.5);
assert.equal(normalized.rsi_window.length, 3);
assert.deepEqual(
  normalized.rsi_window.map((point) => ({
    barIndex: point.bar_index,
    rsi: point.rsi,
    lineValue: point.line_value,
  })),
  [
    { barIndex: 92, rsi: 44.1, lineValue: 45.0 },
    { barIndex: 93, rsi: 45.6, lineValue: 46.2 },
    { barIndex: 94, rsi: 52.4, lineValue: 48.7 },
  ],
);

const fromStringTime = normalizeHypothesisEvent(
  {
    type: 'RSI_TRENDLINE_BREAK_LONG',
    time: '2026-07-10T10:15:00',
  },
  0,
);
const expectedStringTs = Math.floor(new Date('2026-07-10T10:15:00').getTime() / 1000);
assert.equal(fromStringTime.timestamp, expectedStringTs);
assert.equal(typeof fromStringTime.timestamp, 'number');
assert.equal(fromStringTime.entry_side, null);

const zeroTimestampFallsBack = normalizeHypothesisEvent(
  {
    type: 'RSI_TRENDLINE_BREAK_LONG',
    time: '2026-07-02T11:00:00',
    timestamp: 0,
  },
  1,
);
const expectedZeroFallbackTs = Math.floor(new Date('2026-07-02T11:00:00').getTime() / 1000);
assert.equal(
  zeroTimestampFallsBack.timestamp,
  expectedZeroFallbackTs,
  'non-positive timestamps should fall back to the event time string so chart focus does not jump to Unix zero',
);

const normalizedBatch = normalizeHypothesisEvents([
  {
    type: 'RSI_TRENDLINE_BREAK_SHORT',
    time: '2026-07-02T08:00:00',
    entry_price: '60285.5',
    stop_price: '60113.5',
    rsi_value: '46.855',
    line_value_at_break: '41.117',
    break_bar_index: '224',
    line_start_bar_index: '207',
    line_end_bar_index: '212',
    rsi_window: [
      { bar_index: '223', rsi: '45.1', line_value: '41.0' },
      { bar_index: '224', rsi: '46.9', line_value: '41.1' },
    ],
  },
]);
assert.equal(normalizedBatch.length, 1);
assert.equal(normalizedBatch[0].entry_price, 60285.5);
assert.equal(normalizedBatch[0].stop_price, 60113.5);
assert.equal(normalizedBatch[0].rsi_value, 46.855);
assert.equal(normalizedBatch[0].line_value_at_break, 41.117);
assert.equal(normalizedBatch[0].break_bar_index, 224);
assert.equal(normalizedBatch[0].line_start_bar_index, 207);
assert.equal(normalizedBatch[0].line_end_bar_index, 212);
assert.deepEqual(
  normalizedBatch[0].rsi_window.map((point) => ({
    barIndex: point.bar_index,
    rsi: point.rsi,
    lineValue: point.line_value,
  })),
  [
    { barIndex: 223, rsi: 45.1, lineValue: 41.0 },
    { barIndex: 224, rsi: 46.9, lineValue: 41.1 },
  ],
  'batch normalization should preserve numeric RSI event fields used by the chart renderer',
);

// --- getEventTableColumns tests ---

// 1. RSI events (event_type starts with RSI_TRENDLINE_BREAK_) get RSI columns
const rsiCols = getEventTableColumns({
  event_type: 'RSI_TRENDLINE_BREAK_LONG',
  entry_price: 100,
  stop_price: 95,
  best_r: 1.5,
  rsi_value: 55,
  sma_200: 99,
  outcome: 'WIN',
  exit_reason: 'target',
  net_pnl: 12.5,
  direction: 'LONG',
});
assert.equal(rsiCols.length, RSI_COLUMNS.length);
assert.deepEqual(
  rsiCols.map((c) => c.key),
  RSI_COLUMNS.map((c) => c.key),
);
for (const col of rsiCols) {
  assert.equal(typeof col.render, 'function');
}
assert.equal(rsiCols.find((c) => c.key === 'entry').render({ entry_price: 100 }), '100.00');
assert.equal(rsiCols.find((c) => c.key === 'stop').render({ stop_price: 95 }), '95.00');
assert.equal(rsiCols.find((c) => c.key === 'r_multiple').render({ best_r: 2 }), '2.00R');
assert.equal(rsiCols.find((c) => c.key === 'rsi').render({ rsi_value: 50.123 }), '50.12');
assert.equal(rsiCols.find((c) => c.key === 'sma').render({ sma_200: 200 }), '200.00');
assert.equal(rsiCols.find((c) => c.key === 'outcome').render({ outcome: 'WIN' }), 'WIN');
assert.equal(rsiCols.find((c) => c.key === 'outcome').render({ status: 'ACCEPTED' }), 'ACCEPTED');
assert.equal(rsiCols.find((c) => c.key === 'exit_reason').render({ exit_reason: 'stop' }), 'stop');
assert.equal(rsiCols.find((c) => c.key === 'net_pnl').render({ net_pnl: 7.5 }), '7.50');
assert.equal(rsiCols.find((c) => c.key === 'direction').render({ direction: 'SHORT' }), 'SHORT');
assert.equal(rsiCols.find((c) => c.key === 'r_multiple').render({ best_r: null }), '-');
assert.equal(rsiCols.find((c) => c.key === 'net_pnl').render({}), '-');

// 2. Non-RSI events without rsi_window get fan columns
const fanCols = getEventTableColumns({
  event_type: 'TARGET_PROGRESSION_WIN',
  fan_display: 'P1',
  fraction: 0.5,
  next_angle: 0.625,
  price: 123.45,
  outcome: 'WIN',
  mfe: 5,
  mae: -2,
});
assert.equal(fanCols.length, FAN_COLUMNS.length);
assert.deepEqual(
  fanCols.map((c) => c.key),
  FAN_COLUMNS.map((c) => c.key),
);
for (const col of fanCols) {
  assert.equal(typeof col.render, 'function');
}
assert.equal(fanCols.find((c) => c.key === 'fan').render({ fan_display: 'P1' }), 'P1');
assert.equal(fanCols.find((c) => c.key === 'fan').render({}), 'Unknown');
assert.equal(fanCols.find((c) => c.key === 'fraction').render({ fraction: 0.5 }), 0.5);
assert.equal(fanCols.find((c) => c.key === 'fraction').render({}), '-');
assert.equal(fanCols.find((c) => c.key === 'target').render({ next_angle: 0.625 }), 0.625);
assert.equal(fanCols.find((c) => c.key === 'price').render({ price: 50 }), '50.00');
assert.equal(fanCols.find((c) => c.key === 'mfe').render({ mfe: 3.2 }), '3.20');
assert.equal(fanCols.find((c) => c.key === 'breach').render({}), '-');
assert.equal(
  fanCols.find((c) => c.key === 'breach').render({
    breach_time: '2026-07-10T10:00:00',
    breach_direction: 'up',
    breach_fraction: 0.5,
    breach_price: 100,
  }),
  '2026-07-10T10:00:00 UP @0.5 100.00',
);

// 3. isRsiTrendlineBreakEvent returns true for RSI_TRENDLINE_BREAK_* types
assert.equal(isRsiTrendlineBreakEvent({ event_type: 'RSI_TRENDLINE_BREAK_LONG' }), true);
assert.equal(isRsiTrendlineBreakEvent({ type: 'RSI_TRENDLINE_BREAK_SHORT' }), true);
// 4. and for events with rsi_window populated
assert.equal(isRsiTrendlineBreakEvent({ event_type: 'OTHER', rsi_window: [{ bar_index: 0, rsi: 50 }] }), true);
assert.equal(isRsiTrendlineBreakEvent({ rsi_window_bars: 40 }), true);
// 5. but false for plain events
assert.equal(isRsiTrendlineBreakEvent({ event_type: 'TARGET_PROGRESSION_WIN' }), false);
assert.equal(isRsiTrendlineBreakEvent({}), false);
assert.equal(isRsiTrendlineBreakEvent(null), false);
// 6. Empty rsi_window array does NOT count as RSI event
assert.equal(isRsiTrendlineBreakEvent({ event_type: 'OTHER', rsi_window: [] }), false);

console.log('hypothesisEventFormatting.test.mjs: ok');
