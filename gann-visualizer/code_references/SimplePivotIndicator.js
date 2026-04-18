// SimplePivotIndicator.js
// Custom Pivot High/Low Indicator
// -----------------------------------------------------------------------------
// This indicator detects pivot highs and pivot lows using left/right bar 
// validation. A pivot high is confirmed when the high at bar[i] is greater 
// than the highs of all bars within [i - leftBars, i + rightBars].
// A pivot low is confirmed when the low at bar[i] is less than the lows of 
// all bars within the same range.
//
// Pivot Highs are marked with a DOWN TRIANGLE (▼) above the bar.
// Pivot Lows are marked with an UP TRIANGLE (▲) below the bar.
//
// This uses the same pivot detection logic as the Angular Price Coverage Strategy.
// -----------------------------------------------------------------------------

function SimplePivotIndicator(PineJS) {
    const DEFAULT_LEFT = 5;
    const DEFAULT_RIGHT = 5;

    const metainfo = {
        _metainfoVersion: 53,
        name: 'Simple_Pivot_Indicator',
        id: 'Simple_Pivot_Indicator@tv-basicstudies-1',
        description: 'Simple Pivot High/Low Indicator',
        shortDescription: 'Pivot H/L',
        is_price_study: true,
        isCustomIndicator: true,

        plots: [
            { id: 'ph', type: 'shapes' },
            { id: 'pl', type: 'shapes' },
        ],
        styles: {
            ph: {
                title: 'Pivot High',
                plottype: 'shape_triangle_down',
                location: 'AboveBar',
                color: '#e91e63',
                size: 'Normal',
            },
            pl: {
                title: 'Pivot Low',
                plottype: 'shape_triangle_up',
                location: 'BelowBar',
                color: '#2196F3',
                size: 'Normal',
            },
        },
        inputs: [
            { id: 'leftBars', name: 'Left Bars', type: 'integer', defval: DEFAULT_LEFT, min: 1, max: 100 },
            { id: 'rightBars', name: 'Right Bars', type: 'integer', defval: DEFAULT_RIGHT, min: 1, max: 100 },
        ],
        defaults: {
            styles: {
                ph: { plottype: 'shape_triangle_down', location: 'AboveBar', color: '#e91e63', size: 'Normal' },
                pl: { plottype: 'shape_triangle_up', location: 'BelowBar', color: '#2196F3', size: 'Normal' },
            },
            inputs: { leftBars: DEFAULT_LEFT, rightBars: DEFAULT_RIGHT },
        },
        format: { type: 'price', precision: 2 },
    };

    return {
        name: 'Simple_Pivot_Indicator',
        metainfo,

        constructor: function () {
            // Runtime state - history buffer to store recent bars
            this._history = [];

            // Lifecycle hooks
            this.init = (context, inputCallback) => {
                this._context = context;
                this._input = inputCallback;
                // Reset history on symbol/interval change
                this._history = [];
                return Promise.resolve();
            };

            // Bar-by-bar evaluation
            this.main = (ctx, inputCallback) => {
                this._context = ctx;
                this._input = inputCallback;

                const left = Math.max(1, this._input(0));
                const right = Math.max(1, this._input(1));

                // Capture current bar data
                const time = PineJS.Std.time(ctx);
                const high = PineJS.Std.high(ctx);
                const low = PineJS.Std.low(ctx);
                this._history.push({ time, high, low });

                // Keep only the necessary bars in history
                const maxHist = left + right + 3;
                if (this._history.length > maxHist) {
                    this._history.shift();
                }

                let phOut = 0;
                let plOut = 0;

                // Check for pivot only when we have enough bars
                if (this._history.length >= left + right + 1) {
                    // Candidate pivot index (right bars behind current)
                    const cIdx = this._history.length - 1 - right;
                    const cBar = this._history[cIdx];

                    // Test for Pivot High:
                    // Candidate high must be GREATER than all neighbors within [left, right]
                    const isPH = (() => {
                        for (let i = 1; i <= left; i++) {
                            if (this._history[cIdx - i].high >= cBar.high) return false;
                        }
                        for (let i = 1; i <= right; i++) {
                            if (this._history[cIdx + i].high >= cBar.high) return false;
                        }
                        return true;
                    })();

                    // Test for Pivot Low:
                    // Candidate low must be LESS than all neighbors within [left, right]
                    const isPL = (() => {
                        for (let i = 1; i <= left; i++) {
                            if (this._history[cIdx - i].low <= cBar.low) return false;
                        }
                        for (let i = 1; i <= right; i++) {
                            if (this._history[cIdx + i].low <= cBar.low) return false;
                        }
                        return true;
                    })();

                    // Output pivot markers with offset to place them at the correct bar
                    if (isPH) {
                        phOut = { value: cBar.high, offset: -right };
                    }

                    if (isPL) {
                        plOut = { value: cBar.low, offset: -right };
                    }
                }

                return [phOut, plOut];
            };
        },
    };
}

// Export for TradingView custom indicator loading
if (typeof module !== 'undefined' && module.exports) {
    module.exports = SimplePivotIndicator;
}
