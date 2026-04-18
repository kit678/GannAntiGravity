// public/indicator/PivotHighLowAngles_v3.js
// v3 – successive‑pivot filtering + automatic 1⁄8‑divisions of the main angle
// -----------------------------------------------------------------------------
//  • Keeps only the most extreme pivot when two consecutive pivots are of the
//    same kind (highest of two highs, lowest of two lows).
//  • Whenever an alternate‑type pivot is confirmed we draw:
//        – The main trend‑angle line between the two pivots (orange)
//        – 5 fractional "Gann"* division angles (7/8, 3/4, 1/2, 1/4, 1/8)
//          colour‑coded and limited to the same radius (time span) as the main
//          line for a tidy fan.
//  • Fully real‑time / bar‑replay safe – runs entirely from `main()` without
//    look‑ahead.
//
//  *We are not implementing the full Gann fan, only the divisions requested.
// -----------------------------------------------------------------------------
function PivotHighLowAngles(PineJS) {
  const DEFAULT_LEFT  = 5;
  const DEFAULT_RIGHT = 5;

  // Fractions are used by the widget-side drawer; indicator only emits events
  const FRACTIONS = [7 / 8, 3 / 4, 1 / 2, 1 / 4, 1 / 8];
  const FRACTION_COLORS = ['#c62828', '#ad1457', '#6a1b9a', '#283593', '#00695c'];

  if (FRACTIONS.length !== FRACTION_COLORS.length) {
    console.error(
      'PivotHighLowAngles Error: FRACTIONS and FRACTION_COLORS arrays must have the same length for consistent subdivision color-coding.'
    );
  }

  const metainfo = {
    _metainfoVersion: 53,
    name: 'Pivot_High_Low_Angles_v3',
    id: 'Pivot_High_Low_Angles_v3@tv-basicstudies-1',
    description: 'Pivot High/Low angles with 1/8 divisions',
    shortDescription: 'Pivot∠‑fan',
    is_price_study: true,
    isCustomIndicator: true,

    plots: [
      { id: 'ph', type: 'shapes' },
      { id: 'pl', type: 'shapes' },
    ],
    styles: {
      ph: {
        title: 'Pivot High', plottype: 'shape_triangle_down', location: 'AboveBar', color: '#e91e63', size: 'Normal',
      },
      pl: {
        title: 'Pivot Low',  plottype: 'shape_triangle_up',   location: 'BelowBar', color: '#2196F3', size: 'Normal',
      },
    },
    inputs: [
      { id: 'leftBars',  name: 'Left Bars',  type: 'integer', defval: DEFAULT_LEFT,  min: 1, max: 100 },
      { id: 'rightBars', name: 'Right Bars', type: 'integer', defval: DEFAULT_RIGHT, min: 1, max: 100 },
    ],
    defaults: {
      styles: {
        ph: { plottype: 'shape_triangle_down', location: 'AboveBar', color: '#e91e63', size: 'Normal' },
        pl: { plottype: 'shape_triangle_up',   location: 'BelowBar', color: '#2196F3', size: 'Normal' },
      },
      inputs: { leftBars: DEFAULT_LEFT, rightBars: DEFAULT_RIGHT },
    },
    format: { type: 'price', precision: 2 },
  };

  return {
    name: 'Pivot_High_Low_Angles_v3',
    metainfo,

    constructor: function () {
      // ────────────────────── runtime state ────────────────────────────────
      this._history = [];               // recent bars – {time,high,low}
      this._lastHighPivot = null;       // {time, price}
      this._lastLowPivot  = null;       // {time, price}
      this._lastPivotType = null;       // 'high' | 'low'

      // Broadcast a pivot fan pair to the widget layer for drawing
      this._emitFan = (from, to) => {
        try {
          if (typeof window !== 'undefined' && window.PivotFanBus && typeof window.PivotFanBus.emitFan === 'function') {
            window.PivotFanBus.emitFan(from, to);
          }
        } catch (e) {
          // Swallow; indicator must never break rendering
          // console.error('PivotFanBus emit failed', e);
        }
      };

      // ─────── lifecycle hooks ────────────────────────────────────────────
      this.init = (context, inputCallback) => {
        this._context = context;
        this._input   = inputCallback;
        // full reset (needed on symbol / interval change)
        this._history = [];
        this._lastHighPivot = null;
        this._lastLowPivot  = null;
        this._lastPivotType = null;
        // shapes remain on chart intentionally (cleared by TradingView when
        // script re‑executes). No explicit purge required.
        return Promise.resolve();
      };

      // ───────────── bar‑by‑bar evaluation ────────────────────────────────
      this.main = (ctx, inputCallback) => {
        this._context = ctx;
        this._input   = inputCallback;

        const left  = Math.max(1, this._input(0));
        const right = Math.max(1, this._input(1));

        // capture bar
        const time = PineJS.Std.time(ctx);
        const high = PineJS.Std.high(ctx);
        const low  = PineJS.Std.low(ctx);
        this._history.push({ time, high, low });
        const maxHist = left + right + 3;
        if (this._history.length > maxHist) this._history.shift();

        let phOut = 0;
        let plOut = 0;

        // candidate pivot index
        if (this._history.length >= left + right + 1) {
          const cIdx = this._history.length - 1 - right;
          const cBar = this._history[cIdx];

          // tests
          const isPH = (() => {
            for (let i = 1; i <= left;  i++) if (this._history[cIdx - i].high >= cBar.high) return false;
            for (let i = 1; i <= right; i++) if (this._history[cIdx + i].high >= cBar.high) return false;
            return true;
          })();

          const isPL = (() => {
            for (let i = 1; i <= left;  i++) if (this._history[cIdx - i].low <= cBar.low)   return false;
            for (let i = 1; i <= right; i++) if (this._history[cIdx + i].low <= cBar.low)   return false;
            return true;
          })();

          // ───── handle confirmed pivots ────────────────────────────────
          if (isPH) {
            const pivot = { time: cBar.time, price: cBar.high };
            console.log('[PivotHighLowAngles] Detected Pivot High at', new Date(pivot.time), 'price', pivot.price);

            // consecutive‑high filter (keep the highest)
            if (this._lastPivotType === 'high') {
              if (pivot.price > this._lastHighPivot.price) {
                console.log('[PivotHighLowAngles] Replacing previous high pivot with higher high');
                this._lastHighPivot = pivot; // replace with newer / higher high
              }
            } else { // alternate type – complete pair
              if (this._lastLowPivot) {
                console.log('[PivotHighLowAngles] Emitting fan from low pivot to new high pivot');
                this._emitFan(this._lastLowPivot, pivot);
              }
              this._lastHighPivot = pivot;
              this._lastPivotType = 'high';
            }

            phOut = { value: 1, offset: -right };
          }

          if (isPL) {
            const pivot = { time: cBar.time, price: cBar.low };
            console.log('[PivotHighLowAngles] Detected Pivot Low at', new Date(pivot.time), 'price', pivot.price);

            // consecutive‑low filter (keep the lowest)
            if (this._lastPivotType === 'low') {
              if (pivot.price < this._lastLowPivot.price) {
                console.log('[PivotHighLowAngles] Replacing previous low pivot with lower low');
                this._lastLowPivot = pivot; // replace with newer / lower low
              }
            } else { // alternate type – complete pair
              if (this._lastHighPivot) {
                console.log('[PivotHighLowAngles] Emitting fan from high pivot to new low pivot');
                this._emitFan(this._lastHighPivot, pivot);
              }
              this._lastLowPivot = pivot;
              this._lastPivotType = 'low';
            }

            plOut = { value: 1, offset: -right };
          }
        }

        return [phOut, plOut];
      };
    },
  };
}

// Export factory for TradingView
// export default PivotHighLowAngles; // Removed this line
