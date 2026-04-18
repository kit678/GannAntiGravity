// public/indicators/PivotFanBus.js  v-pixel-perfect-2025-11-25-17-30

// This module provides a global event bus for pivot fan drawing requests.

window.PivotFanBus = {
    _fanCallback: null,
    onFan(callback) {
        this._fanCallback = callback;
    },
    emitFan(from, to) {
        console.log('[PivotFanBus] emitFan called with from:', from, 'to:', to);
        if (this._fanCallback) {
            this._fanCallback(from, to);
        }
    }
};

// This class is responsible for drawing the pivot fans on the chart.
window.PivotFanDrawer = class PivotFanDrawer {
    constructor(widget) {
        this.widget = widget;
        this.dataReady = false;
        this.drawQueue = [];
        this._shapeIds = [];
        this._maxShapes = 120;
        this._fractions = [0.875, 0.75, 0.5, 0.25, 0.125];
        this._fractionColors = ['#c62828', '#ad1457', '#6a1b9a', '#283593', '#00695c'];
        console.log('[PivotFanDrawer] fractions loaded:', this._fractions);

        this.widget.onChartReady(() => {
            const chart = this.widget.chart ? this.widget.chart() : this.widget.activeChart();
            chart.onDataLoaded().subscribe(null, () => {
                this.dataReady = true;
                this._processDrawQueue();
            }, true);
        });

        window.PivotFanBus.onFan(this._onFanRequest.bind(this));
    }

    _onFanRequest(from, to) {
        console.log('[PivotFanDrawer] _onFanRequest called with:', from, to);
        if (this.dataReady) {
            console.log('[PivotFanDrawer] Data ready, drawing fan and fractions');
            this._drawFan(from, to);
            this._drawFractionFans(from, to);
        } else {
            console.log('[PivotFanDrawer] Data not ready, queuing request');
            this.drawQueue.push({ from, to });
        }
    }

    _drawFan(from, to) {
        console.log('[PivotFanDrawer] _drawFan called with from:', from, 'to:', to);
        const chart = this.widget.chart ? this.widget.chart() : this.widget.activeChart();
        if (!chart) return;

        // Draw the fan line regardless of visible range for now
        const toSec = (t) => Math.floor(t / 1000);
        const mainPoints = [
            { time: toSec(from.time), price: from.price },
            { time: toSec(to.time), price: to.price },
        ];

        const mainOpts = {
            shape: 'trend_line',
            lock: true,
            disableUndo: true,
            overrides: {
                linecolor: '#ff0000',   // bright red – impossible to miss
                linewidth: 3,           // thick
                extendLeft: false,
                extendRight: false,     // *** clipped exactly to the two pivots ***
            },
            zOrder: 'top',
        };

        try {
            console.log('[PivotFanDrawer] Calling chart.createMultipointShape with points:', mainPoints, 'options:', mainOpts);
            const ret = chart.createMultipointShape(mainPoints, mainOpts);
            console.log('[PivotFanDrawer] createMultipointShape returned:', ret);
            if (ret && typeof ret.then === 'function') {
                ret.then((id) => {
                    console.log('[PivotFanDrawer] Shape created with id:', id);
                    this._shapeIds.push(id);
                    if (this._shapeIds.length > this._maxShapes) {
                        const oldId = this._shapeIds.shift();
                        chart.removeEntity(oldId);
                    }
                });
            }
        } catch (e) {
            console.error('[Fan] createMultipointShape failed', e);
        }
    }

    _drawFractionFans(from, to) {
        const chart = this.widget.chart ? this.widget.chart() : this.widget.activeChart();
        if (!chart) return;
        const toSec = (t) => Math.floor(t / 1000);
        const t0 = toSec(from.time);
        const t1 = toSec(to.time);
        const dt = Math.max(1, t1 - t0);
        const dp = to.price - from.price;
        const slopeMain = dp / dt;

        for (let i = 0; i < this._fractions.length; i++) {
            const f = this._fractions[i];
            const s = slopeMain * f;
            const endTimeSec = t0 + dt;
            const endPrice = from.price + s * dt;
            const points = [
                { time: Math.floor(t0), price: from.price },
                { time: Math.floor(endTimeSec), price: endPrice },
            ];
            const opts = {
                shape: 'trend_line',
                lock: true,
                disableUndo: true,
                overrides: {
                    linecolor: this._fractionColors[i],
                    linewidth: 2,
                    extendLeft: false,
                    extendRight: false,
                },
                zOrder: 'top',
            };
            try {
                const ret = chart.createMultipointShape(points, opts);
                if (ret && typeof ret.then === 'function') {
                    ret.then((id) => {
                        this._shapeIds.push(id);
                        if (this._shapeIds.length > this._maxShapes) {
                            const oldId = this._shapeIds.shift();
                            chart.removeEntity(oldId);
                        }
                    });
                }
            } catch (e) {
                console.error('[Fan] createMultipointShape failed (fraction revert)', e);
            }
        }
    }

    _drawRefCircle(chart, cx, cy, r) {
        // faint reference circle (16 segments)
        const segs = 16;
        for (let i = 0; i < segs; i++) {
            const a1 = (i * 2 * Math.PI) / segs;
            const a2 = ((i + 1) * 2 * Math.PI) / segs;
            const x1 = cx + r * Math.cos(a1), y1 = cy + r * Math.sin(a1);
            const x2 = cx + r * Math.cos(a2), y2 = cy + r * Math.sin(a2);
            
            let tp1, tp2;
            if (chart.coordinateToTimePrice) {
                tp1 = chart.coordinateToTimePrice(x1, y1);
                tp2 = chart.coordinateToTimePrice(x2, y2);
            } else if (chart.coordinateToTime && chart.coordinateToPrice) {
                const time1 = chart.coordinateToTime(x1);
                const price1 = chart.coordinateToPrice(y1);
                const time2 = chart.coordinateToTime(x2);
                const price2 = chart.coordinateToPrice(y2);
                tp1 = time1 && price1 ? { time: time1, price: price1 } : null;
                tp2 = time2 && price2 ? { time: time2, price: price2 } : null;
            }
            
            if (tp1 && tp2) {
                chart.createMultipointShape([
                    { time: Math.floor(tp1.time), price: tp1.price },
                    { time: Math.floor(tp2.time), price: tp2.price }
                ], {
                    shape: 'trend_line', lock: true, disableUndo: true,
                    overrides: { linecolor: '#999', linewidth: 1, linestyle: 2,
                                  extendLeft: false, extendRight: false },
                    zOrder: 'top'
                });
            }
        }
    }

    _rayCircleIntersect(chart, cx, cy, r, startPx, endPx, f) {
        console.log(`[RayIntersect] fraction ${f}`);
        // unit vector of main fan
        const dx0 = endPx.x - cx, dy0 = endPx.y - cy;
        const L0 = Math.hypot(dx0, dy0) || 1;
        const ux0 = dx0 / L0, uy0 = dy0 / L0;
        console.log(`[RayIntersect] main unit vector (${ux0.toFixed(2)},${uy0.toFixed(2)})`);

        // rotate unit vector by angle that gives slope fraction f
        const mainSlope = (endPx.y - startPx.y) / (endPx.x - startPx.x);
        const fracSlope = mainSlope * f;
        const θ = Math.atan2(fracSlope, 1) - Math.atan2(mainSlope, 1);
        const cosθ = Math.cos(θ), sinθ = Math.sin(θ);
        const ux = ux0 * cosθ - uy0 * sinθ;
        const uy = ux0 * sinθ + uy0 * cosθ;
        console.log(`[RayIntersect] rotated unit vector (${ux.toFixed(2)},${uy.toFixed(2)})`);

        // circle intersection:  P = (cx,cy) + r·(ux,uy)
        const ix = cx + r * ux;
        const iy = cy + r * uy;
        console.log(`[RayIntersect] intersection pixel (${ix.toFixed(1)},${iy.toFixed(1)})`);

        // convert back to time/price
        let tp;
        if (chart.coordinateToTimePrice) {
            tp = chart.coordinateToTimePrice(ix, iy);
        } else if (chart.coordinateToTime && chart.coordinateToPrice) {
            const time = chart.coordinateToTime(ix);
            const price = chart.coordinateToPrice(iy);
            tp = time && price ? { time: time, price: price } : null;
        } else {
            console.error('[RayIntersect] No coordinate back-conversion methods found');
            return null;
        }
        console.log(`[RayIntersect] back-converted`, tp);
        return tp ? { time: Math.floor(tp.time), price: tp.price } : null;
    }

    _drawFractionFansFallback(from, to) {
        // Fallback method using the original weighted approach
        const chart = this.widget.chart ? this.widget.chart() : this.widget.activeChart();
        if (!chart) return;
        const toSec = (t) => Math.floor(t / 1000);
        const t0 = toSec(from.time);
        const t1 = toSec(to.time);
        const dt = Math.max(1, t1 - t0); // seconds
        const dp = to.price - from.price; // price units
        const slopeMain = dp / dt;

        // Simple fallback using proportional extension
        for (let i = 0; i < this._fractions.length; i++) {
            const f = this._fractions[i];
            const s = slopeMain * f;
            const dtf = dt; // Use same time extent as main fan
            const endTimeSec = t0 + dtf;
            const endPrice = from.price + s * dtf;
            const points = [
                { time: Math.floor(t0), price: from.price },
                { time: Math.floor(endTimeSec), price: endPrice },
            ];
            const opts = {
                shape: 'trend_line',
                lock: true,
                disableUndo: true,
                overrides: {
                    linecolor: this._fractionColors[i],
                    linewidth: 2,
                    extendLeft: false,
                    extendRight: false,
                },
                zOrder: 'top',
            };
            try {
                const ret = chart.createMultipointShape(points, opts);
                if (ret && typeof ret.then === 'function') {
                    ret.then((id) => {
                        this._shapeIds.push(id);
                        if (this._shapeIds.length > this._maxShapes) {
                            const oldId = this._shapeIds.shift();
                            chart.removeEntity(oldId);
                        }
                    });
                }
            } catch (e) {
                console.error('[Fan] createMultipointShape failed (fraction fallback)', e);
            }
        }
    }

    _processDrawQueue() {
        while(this.drawQueue.length > 0) {
            const req = this.drawQueue.shift();
            this._drawFan(req.from, req.to);
            this._drawFractionFans(req.from, req.to);
        }
    }
}
