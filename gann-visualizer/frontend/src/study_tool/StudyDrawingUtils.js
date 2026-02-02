/**
 * Study Drawing Utilities
 * 
 * Functions to draw study-related elements (angle fans, pivot markers)
 * on the TradingView Advanced Chart.
 * 
 * Compatible with the response format from /evaluate_strategy_step
 * when processing studies (type: "drawing_update")
 */

/**
 * Draw all elements from a study response
 * @param {Object} chart - TradingView chart instance
 * @param {Object} data - Study response data
 * @param {Object} shapeTracking - Object to track created shape IDs for cleanup
 */
export function processStudyResponse(chart, data, shapeTracking = {}) {
    if (!chart || !data) return shapeTracking;

    // Draw angle lines or polylines (EMA, indicators)
    if (data.drawings && data.drawings.length > 0) {
        data.drawings.forEach(drawing => {
            let shapeId;

            if (drawing.type === 'polyline') {
                // Handle polyline (EMA line, moving averages, etc.)
                shapeId = drawPolyline(chart, drawing, shapeTracking);
            } else {
                // Handle trend_line and other types
                shapeId = drawAngleLine(chart, drawing);
            }

            if (shapeId && drawing.id) {
                shapeTracking[drawing.id] = shapeId;
            }
        });
    }

    // Draw pivot markers
    if (data.pivot_markers && data.pivot_markers.length > 0) {
        data.pivot_markers.forEach(pivot => {
            const shapeId = drawPivotMarker(chart, pivot);
            if (shapeId) {
                const trackingKey = pivot.id || `pivot_${pivot.type}_${pivot.time}`;
                shapeTracking[trackingKey] = shapeId;
            }
        });
    }

    // Remove completed drawings
    if (data.remove_drawings && data.remove_drawings.length > 0) {
        data.remove_drawings.forEach(drawingId => {
            const shapeId = shapeTracking[drawingId];
            if (shapeId) {
                try {
                    chart.removeEntity(shapeId);
                    delete shapeTracking[drawingId];
                } catch (e) {
                    console.warn('[StudyDrawing] Failed to remove shape:', drawingId, e);
                }
            }
        });
    }

    return shapeTracking;
}

/**
 * Draw a single angle line on the chart
 * @param {Object} chart - TradingView chart instance
 * @param {Object} drawing - Drawing definition from backend
 * @returns {string|null} - Shape ID if created, null otherwise
 */
export function drawAngleLine(chart, drawing) {
    if (!chart || !drawing || drawing.type !== 'trend_line') {
        return null;
    }

    try {
        const points = drawing.points.map(p => ({
            time: p.time,
            price: p.price
        }));

        const options = {
            shape: 'trend_line',
            lock: true,
            disableUndo: true,
            overrides: {
                linecolor: drawing.options?.linecolor || '#FF6600',
                linewidth: drawing.options?.linewidth || 2,
                extendLeft: drawing.options?.extendLeft || false,
                extendRight: drawing.options?.extendRight || false,
            },
            zOrder: 'top'
        };

        const result = chart.createMultipointShape(points, options);

        if (result && typeof result.then === 'function') {
            return result;  // Returns promise that resolves to shape ID
        }

        return result;
    } catch (e) {
        console.error('[StudyDrawing] Failed to draw angle line:', e);
        return null;
    }
}

/**
 * Draw a polyline (connected line segments) on the chart
 * Used for indicators like EMA, SMA, etc.
 * @param {Object} chart - TradingView chart instance
 * @param {Object} drawing - Polyline definition {id, type, points, options}
 * @param {Object} shapeTracking - Object tracking existing shapes for cleanup
 * @returns {Array} - Array of shape IDs created
 */
export function drawPolyline(chart, drawing, shapeTracking = {}) {
    if (!chart || !drawing || drawing.type !== 'polyline') {
        return null;
    }

    const points = drawing.points || [];
    if (points.length < 2) {
        return null;
    }

    try {
        // First, remove existing polyline with same ID to redraw it fresh
        // (the EMA line grows with each new candle)
        const existingSegments = shapeTracking[`${drawing.id}_segments`] || [];
        existingSegments.forEach(segmentId => {
            try {
                if (segmentId && typeof segmentId !== 'object') {
                    chart.removeEntity(segmentId);
                } else if (segmentId && typeof segmentId.then === 'function') {
                    segmentId.then(id => {
                        if (id) chart.removeEntity(id);
                    }).catch(() => { });
                }
            } catch (e) {
                // Ignore removal errors
            }
        });

        const overrides = drawing.options?.overrides || {};
        const lineColor = overrides.lineColor || '#FFD700';  // Gold default for EMA
        const lineWidth = overrides.lineWidth || 2;
        const lineStyle = overrides.lineStyle || 0; // 0=solid, 1=dotted, 2=dashed

        const segmentIds = [];

        // Draw polyline as connected trend lines (2 points each)
        // TradingView doesn't have native polyline, so we connect segments
        for (let i = 0; i < points.length - 1; i++) {
            const segmentPoints = [
                { time: points[i].time, price: points[i].price },
                { time: points[i + 1].time, price: points[i + 1].price }
            ];

            const result = chart.createMultipointShape(segmentPoints, {
                shape: 'trend_line',
                lock: true,
                disableUndo: true,
                overrides: {
                    linecolor: lineColor,
                    linewidth: lineWidth,
                    linestyle: lineStyle,
                    extendLeft: false,
                    extendRight: false
                },
                zOrder: 'top'
            });

            if (result) {
                segmentIds.push(result);
            }
        }

        // Store segment IDs for future cleanup
        shapeTracking[`${drawing.id}_segments`] = segmentIds;

        console.log(`[StudyDrawing] Drew EMA polyline with ${segmentIds.length} segments`);

        // Return first segment ID as the "representative" ID
        return segmentIds.length > 0 ? segmentIds[0] : null;
    } catch (e) {
        console.error('[StudyDrawing] Failed to draw polyline:', e);
        return null;
    }
}

/**
 * Draw a pivot marker on the chart
 * @param {Object} chart - TradingView chart instance
 * @param {Object} pivot - Pivot definition {type, time, price, bar_index}
 * @returns {string|null} - Shape ID if created, null otherwise
 */
export function drawPivotMarker(chart, pivot) {
    if (!chart || !pivot) {
        return null;
    }

    try {
        const isHigh = pivot.type === 'pivot_high' || pivot.type === 'high';

        const point = {
            time: pivot.time,
            price: pivot.price
        };

        // User reported seeing flags instead of triangles/arrows.
        // 'triangle_down' might not be valid for createShape in this version, causing fallback to a flag-like default.
        // 'arrow_down' is the standard shape that looks like a triangle pointer.

        const options = {
            shape: isHigh ? 'arrow_down' : 'arrow_up',
            lock: true,
            disableUndo: true,
            text: '', // Ensure no text is displayed (flags often have text)
            overrides: {
                color: isHigh ? '#e91e63' : '#2196F3',
                linewidth: 1,
            },
            zOrder: 'top'
        };

        const result = chart.createShape(point, options);

        if (result && typeof result.then === 'function') {
            return result;
        }

        return result;
    } catch (e) {
        console.error('[StudyDrawing] Failed to draw pivot marker:', e);
        return null;
    }
}

/**
 * Draw a vertical infinite line
 * @param {Object} chart - TradingView chart instance
 * @param {Object} drawing - Drawing definition {id, points: [{time, price}], options}
 * @returns {string|null} - Shape ID if created, null otherwise
 */
export function drawVerticalLine(chart, drawing) {
    if (!chart || !drawing || !drawing.points || drawing.points.length === 0) {
        return null;
    }

    try {
        const point = {
            time: drawing.points[0].time,
            price: drawing.points[0].price
        };

        const options = {
            shape: 'vertical_line',
            lock: true,
            disableUndo: true,
            text: drawing.options?.text || '',
            overrides: {
                linecolor: drawing.options?.linecolor || '#AAAAAA',
                linewidth: drawing.options?.linewidth || 1,
                linestyle: drawing.options?.linestyle || 2,
                showLabel: !!drawing.options?.text
            },
            zOrder: 'bottom'
        };

        const result = chart.createShape(point, options);

        if (result && typeof result.then === 'function') {
            return result;
        }
        return result;
    } catch (e) {
        console.error('[StudyDrawing] Failed to draw vertical line:', e);
        return null;
    }
}

/**
 * Draw a generic marker/shape (circle, cross, etc.)
 * @param {Object} chart - TradingView chart instance
 * @param {Object} drawing - Drawing definition {id, points, options}
 * @returns {string|null} - Shape ID
 */
export function drawGenericMarker(chart, drawing) {
    if (!chart || !drawing || !drawing.points || drawing.points.length === 0) {
        return null;
    }

    try {
        const point = {
            time: drawing.points[0].time,
            price: drawing.points[0].price
        };

        // Map abstract shape names to TradingView shape names if needed
        // 'circle' is 'icon' with specific paths, but TV has 'circle' shape in newer versions
        // Fallback to 'icon' or 'arrow_down' if specific shape not supported
        let shapeType = drawing.options?.shape || 'icon';

        // Use 'callout' or 'arrow_up' as safe defaults if unsure
        // For heatmaps (dots), 'circle' is best if supported, otherwise tiny 'icon'

        const options = {
            shape: shapeType,
            lock: true,
            disableUndo: true,
            text: drawing.options?.text || '',
            overrides: {
                color: drawing.options?.color || '#FFFF00',
                backgroundColor: drawing.options?.color || '#FFFF00',
                transparency: drawing.options?.transparency || 50,
                size: drawing.options?.size || 1
            },
            zOrder: 'top'
        };

        const result = chart.createShape(point, options);

        if (result && typeof result.then === 'function') {
            return result;
        }
        return result;
    } catch (e) {
        console.error('[StudyDrawing] Failed to draw generic marker:', e);
        return null;
    }
}

/**
 * Clear all study drawings from the chart
 * @param {Object} chart - TradingView chart instance
 * @param {Object} shapeTracking - Object containing tracked shape IDs
 */
export function clearAllStudyDrawings(chart, shapeTracking) {
    if (!chart || !shapeTracking) return;

    Object.keys(shapeTracking).forEach(key => {
        const shapeId = shapeTracking[key];
        try {
            if (shapeId && typeof shapeId !== 'object') {
                chart.removeEntity(shapeId);
            } else if (shapeId && typeof shapeId.then === 'function') {
                // Handle promise
                shapeId.then(id => {
                    if (id) chart.removeEntity(id);
                }).catch(() => { });
            }
        } catch (e) {
            // Ignore removal errors
        }
    });
}

/**
 * Draw an entire angle fan (main line + fractions)
 * Convenience function for direct fan creation
 * @param {Object} chart - TradingView chart instance
 * @param {Object} fromPivot - Source pivot {time, price}
 * @param {Object} toPivot - Destination pivot {time, price}
 * @param {Array} fractions - Fraction values (default: [7/8, 3/4, 1/2, 1/4, 1/8])
 * @param {Array} colors - Colors for each fraction line
 * @param {number} extensionBars - How many bars to extend lines
 * @param {number} barInterval - Time interval per bar in seconds
 */
export function drawAngleFan(
    chart,
    fromPivot,
    toPivot,
    fractions = [0.875, 0.75, 0.5, 0.25, 0.125],
    colors = ['#c62828', '#ad1457', '#6a1b9a', '#283593', '#00695c'],
    extensionBars = 50,
    barInterval = 60
) {
    if (!chart || !fromPivot || !toPivot) return [];

    const shapeIds = [];

    const t0 = fromPivot.time;
    const p0 = fromPivot.price;
    const t1 = toPivot.time;
    const p1 = toPivot.price;

    const dt = Math.max(1, t1 - t0);
    const dp = p1 - p0;
    const mainSlope = dp / dt;

    const extensionTime = barInterval * extensionBars;
    const endTime = t1 + extensionTime;

    // Draw main angle line
    try {
        const mainEndPrice = p1 + (mainSlope * extensionTime);
        const mainPoints = [
            { time: t0, price: p0 },
            { time: endTime, price: mainEndPrice }
        ];

        const mainResult = chart.createMultipointShape(mainPoints, {
            shape: 'trend_line',
            lock: true,
            disableUndo: true,
            overrides: {
                linecolor: '#FF6600',
                linewidth: 3,
                extendLeft: false,
                extendRight: false
            },
            zOrder: 'top'
        });

        if (mainResult) shapeIds.push(mainResult);
    } catch (e) {
        console.error('[StudyDrawing] Failed to draw main angle:', e);
    }

    // Draw fraction lines
    fractions.forEach((fraction, i) => {
        try {
            const fracSlope = mainSlope * fraction;
            const fracEndPrice = p0 + (fracSlope * (endTime - t0));

            const fracPoints = [
                { time: t0, price: p0 },
                { time: endTime, price: fracEndPrice }
            ];

            const fracResult = chart.createMultipointShape(fracPoints, {
                shape: 'trend_line',
                lock: true,
                disableUndo: true,
                overrides: {
                    linecolor: colors[i] || '#888888',
                    linewidth: 2,
                    extendLeft: false,
                    extendRight: false
                },
                zOrder: 'top'
            });

            if (fracResult) shapeIds.push(fracResult);
        } catch (e) {
            console.error('[StudyDrawing] Failed to draw fraction line:', e);
        }
    });

    return shapeIds;
}
