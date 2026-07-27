import assert from 'node:assert/strict';

import { normalizeHypothesisEvent } from './hypothesisEventFormatting.js';
import { selectLiveSegments, buildRsiVerificationModel } from './hypothesisRsiVerification.js';

const event = normalizeHypothesisEvent(
  {
    type: 'RSI_TRENDLINE_BREAK_SHORT',
    time: '2026-07-10T10:15:00',
    timestamp: 1783678500,
    outcome: 'WIN',
    direction: 'SHORT',
    rsi_value: 52.4,
    sma_value: 103455.1,
    trend_filter_passed: true,
    pivot_a_bar_index: 88,
    pivot_b_bar_index: 96,
    bar_index: 94,
    line_start_bar_index: 88,
    line_start_rsi: 50.0,
    line_end_bar_index: 96,
    line_end_rsi: 42.0,
    line_value_at_break: 48.7,
    best_r: null,
    stop_price: 104325.5,
    entry_price: 104100.25,
    exit_price: 103400.25,
    rsi_window: [
      { bar_index: 92, rsi: 44.1 },
      { bar_index: 93, rsi: 45.6 },
      { bar_index: 94, rsi: 52.4 },
    ],
  },
  0,
);

const model = buildRsiVerificationModel(event);

assert.ok(model);
assert.deepEqual(
  model.windowPoints.map((point) => ({
    barIndex: point.barIndex,
    rsi: point.rsi,
    lineValue: point.lineValue,
  })),
  [
    { barIndex: 92, rsi: 44.1, lineValue: 46.0 },
    { barIndex: 93, rsi: 45.6, lineValue: 45.0 },
    { barIndex: 94, rsi: 52.4, lineValue: 44.0 },
  ],
);
assert.deepEqual(model.breakPoint, {
  barIndex: 94,
  rsi: 52.4,
  lineValue: 48.7,
});
assert.deepEqual(model.line, {
  startBarIndex: 88,
  endBarIndex: 96,
  startRsi: 50.0,
  endRsi: 42.0,
});
assert.deepEqual(model.pivots, {
  pivotABarIndex: 88,
  pivotBBarIndex: 96,
});
assert.equal(model.summary.side, 'SHORT');
assert.equal(model.summary.trendFilter, 'PASS');
assert.equal(model.summary.bestRLabel, '-');
assert.equal(model.summary.stopPrice, 104325.5);
assert.equal(model.summary.tradeResult, 'WIN');

const withExplicitLineValues = buildRsiVerificationModel(
  normalizeHypothesisEvent(
    {
      type: 'RSI_TRENDLINE_BREAK_LONG',
      time: '2026-07-10T10:15:00',
      timestamp: 1783678500,
      direction: 'LONG',
      bar_index: 94,
      rsi_value: 52.4,
      line_start_bar_index: 88,
      line_start_rsi: 40.0,
      line_end_bar_index: 96,
      line_end_rsi: 70.0,
      line_value_at_break: 48.7,
      rsi_window: [
        { bar_index: 92, rsi: 44.1, line_value: 44.0 },
        { bar_index: 93, rsi: 45.6, line_value: 46.0 },
        { bar_index: 94, rsi: 52.4, line_value: 48.0 },
      ],
    },
    0,
  ),
);

assert.deepEqual(
  withExplicitLineValues.windowPoints.map((point) => ({
    barIndex: point.barIndex,
    lineValue: point.lineValue,
  })),
  [
    { barIndex: 92, lineValue: 44.0 },
    { barIndex: 93, lineValue: 46.0 },
    { barIndex: 94, lineValue: 48.0 },
  ],
);

assert.equal(buildRsiVerificationModel({ rsi_window: [] }), null);
assert.equal(buildRsiVerificationModel(null), null);

// Minimal model is returned for RSI events with an empty rsi_window
const originalWarn = console.warn;
let warnCalls = 0;
console.warn = () => { warnCalls += 1; };
try {
    const minimalModel = buildRsiVerificationModel({
        event_type: 'RSI_TRENDLINE_BREAK_LONG',
        direction: 'LONG',
        break_bar_index: 100,
        rsi_value: 55,
        line_value_at_break: 50,
        best_r: 1.5,
        stop_price: 95,
        outcome: 'WIN',
        trend_filter_passed: true,
        rsi_window: [],
    });
    assert.ok(minimalModel, 'expected a minimal model for empty rsi_window');
    assert.equal(minimalModel.isMinimal, true);
    assert.equal(minimalModel.windowPoints.length, 0);
    assert.deepEqual(minimalModel.breakPoint, { barIndex: 100, rsi: 55, lineValue: 50 });
    assert.deepEqual(minimalModel.line, {
        startBarIndex: null,
        endBarIndex: null,
        startRsi: null,
        endRsi: null,
    });
    assert.deepEqual(minimalModel.pivots, {
        pivotABarIndex: null,
        pivotBBarIndex: null,
    });
    assert.equal(minimalModel.summary.side, 'LONG');
    assert.equal(minimalModel.summary.trendFilter, 'PASS');
    assert.equal(minimalModel.summary.bestRLabel, '1.5R');
    assert.equal(minimalModel.summary.stopPrice, 95);
    assert.equal(minimalModel.summary.tradeResult, 'WIN');
    assert.ok(warnCalls >= 1, 'expected console.warn to be called when rsi_window is empty');
} finally {
    console.warn = originalWarn;
}

console.log('hypothesisRsiVerification.test.mjs: ok');


// Mirrors the backend's half-open handoff: a re_anchored segment ends at
// (successor.valid_from_bar - 1), so no bar ever has two live down-lines.
const TIMELINE = [
  { segment_id: 1, direction: 'down', valid_from_bar: 10, valid_to_bar: 39, end_reason: 're_anchored' },
  { segment_id: 2, direction: 'down', valid_from_bar: 40, valid_to_bar: 90, end_reason: 'broken' },
  { segment_id: 3, direction: 'up',   valid_from_bar: 20, valid_to_bar: 95, end_reason: 'broken' },
  { segment_id: 4, direction: 'down', valid_from_bar: 95, valid_to_bar: 130, end_reason: 'end_of_data' },
];

{
  const live = selectLiveSegments(TIMELINE, 50);
  assert.deepEqual(live.map((s) => s.segment_id).sort(), [2, 3]);
}

{
  // at most one line per direction, always
  for (const bar of [0, 10, 25, 40, 60, 90, 95, 120, 200]) {
    const live = selectLiveSegments(TIMELINE, bar);
    for (const direction of ['up', 'down']) {
      const count = live.filter((s) => s.direction === direction).length;
      assert.ok(count <= 1, `bar ${bar} had ${count} ${direction} lines`);
    }
  }
}

{
  assert.deepEqual(selectLiveSegments(null, 50), []);
  assert.deepEqual(selectLiveSegments(TIMELINE, null), []);
}

console.log('hypothesisRsiVerification.test.mjs: selectLiveSegments ok');
