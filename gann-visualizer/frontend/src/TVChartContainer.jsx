import React, { useEffect, useRef, useState, useImperativeHandle, forwardRef } from 'react';
import createChartDatafeed from './chart/ChartDatafeed';
import { processStudyResponse, clearAllStudyDrawings } from './study_tool/StudyDrawingUtils';
import { normalizeHypothesisRunCandle } from './hypothesisRunContext.js';
import { buildHypothesisRsiOverlayModel } from './hypothesisRsiOverlay.js';
import { buildHypothesisVisibleRange, shouldApplyRunCandleVisibleRange, shouldDeferHypothesisNavigation, shouldLoadHypothesisRunCandles } from './hypothesisChartNavigation.js';

export const TVChartContainer = forwardRef(({ symbol = 'NIFTY 50', datafeedUrl, interval = '60', onTradeLogged, dataSource = 'dhan', cycleType = '24_hour', sessionDuration = 'standard', onSymbolChange, onPlayingStateChange, selectedInteraction, showPatternLegend = false, showPatternDots = false, onStrategyMeta, ...props }, ref) => {
    const chartContainerRef = useRef(null);
    const datafeedRef = useRef(null);
    const widgetRef = useRef(null);

    // Playback state
    const [isPlaybackMode, setIsPlaybackMode] = useState(false);
    const [isPlaying, setIsPlaying] = useState(false);
    const [, setPlaybackSpeed] = useState(1000);

    // Sync playing state to parent
    useEffect(() => {
        if (onPlayingStateChange) onPlayingStateChange(isPlaying);
    }, [isPlaying, onPlayingStateChange]);

    // Store trades for replay mode
    const tradesRef = useRef([]);

    // Track study shapes for cleanup
    const studyShapesRef = useRef({});
    // Track fan labels for visibility toggling
    const fanLabelsRef = useRef({});
    const tradeMarkersRef = useRef({});

    // Track indicator line series (EMA, etc.) for cleanup
    const indicatorLinesRef = useRef({});

    // Track RSI/SMA study entities and shapes for cleanup when navigating away
    const rsiStudyRef = useRef({ studies: [], shapes: [] });

    // Track current clean symbol for fallback when chart.symbol() is unavailable
    const currentCleanSymbolRef = useRef(symbol);

    // Store latest visible labels so callbacks don't capture stale state
    const visibleFanLabelsRef = useRef(['Primary', 'Secondary', 'Tertiary']);

    // Sync visibility when props.visibleFanLabels changes
    useEffect(() => {
        visibleFanLabelsRef.current = props.visibleFanLabels || [];
        
        // Apply visibility to existing shapes
        if (widgetRef.current && studyShapesRef.current && fanLabelsRef.current) {
            try {
                let chart;
                try {
                    chart = widgetRef.current.activeChart();
                } catch (e) {
                    console.warn("[TVChartContainer] activeChart not ready yet");
                    return;
                }
                const visibleLabels = visibleFanLabelsRef.current;
                
                Object.entries(studyShapesRef.current).forEach(([drawingId, shapeId]) => {
                    const identity = fanLabelsRef.current[drawingId];
                    if (identity) {
                        const isVisible = visibleLabels.includes(identity);
                        if (typeof shapeId === 'object' && typeof shapeId.then === 'function') {
                            shapeId.then(id => {
                                if (id) {
                                    const shape = chart.getShapeById(id);
                                    if (shape) shape.setProperties({ visible: isVisible });
                                }
                            }).catch(e => console.warn("[TVChartContainer] Error updating shape visibility:", e));
                        } else if (shapeId) {
                            const shape = chart.getShapeById(shapeId);
                            if (shape) shape.setProperties({ visible: isVisible });
                        }
                    }
                });
            } catch (e) {
                console.warn("[TVChartContainer] Error updating shape visibility:", e);
            }
        }
    }, [props.visibleFanLabels]);

    useEffect(() => {
        console.log('[TVChart] useEffect triggered - dataSource:', dataSource, 'symbol:', symbol);

        let scriptElement = null;
        let isMounted = true;

        function initChart() {
            if (!isMounted) return;
            if (!window.TradingView) {
                console.error('[TVChart] TradingView not available');
                return;
            }

            // Force clear TradingView's aggressive local storage caching so new timeframes (like 4m) appear
            try {
                Object.keys(localStorage).forEach(key => {
                    if (key.toLowerCase().includes('tradingview') || key.toLowerCase().includes('udf')) {
                        localStorage.removeItem(key);
                    }
                });
            } catch (e) {
                console.warn("Could not clear localStorage", e);
            }

            console.log('[TVChart] Initializing chart with dataSource:', dataSource);

            const udfDatafeed = new window.Datafeeds.UDFCompatibleDatafeed(datafeedUrl);
            const customDatafeed = createChartDatafeed(udfDatafeed, dataSource);
            datafeedRef.current = customDatafeed;

            const widget = new window.TradingView.widget({
            symbol: symbol,
            interval: interval,
            timezone: dataSource === 'binance' ? 'Etc/UTC' : 'Asia/Kolkata',
            fullscreen: false,
            container: chartContainerRef.current,
            datafeed: customDatafeed,
            library_path: '/charting_library/',
            locale: 'en',
            disabled_features: ['use_localstorage_for_settings', 'header_compare', 'create_volume_indicator_by_default'],
            enabled_features: ['study_templates', 'header_symbol_search', 'symbol_search_hot_key'],
            symbol_search_request_delay: 500,
            charts_storage_url: 'https://saveload.tradingview.com',
            charts_storage_api_version: '1.1',
            client_id: 'tradingview.com',
            user_id: 'public_user_id',
            theme: 'Dark',
            autosize: true,
            supported_resolutions: ["1", "4", "5", "15", "30", "60", "240", "D", "W", "M"],
            favorites: {
                intervals: ["1", "4", "5", "15", "30", "60", "240", "D"]
            },
            time_scale: {
                right_offset: 5
            },
                time_frames: [
                { text: "1y", resolution: "D", description: "1 Year" },
                { text: "6m", resolution: "D", description: "6 Months" },
                { text: "3m", resolution: "D", description: "3 Months" },
                { text: "1m", resolution: "240", description: "1 Month" },
                { text: "5d", resolution: "60", description: "5 Days" },
                { text: "1d", resolution: "15", description: "1 Day" },
            ],
            overrides: {
                "scalesProperties.showSymbolLabels": true,
                "mainSeriesProperties.candleStyle.drawBorder": true,
            },
            });

            widgetRef.current = widget;
            window.tvWidget = widget;

            widget.onChartReady(() => {
                console.log("[Chart] Ready");

                // Apply dynamic Price-to-Bar Ratio via backend mapping
                let chart;
                try {
                    chart = widget.activeChart();
                } catch (e) {
                    console.warn("[Chart] activeChart not ready yet on chartReady event");
                    return;
                }
                const currentResolution = chart.resolution();
                // Clean the symbol if it contains YF
                let cleanSymbol = symbol;
                if (cleanSymbol && cleanSymbol.endsWith(':YF')) {
                    cleanSymbol = cleanSymbol.replace(':YF', '');
                }

                fetch(`http://localhost:8005/api/scale_ratio?symbol=${encodeURIComponent(cleanSymbol)}&resolution=${encodeURIComponent(currentResolution)}&cycle_type=${encodeURIComponent(cycleType)}&session_duration=${encodeURIComponent(sessionDuration)}`)
                    .then(res => res.json())
                    .then(data => {
                        if (data && data.scale_ratio) {
                            try {
                                chart.setPriceToBarRatio(data.scale_ratio, { disableUndo: true });
                                try {
                                    if (typeof chart.setPriceToBarRatioLocked === 'function') {
                                        chart.setPriceToBarRatioLocked(true, { disableUndo: true });
                                    } else {
                                        chart.getPriceScale().setMode({ autoScale: false });
                                        chart.executeActionById("priceScaleLockRatio");
                                    }
                                } catch (_e) { }
                                console.log(`[Chart] Applied and Locked backend PriceToBarRatio: ${data.scale_ratio}`);
                            } catch (e) {
                                console.warn("[Chart] Failed to set backend PriceToBarRatio:", e);
                            }
                        }
                    })
                    .catch(err => {
                        console.warn("[Chart] Failed to fetch scale ratio from backend, defaulting:", err);
                        try { chart.setPriceToBarRatio(5.5); } catch (e) { }
                    });

                // Actively remove any Bollinger Bands that might have been loaded from a saved layout
                try {
                    const allStudies = chart.getAllStudies();
                    allStudies.forEach(study => {
                        if (study.name && study.name.toLowerCase().includes('bollinger')) {
                            chart.removeEntity(study.id);
                            console.log("[Chart] Actively removed Bollinger Bands from saved layout");
                        }
                    });
                } catch (e) {
                    console.warn("[Chart] Failed to remove Bollinger Bands:", e);
                }

                try {
                    chart.onSymbolChanged().subscribe(null, (symbolInfo) => {
                        console.log("[Chart] Symbol Changed to:", symbolInfo);

                        // Extract cleanly if it has suffix. Always prefer ticker.
                        let cleanName = symbolInfo.ticker || symbolInfo.name;

                        if (cleanName && cleanName.endsWith(':YF')) {
                            cleanName = cleanName.replace(':YF', '');
                        }
                        currentCleanSymbolRef.current = cleanName;

                        if (onSymbolChange) onSymbolChange(cleanName);

                        // Automatically sync backend aspect ratio mapping for newly searched symbol
                        let currentRes;
                        try {
                            currentRes = chart.resolution();
                        } catch (e) {
                            return;
                        }
                        
                        fetch(`http://localhost:8005/api/scale_ratio?symbol=${encodeURIComponent(cleanName)}&resolution=${encodeURIComponent(currentRes)}&cycle_type=${encodeURIComponent(cycleType)}&session_duration=${encodeURIComponent(sessionDuration)}`)
                            .then(res => res.json())
                            .then(data => {
                                if (data && data.scale_ratio) {
                                    try {
                                        chart.setPriceToBarRatio(data.scale_ratio, { disableUndo: true });
                                        try {
                                            if (typeof chart.setPriceToBarRatioLocked === 'function') {
                                                chart.setPriceToBarRatioLocked(true, { disableUndo: true });
                                            } else {
                                                chart.getPriceScale().setMode({ autoScale: false });
                                                chart.executeActionById("priceScaleLockRatio");
                                            }
                                        } catch (_e) { }
                                        console.log(`[Chart] Updated and Locked PriceToBarRatio to ${data.scale_ratio} for new symbol: ${cleanName}`);
                                    } catch (e) {
                                        console.warn("[Chart] Failed to dynamically set backend PriceToBarRatio:", e);
                                    }
                                }
                            })
                            .catch(err => {
                                console.warn("[Chart] Failed to fetch scale ratio from backend, locked on old map:", err);
                            });

                    });
                } catch (e) {
                    console.warn("[Chart] Failed to subscribe to symbol changes:", e);
                }

                // Subscribe to Interval (Resolution) Changes to keep ratio in sync
                try {
                    chart.onIntervalChanged().subscribe(null, (interval, timeframeObj) => {
                        console.log("[Chart] Interval Changed to:", interval);

                        let cleanName;
                        try {
                            cleanName = chart.symbolExt ? chart.symbolExt().symbol : chart.symbol();
                        } catch (e) {
                            // fall through to fallback
                        }

                        if (!cleanName) {
                            cleanName = currentCleanSymbolRef.current;
                            console.log("[TVChart] Using fallback symbol for interval change:", cleanName);
                        }

                        if (!cleanName) {
                            console.warn("[TVChart] Interval changed but symbol is undefined, skipping ratio update");
                            return;
                        }

                        if (cleanName && cleanName.endsWith(':YF')) {
                            cleanName = cleanName.replace(':YF', '');
                        }
                        currentCleanSymbolRef.current = cleanName;

                        fetch(`http://localhost:8005/api/scale_ratio?symbol=${encodeURIComponent(cleanName)}&resolution=${encodeURIComponent(interval)}&cycle_type=${encodeURIComponent(cycleType)}&session_duration=${encodeURIComponent(sessionDuration)}`)
                            .then(res => res.json())
                            .then(data => {
                                if (data && data.scale_ratio) {
                                    try {
                                        chart.setPriceToBarRatio(data.scale_ratio, { disableUndo: true });
                                        try {
                                            if (typeof chart.setPriceToBarRatioLocked === 'function') {
                                                chart.setPriceToBarRatioLocked(true, { disableUndo: true });
                                            } else {
                                                chart.getPriceScale().setMode({ autoScale: false });
                                                chart.executeActionById("priceScaleLockRatio");
                                            }
                                        } catch (_e) { }
                                        console.log(`[Chart] Updated and Locked PriceToBarRatio to ${data.scale_ratio} for new interval: ${interval}`);
                                    } catch (e) {
                                        console.warn("[Chart] Failed to dynamically set backend PriceToBarRatio on interval change:", e);
                                    }
                                }
                            })
                            .catch(err => {
                                console.warn("[Chart] Failed to fetch scale ratio on interval change:", err);
                            });
                    });
                } catch (e) {
                    console.warn("[Chart] Failed to subscribe to interval changes:", e);
                }


            });
        }

        // Check if TradingView library is already loaded
        if (window.TradingView && window.Datafeeds && window.Datafeeds.UDFCompatibleDatafeed) {
            console.log('[TVChart] TradingView already loaded, initializing directly');
            initChart();
        } else {
            // Load the library for the first time
            console.log('[TVChart] Loading TradingView library...');
            scriptElement = document.createElement('script');
            scriptElement.src = '/charting_library/charting_library.js';
            scriptElement.async = true;
            scriptElement.onload = () => {
                console.log('[TVChart] TradingView library loaded');
                initChart();
            };
            document.body.appendChild(scriptElement);
        }

        return () => {
            console.log('[TVChart] Cleanup - destroying widget');
            isMounted = false;

            // Properly destroy widget to ensure clean re-initialization
            if (widgetRef.current) {
                try {
                    // Try to catch the "activeChart not ready" error gracefully on destruction too
                    let chartReady = false;
                    try {
                        chartReady = !!widgetRef.current.activeChart();
                    } catch(e) {}
                    
                    widgetRef.current.remove();
                    console.log('[TVChart] Widget destroyed for clean re-init');
                } catch (e) {
                    console.warn('[TVChart] Error removing widget:', e);
                }
                widgetRef.current = null;
            }
            datafeedRef.current = null;
            studyShapesRef.current = {};
            fanLabelsRef.current = {};
            fanDisplayMapRef.current = {};
            tradeMarkersRef.current = {};
            indicatorLinesRef.current = {};

            // Only remove script if we created one
            if (scriptElement && scriptElement.parentNode) {
                scriptElement.parentNode.removeChild(scriptElement);
            }
        };
    }, [symbol, datafeedUrl, interval, dataSource, onSymbolChange]);

    // Listen for changes to cycleType or sessionDuration and update the chart dynamically
    useEffect(() => {
        if (!widgetRef.current) return;
        try {
            let chart;
            try {
                chart = widgetRef.current.activeChart();
            } catch (e) {
                console.warn("[Chart] activeChart not available for config change update", e);
                return;
            }
            
            const currentResolution = chart.resolution();
            let cleanSymbol = chart.symbolExt ? chart.symbolExt().symbol : chart.symbol();
            
            if (!cleanSymbol) {
                // Symbol might not be ready yet
                return;
            }

            if (cleanSymbol && cleanSymbol.endsWith(':YF')) {
                cleanSymbol = cleanSymbol.replace(':YF', '');
            }

            fetch(`http://localhost:8005/api/scale_ratio?symbol=${encodeURIComponent(cleanSymbol)}&resolution=${encodeURIComponent(currentResolution)}&cycle_type=${encodeURIComponent(cycleType)}&session_duration=${encodeURIComponent(sessionDuration)}`)
                .then(res => res.json())
                .then(data => {
                    if (data && data.scale_ratio) {
                        chart.setPriceToBarRatio(data.scale_ratio, { disableUndo: true });
                        try {
                            if (typeof chart.setPriceToBarRatioLocked === 'function') {
                                chart.setPriceToBarRatioLocked(true, { disableUndo: true });
                            } else {
                                chart.getPriceScale().setMode({ autoScale: false });
                                chart.executeActionById("priceScaleLockRatio");
                            }
                        } catch (_e) { }
                        console.log(`[Chart] Updated PriceToBarRatio to ${data.scale_ratio} due to session config change`);
                    }
                })
                .catch(err => console.warn("[Chart] Failed to update ratio on config change", err));
        } catch (e) {
            // Chart might not be ready yet, which is fine (handled by initial load)
        }
    }, [cycleType, sessionDuration]);

    // Track the currently drawn interaction markers
    const interactionMarkersRef = useRef([]);
    // Track the last processed interaction to avoid duplicate processing
    const lastProcessedInteractionRef = useRef(null);

    // Track hypothesis markers for cleanup
    const hypothesisMarkerRef = useRef([]);
    // Track last navigated event key to skip re-render for same fan
    const lastNavigatedEventKeyRef = useRef(null);
    const navigationGenerationRef = useRef(0);
    const selectedHypothesisEventRef = useRef(null);
    const pendingHypothesisEventRef = useRef(null);
    const isLoadingRunCandlesRef = useRef(false);
    const loadedHypothesisRunPathRef = useRef(null);

    const executeHypothesisNavigation = (event) => {
        if (!widgetRef.current) return;
        const chart = widgetRef.current.activeChart();
        if (!chart) return;

        const eventKey = event.event_id != null ? String(event.event_id) : ((event.fan_display || '') + '|' + (event.datetime || event.time || ''));
        if (lastNavigatedEventKeyRef.current === eventKey) return;
        lastNavigatedEventKeyRef.current = eventKey;
        selectedHypothesisEventRef.current = eventKey;

        const gen = ++navigationGenerationRef.current;

        hypothesisMarkerRef.current.forEach(m => {
            try {
                if (m && typeof m.then === 'function') {
                    m.then(id => { if (id) chart.removeEntity(id); }).catch(() => {});
                } else if (m) {
                    chart.removeEntity(m);
                }
            } catch (_) {}
        });
        hypothesisMarkerRef.current = [];

        clearAllStudyDrawings(chart, studyShapesRef.current);
        studyShapesRef.current = {};

        Object.values(indicatorLinesRef.current).forEach(ids => {
            const idList = Array.isArray(ids) ? ids : [ids];
            idList.forEach(id => {
                try { chart.removeEntity(id); } catch (e) { /* ignore */ }
            });
        });
        indicatorLinesRef.current = {};

        rsiStudyRef.current.studies.forEach(id => {
            try { chart.removeEntity(id); } catch (e) { /* ignore */ }
        });
        rsiStudyRef.current.shapes.forEach(id => {
            try { chart.removeEntity(id); } catch (e) { /* ignore */ }
        });
        rsiStudyRef.current = { studies: [], shapes: [] };

        let visibleRange = null;
        try {
            visibleRange = chart.getVisibleRange();
        } catch (_) {}
        const {
            from: newFrom,
            to: newTo,
            centerTimeSec,
        } = buildHypothesisVisibleRange({ event, visibleRange });
        const eventTimeSec = event?.timestamp != null
            ? (event.timestamp < 2000000000 ? event.timestamp : Math.floor(event.timestamp / 1000))
            : centerTimeSec;

        function drawMarkerAndFan() {
            if (gen !== navigationGenerationRef.current) return;
            if (event.price != null) {
                const iconId = chart.createShape(
                    { time: eventTimeSec, price: event.price },
                    {
                        shape: 'icon',
                        lock: true,
                        disableSelection: true,
                        disableSave: true,
                        overrides: { color: '#FFFFFF', size: 10 },
                        icon: 0xf0ab,
                    }
                );
                if (iconId) hypothesisMarkerRef.current.push(iconId);
                const lineId = chart.createShape(
                    { time: eventTimeSec, price: event.price },
                    {
                        shape: 'vertical_line',
                        lock: true,
                        disableSelection: true,
                        disableSave: true,
                        overrides: { color: '#FFFFFF', linestyle: 2, linewidth: 1, showLabel: false },
                    }
                );
                if (lineId) hypothesisMarkerRef.current.push(lineId);
            }

            if (event.fan_geometry && event.fan_geometry.rays && event.fan_geometry.rays.length > 0) {
                const studyData = {
                    drawings: event.fan_geometry.rays.map(ray => ({
                        id: ray.id,
                        type: 'trend_line',
                        points: ray.points,
                        options: {
                            linecolor: ray.color,
                            linewidth: ray.width,
                            linestyle: 0,
                            extendRight: true,
                            fanIdentity: event.fan_display,
                            fanLabel: event.fan_display
                        }
                    })),
                    pivot_markers: (() => {
                        const m = [];
                        const g = event.fan_geometry;
                        if (g.origin && g.origin.time) m.push({ type: g.origin.label === 'high' ? 'pivot_high' : 'pivot_low', time: g.origin.time, price: g.origin.price, text: event.fan_display || (g.origin.label||'').toUpperCase() });
                        if (g.anchor && g.anchor.time) m.push({ type: g.anchor.label === 'high' ? 'pivot_high' : 'pivot_low', time: g.anchor.time, price: g.anchor.price });
                        return m;
                    })()
                };
                studyShapesRef.current = processStudyResponse(chart, studyData, studyShapesRef.current);
            }
        }

        const isRsiEvent = event.rsi_value != null
                || (event.event_type && String(event.event_type).startsWith('RSI_TRENDLINE_BREAK_'))
                || (Array.isArray(event.rsi_window) && event.rsi_window.length > 0);

            const drawRsiOverlay = () => {
                if (!widgetRef.current) return;
                const ovChart = widgetRef.current.activeChart();
                if (!ovChart) return;

                // Helper: parse backend time values (numeric string = Unix seconds, date string, or number)
                const toTimeSec = (val) => {
                    if (val == null) return null;
                    if (typeof val === 'number') return val > 1000000000 ? val : null;
                    const num = Number(val);
                    if (Number.isFinite(num) && num > 1000000000) return num;
                    const d = new Date(val);
                    return Number.isFinite(d.getTime()) ? d.getTime() / 1000 : null;
                };

                const shapes = [];

                try {
                    ovChart.createStudy('Relative Strength Index', false, false, {length: 14})
                        .then(id => {
                            if (id) {
                                console.log('[TVChart] Added RSI(14) study:', id);
                                rsiStudyRef.current.studies.push(id);
                            }
                        })
                        .catch(e => console.warn('[TVChart] RSI study resolve failed:', e));
                } catch (e) {
                    console.warn('[TVChart] createStudy RSI failed:', e);
                }

                try {
                    ovChart.createStudy('Moving Average', true, false, {length: 200}, {
                        'plot.color': '#FF9800',
                        'plot.linewidth': 2,
                    })
                        .then(id => {
                            if (id) {
                                console.log('[TVChart] Added SMA(200) study:', id);
                                rsiStudyRef.current.studies.push(id);
                            }
                        })
                        .catch(e => console.warn('[TVChart] SMA study resolve failed:', e));
                } catch (e) {
                    console.warn('[TVChart] createStudy SMA failed:', e);
                }

                if (event.entry_price != null) {
                    const side = (event.entry_side || event.direction || '').toUpperCase();
                    const entryColor = side === 'SHORT' ? '#EF5350' : '#4CAF50';
                    const entryLineId = ovChart.createShape(
                        { time: eventTimeSec, price: event.entry_price },
                        {
                            shape: 'horizontal_line',
                            lock: true,
                            disableUndo: true,
                            overrides: {
                                color: entryColor,
                                linestyle: 2,
                                linewidth: 2,
                                showLabel: true,
                                text: `ENTRY ${side} @ ${event.entry_price.toFixed(2)}`,
                            },
                        }
                    );
                    if (entryLineId) {
                        shapes.push(entryLineId);
                        hypothesisMarkerRef.current.push(entryLineId);
                    }
                }

                if (event.stop_price != null) {
                    const stopLineId = ovChart.createShape(
                        { time: eventTimeSec, price: event.stop_price },
                        {
                            shape: 'horizontal_line',
                            lock: true,
                            disableUndo: true,
                            overrides: {
                                color: '#F44336',
                                linestyle: 2,
                                linewidth: 1,
                                showLabel: true,
                                text: `STOP @ ${event.stop_price.toFixed(2)}`,
                            },
                        }
                    );
                    if (stopLineId) {
                        shapes.push(stopLineId);
                        hypothesisMarkerRef.current.push(stopLineId);
                    }
                }

                const labelText = event.rsi_value != null
                    ? `RSI: ${event.rsi_value.toFixed(1)} | Line: ${event.line_value_at_break != null ? event.line_value_at_break.toFixed(1) : '-'}`
                    : 'RSI Break';
                const labelId = ovChart.createShape(
                    { time: eventTimeSec, price: event.price || event.entry_price || 0 },
                    {
                        shape: 'label_down',
                        lock: true,
                        disableUndo: true,
                        overrides: {
                            color: '#FFFFFF',
                            backgroundColor: event.entry_side === 'SHORT' ? '#EF5350' : '#4CAF50',
                            fontsize: 12,
                            text: labelText,
                        },
                        text: labelText,
                    }
                );
                if (labelId) {
                    shapes.push(labelId);
                    hypothesisMarkerRef.current.push(labelId);
                }

                const candles = datafeedRef.current?.customData;
                const overlayModel = buildHypothesisRsiOverlayModel(event, candles);

                // If we have the full RSI series from the report, use that for the curve
                const rsiSeries = props.rsiSeries;
                const hasFullRsiSeries = rsiSeries && Array.isArray(rsiSeries) && rsiSeries.length > 0;

                if (hasFullRsiSeries || (overlayModel && overlayModel.windowPoints.length > 0 && candles && candles.length > 0)) {
                    let rsiMin = Infinity, rsiMax = -Infinity;
                    let priceMin = Infinity, priceMax = -Infinity;

                    // Build RSI curve points — use full series when available
                    const curveSource = hasFullRsiSeries
                        ? rsiSeries.map(p => ({
                            time: toTimeSec(p.time),
                            rsi: Number(p.rsi),
                            barIndex: Number(p.bar_index),
                        })).filter(p => Number.isFinite(p.time) && p.time > 0 && Number.isFinite(p.rsi))
                        : (() => {
                            const pts = [];
                            for (const pt of overlayModel.windowPoints) {
                                const rsi = pt.rsi;
                                if (rsi == null || !Number.isFinite(rsi)) continue;
                                const timeSec = pt.time;
                                if (!Number.isFinite(timeSec) || timeSec <= 0) continue;
                                pts.push({ time: timeSec, rsi, barIndex: pt.barIndex });
                            }
                            return pts;
                        })();

                    // --- Draw RSI curve & trendlines on price pane ---
                        // Determine visible time window for RSI range matching (like RSI panel)
                        let visFrom = -Infinity, visTo = Infinity;
                        try {
                            const vr = ovChart.getVisibleRange();
                            if (vr && vr.from && vr.to) { visFrom = vr.from; visTo = vr.to; }
                        } catch (_) {}
                        if (!Number.isFinite(visFrom) && curveSource.length > 0) {
                            visFrom = curveSource[0].time;
                            visTo = curveSource[curveSource.length - 1].time;
                        }

                    for (const p of curveSource) {
                        if (p.rsi < rsiMin) rsiMin = p.rsi;
                        if (p.rsi > rsiMax) rsiMax = p.rsi;
                    }

                    for (const candle of candles) {
                        if (!Number.isFinite(candle?.low) || !Number.isFinite(candle?.high)) continue;
                        if (candle.low < priceMin) priceMin = candle.low;
                        if (candle.high > priceMax) priceMax = candle.high;
                    }

                    if (curveSource.length >= 2 && Number.isFinite(rsiMin) && Number.isFinite(priceMin)) {
                        const rsiRange = rsiMax - rsiMin || 1;
                        const priceRange = priceMax - priceMin || 1;
                        // RSI band: 25% of chart height, positioned near the top (75%–100% of chart)
                        // Keeps RSI curve clearly separated from the candlestick price action
                        const bandTop = priceMin + priceRange * 1.00;
                        const bandHeight = priceRange * 0.25;
                        const rsiToPrice = (rsi) => bandTop - bandHeight + ((rsi - rsiMin) / rsiRange) * bandHeight;

                        const rsiLinePoints = curveSource.map(p => ({
                            time: p.time,
                            price: rsiToPrice(p.rsi),
                        }));

                        for (let i = 0; i < rsiLinePoints.length - 1; i++) {
                            const p1 = rsiLinePoints[i], p2 = rsiLinePoints[i + 1];
                            if (!p1 || !p2 || !Number.isFinite(p1.time) || !Number.isFinite(p1.price)
                                || !Number.isFinite(p2.time) || !Number.isFinite(p2.price)) continue;
                            // Skip segments entirely outside visible range
                            if (p2.time < visFrom || p1.time > visTo) continue;
                            const segId = ovChart.createMultipointShape([p1, p2], {
                                shape: 'trend_line',
                                lock: true,
                                disableUndo: true,
                                overrides: {
                                    linecolor: hasFullRsiSeries ? '#00BCD4' : '#00BCD4',
                                    linewidth: 1,
                                    linestyle: 0,
                                },
                                zOrder: 'top',
                            });
                            if (segId) {
                                shapes.push(segId);
                                hypothesisMarkerRef.current.push(segId);
                            }
                        }

                        // --- Draw RSI trendlines (multiple, color-coded by direction) ---
                        // Identify the event's broken trendline for highlighting
                        const evtLineStart = Number(event.line_start_bar_index);
                        const evtLineEnd = Number(event.line_end_bar_index);
                        const evtLineDir = String(event.line_direction || event.direction || '');
                        const allLines = props.allRsiLines;

                        const isEventLine = (l) =>
                            l.start_bar_index === evtLineStart &&
                            l.end_bar_index === evtLineEnd &&
                            String(l.direction) === evtLineDir;

                        if (allLines && Array.isArray(allLines) && allLines.length > 0) {
                            // Build bar_index → time lookup from curveSource for extension
                            const barTimeMap = new Map();
                            for (const pt of curveSource) {
                                if (Number.isFinite(pt.barIndex) && Number.isFinite(pt.time)) {
                                    barTimeMap.set(pt.barIndex, pt.time);
                                }
                            }

                            const MAX_VISIBLE_LINES = 6;

                        // First pass: collect visible lines with their drawing params
                        // Prefer best_fit lines (RANSAC) — only fall back to event lines if no best_fit exists for the direction
                        const drawList = [];
                        let eventLineEntry = null;

                        for (const line of allLines) {
                            const pa = line.pivot_a, pb = line.pivot_b;
                            if (!pa || !pb) continue;
                            const ta = toTimeSec(pa.time);
                            const tb = toTimeSec(pb.time);
                            const ra = Number(pa.rsi), rb = Number(pb.rsi);
                            if (!ta || !tb || !Number.isFinite(ta) || !Number.isFinite(tb)
                                || !Number.isFinite(ra) || !Number.isFinite(rb)) continue;

                            // Skip lines entirely outside visible range
                            if (tb < visFrom || ta > visTo) continue;

                            const tlP1 = { time: ta, price: rsiToPrice(ra) };
                            const tlP2 = { time: tb, price: rsiToPrice(rb) };
                            if (!Number.isFinite(tlP1.price) || !Number.isFinite(tlP2.price)) continue;

                            const isMatch = isEventLine(line);
                            // Boost best_fit lines so they always outrank event lines
                            const baseScore = Number(line.score) || 0;
                            const isBestFit = line.kind === "best_fit";
                            const boostedScore = isBestFit ? baseScore + 1e9 : baseScore;
                            const entry = {
                                line, tlP1, tlP2, isMatch,
                                score: boostedScore,
                                isBestFit,
                            };
                            if (isMatch) {
                                eventLineEntry = entry;
                            } else {
                                drawList.push(entry);
                            }
                        }

                        // Sort by score descending, cap to MAX_VISIBLE_LINES
                        drawList.sort((a, b) => b.score - a.score);
                        const capped = drawList.slice(0, MAX_VISIBLE_LINES);

                        // Always include the event's own line (if present, prepend it)
                        const toDraw = eventLineEntry
                            ? [eventLineEntry, ...capped]
                            : capped;

                        for (const entry of toDraw) {
                            const { line, tlP1, tlP2, isMatch } = entry;

                            // Color: up = cool blue, down = warm gold; event line = bright
                            const lineDir = String(line.direction);
                            const baseColor = lineDir === 'up' ? '#42A5F5' : '#FFB300';
                            const segColor = isMatch ? '#FFD700' : baseColor;
                            const segWidth = isMatch ? 3 : 1;
                            const segStyle = isMatch ? 0 : 2; // solid for event, dashed for others

                            const segId = ovChart.createMultipointShape([tlP1, tlP2], {
                                shape: 'trend_line',
                                lock: true,
                                disableUndo: true,
                                overrides: {
                                    linecolor: segColor,
                                    linewidth: segWidth,
                                    linestyle: segStyle,
                                },
                                zOrder: 'top',
                            });
                            if (segId) {
                                shapes.push(segId);
                                hypothesisMarkerRef.current.push(segId);
                            }

                            // For the event's line: extend from pivot B to break bar (dashed)
                            if (isMatch) {
                                const breakBarIdx = Number(event.bar_index ?? event.break_bar_index);
                                const breakTime = barTimeMap.get(breakBarIdx);
                                const lineAtBreak = Number(event.line_value_at_break);
                                if (breakTime && Number.isFinite(lineAtBreak)) {
                                    const breakP = { time: breakTime, price: rsiToPrice(lineAtBreak) };
                                    if (Number.isFinite(breakP.price)) {
                                        const extId = ovChart.createMultipointShape([tlP2, breakP], {
                                            shape: 'trend_line',
                                            lock: true,
                                            disableUndo: true,
                                            overrides: {
                                                linecolor: '#FFD700',
                                                linewidth: 2,
                                                linestyle: 2, // dashed extension
                                            },
                                            zOrder: 'top',
                                        });
                                        if (extId) {
                                            shapes.push(extId);
                                            hypothesisMarkerRef.current.push(extId);
                                        }
                                    }
                                }
                            }
                        }
                        } else if (overlayModel && overlayModel.trendlinePoints.length >= 2) {
                            // Fallback to single trendline from overlayModel
                            const linePoints = overlayModel.trendlinePoints
                                .filter((pt) => Number.isFinite(pt?.lineValue) && Number.isFinite(pt?.time))
                                .map((pt) => ({
                                    time: pt.time,
                                    price: rsiToPrice(pt.lineValue),
                                    lineValue: pt.lineValue,
                                }));

                            for (let i = 0; i < linePoints.length - 1; i++) {
                                const p1 = linePoints[i], p2 = linePoints[i + 1];
                                if (!p1 || !p2 || !Number.isFinite(p1.time) || !Number.isFinite(p1.price)
                                    || !Number.isFinite(p2.time) || !Number.isFinite(p2.price)) continue;
                                const segId = ovChart.createMultipointShape([p1, p2], {
                                    shape: 'trend_line',
                                    lock: true,
                                    disableUndo: true,
                                    overrides: {
                                        linecolor: '#FFD700',
                                        linewidth: 2,
                                        linestyle: 0,
                                    },
                                    zOrder: 'top',
                                });
                                if (segId) {
                                    shapes.push(segId);
                                    hypothesisMarkerRef.current.push(segId);
                                }
                            }

                            const startPt = linePoints[0];
                            const startRsi = linePoints[0].lineValue;
                            const startLabelId = ovChart.createShape(
                                { time: startPt.time, price: startPt.price },
                                {
                                    shape: 'label_down',
                                    lock: true, disableUndo: true,
                                    overrides: {
                                        color: '#FFD700',
                                        backgroundColor: 'rgba(0,0,0,0.7)',
                                        fontsize: 10,
                                        text: `TL:${startRsi.toFixed(1)}`,
                                    },
                                    text: `TL:${startRsi.toFixed(1)}`,
                                }
                            );
                            if (startLabelId) { shapes.push(startLabelId); hypothesisMarkerRef.current.push(startLabelId); }

                            const endPt = linePoints[linePoints.length - 1];
                            const endRsi = linePoints[linePoints.length - 1].lineValue;
                            const endLabelId = ovChart.createShape(
                                { time: endPt.time, price: endPt.price },
                                {
                                    shape: 'label_down',
                                    lock: true, disableUndo: true,
                                    overrides: {
                                        color: '#FFD700',
                                        backgroundColor: 'rgba(0,0,0,0.7)',
                                        fontsize: 10,
                                        text: `TL:${endRsi.toFixed(1)}`,
                                    },
                                    text: `TL:${endRsi.toFixed(1)}`,
                                }
                            );
                            if (endLabelId) { shapes.push(endLabelId); hypothesisMarkerRef.current.push(endLabelId); }
                        }

                        const breakPoint = overlayModel?.breakPoint;
                        if (breakPoint && Number.isFinite(breakPoint.rsi)) {
                            const breakTime = breakPoint.time;
                            const breakPrice = rsiToPrice(breakPoint.rsi);
                            const breakText = `BREAK RSI:${breakPoint.rsi.toFixed(1)} L:${Number.isFinite(breakPoint.lineValue) ? breakPoint.lineValue.toFixed(1) : '?'}`;

                            const breakMarkerId = ovChart.createShape(
                                { time: breakTime, price: breakPrice },
                                {
                                    shape: 'arrow_down',
                                    lock: true, disableUndo: true,
                                    overrides: {
                                        color: '#FF1744',
                                        backgroundColor: '#FF1744',
                                        size: 6,
                                        text: breakText,
                                    },
                                    text: breakText,
                                }
                            );
                            if (breakMarkerId) { shapes.push(breakMarkerId); hypothesisMarkerRef.current.push(breakMarkerId); }

                            const breakLabelId = ovChart.createShape(
                                { time: breakTime, price: breakPrice },
                                {
                                    shape: 'label_up',
                                    lock: true, disableUndo: true,
                                    overrides: {
                                        color: '#FFFFFF',
                                        backgroundColor: '#FF1744',
                                        fontsize: 10,
                                        text: breakText,
                                    },
                                    text: breakText,
                                }
                            );
                            if (breakLabelId) { shapes.push(breakLabelId); hypothesisMarkerRef.current.push(breakLabelId); }
                        }
                    }
                } else {
                    console.log('[TVChart] RSI trendline: no rsi_window data or candles available');
                }

                rsiStudyRef.current.shapes = shapes;
            };

            chart.setVisibleRange({ from: newFrom, to: newTo }).then(() => {
                if (isRsiEvent) {
                    setTimeout(() => drawRsiOverlay(), 200);
                }
                setTimeout(() => drawMarkerAndFan(), 400);
            }).catch(() => {
                if (isRsiEvent) {
                    drawRsiOverlay();
                }
                drawMarkerAndFan();
            });
    };

    const loadHypothesisRunCandles = async (runPath) => {
        if (!datafeedRef.current || !widgetRef.current) return;
        isLoadingRunCandlesRef.current = true;
        try {
            const resp = await fetch(`http://localhost:8005/api/hypothesis-runs/${runPath}/candles`);
            if (!resp.ok) { console.warn(`[TVChart] Failed to load run candles: ${resp.status}`); return; }
            const data = await resp.json();
            if (!data.candles || data.candles.length === 0) { console.warn('[TVChart] No candles in run'); return; }
            const resolution = String(data.resolution || '15');
            const normalized = data.candles.map(normalizeHypothesisRunCandle);
            console.log(`[TVChart] Loading ${normalized.length} run candles @ ${resolution}m into chart`);
            datafeedRef.current.setBacktestData(normalized, resolution, () => {
                isLoadingRunCandlesRef.current = false;
                loadedHypothesisRunPathRef.current = runPath;
                console.log('[TVChart] Run candles loaded into chart');
                try {
                    const chart = widgetRef.current && widgetRef.current.activeChart();
                    if (chart && shouldApplyRunCandleVisibleRange({ hasSelectedEvent: Boolean(selectedHypothesisEventRef.current) })) {
                        const firstTime = normalized[0].time / 1000;
                        const lastTime = normalized[normalized.length - 1].time / 1000;
                        chart.setVisibleRange({ from: firstTime, to: lastTime + 1800 });
                    }
                } catch (e) { console.warn('[TVChart] Failed to set visible range:', e); }
                if (pendingHypothesisEventRef.current) {
                    const pendingEvent = pendingHypothesisEventRef.current;
                    pendingHypothesisEventRef.current = null;
                    setTimeout(() => {
                        executeHypothesisNavigation(pendingEvent);
                    }, 0);
                }
            });
        } catch (e) {
            isLoadingRunCandlesRef.current = false;
            console.warn('[TVChart] Error loading run candles:', e);
        }
    };

    // Re-draw selected interaction
    useEffect(() => {
        console.log('[TVChart] selectedInteraction changed:', selectedInteraction);

        // Skip if same interaction as last processed (compare by value, not reference)
        const lastProcessed = lastProcessedInteractionRef.current;
        
        // Always reset on null to clear markers
        if (!selectedInteraction) {
            lastProcessedInteractionRef.current = null;
        } else {
            const isSameInteraction = lastProcessed && 
                lastProcessed.time === selectedInteraction.time &&
                lastProcessed.price === selectedInteraction.price &&
                lastProcessed.fanIdentity === selectedInteraction.fanIdentity;

            if (isSameInteraction) {
                console.log('[TVChart] Skipping duplicate interaction processing');
                return;
            }
            lastProcessedInteractionRef.current = selectedInteraction;
        }
        
        if (!widgetRef.current) {
            console.log('[TVChart] widgetRef.current is null');
            return;
        }

        let isCancelled = false;

        try {
            let chart;
            try {
                chart = widgetRef.current.activeChart();
            } catch (e) {
                console.log('[TVChart] activeChart not available:', e);
                return; // Chart not ready
            }

            console.log('[TVChart] Chart is ready, proceeding to draw marker');

            // Remove previous markers
            interactionMarkersRef.current.forEach(marker => {
                try {
                    chart.removeEntity(marker);
                } catch (e) {
                    console.warn('[TVChart] Failed to remove old interaction marker:', e);
                }
            });
            interactionMarkersRef.current = [];

            if (selectedInteraction) {
                const interactionTimeSec = toSeconds(selectedInteraction.time);
                console.log('[TVChart] Drawing marker for interaction time:', interactionTimeSec);
                
                // Get candles to find the exact candle this interaction belongs to
                const candles = currentCandlesRef.current || [];
                
                let targetTime = interactionTimeSec;
                let targetPrice = selectedInteraction.price;
                let matchedCandleIndex = -1;
                let candleTimesSec = [];
                
                if (candles.length > 0) {
                    candleTimesSec = candles.map(c => toSeconds(c.time));
                    
                    // Find the candle that contains this interaction time
                    // A candle contains a time if candleTime <= interactionTime < nextCandleTime
                    
                    for (let i = 0; i < candleTimesSec.length - 1; i++) {
                        if (interactionTimeSec >= candleTimesSec[i] && interactionTimeSec < candleTimesSec[i+1]) {
                            matchedCandleIndex = i;
                            break;
                        }
                    }
                    
                    // Handle edge cases (after last candle or before first)
                    if (matchedCandleIndex === -1) {
                        if (interactionTimeSec >= candleTimesSec[candleTimesSec.length - 1]) {
                            matchedCandleIndex = candleTimesSec.length - 1;
                        } else if (interactionTimeSec < candleTimesSec[0]) {
                            matchedCandleIndex = 0;
                        }
                    }
                    
                    if (matchedCandleIndex !== -1) {
                        const matchedCandle = candles[matchedCandleIndex];
                        targetTime = candleTimesSec[matchedCandleIndex];
                        // Add a gap between the icon and the candle high
                        const candleRange = parseFloat(matchedCandle.high) - parseFloat(matchedCandle.low);
                        const gapOffset = candleRange * 0.45; // 45% of candle range as gap (3x the previous 15%)
                        targetPrice = parseFloat(matchedCandle.high) + gapOffset;
                        console.log(`[TVChart] Matched to candle at ${targetTime} with high ${matchedCandle.high} -> icon at ${targetPrice.toFixed(2)}`);
                    }
                }
                
                // First, pan the chart to show this bar
                try {
                    const visibleRange = chart.getVisibleRange();
                    if (visibleRange && candles.length > 0 && matchedCandleIndex !== -1) {
                        // Find indices for current visible range to determine zoom level (number of visible bars)
                        let fromIndex = candleTimesSec.findIndex(t => t >= visibleRange.from);
                        let toIndex = candleTimesSec.findIndex(t => t >= visibleRange.to);
                        
                        if (fromIndex === -1) fromIndex = 0;
                        if (toIndex === -1) toIndex = candleTimesSec.length - 1;
                        
                        let visibleBarsCount = toIndex - fromIndex;
                        if (visibleBarsCount <= 0) visibleBarsCount = 100; // fallback
                        
                        // Check if target is outside the middle 80% of the screen
                        const barPosition = (matchedCandleIndex - fromIndex) / visibleBarsCount;
                        
                        if (barPosition < 0.1 || barPosition > 0.9) {
                            // Calculate new from/to indices to keep the exact same number of visible bars
                            let newFromIndex = Math.floor(matchedCandleIndex - visibleBarsCount / 2);
                            let newToIndex = newFromIndex + visibleBarsCount;
                            
                            // Clamp to available data
                            if (newFromIndex < 0) {
                                newFromIndex = 0;
                                newToIndex = Math.min(visibleBarsCount, candleTimesSec.length - 1);
                            }
                            if (newToIndex >= candleTimesSec.length) {
                                newToIndex = candleTimesSec.length - 1;
                                newFromIndex = Math.max(0, newToIndex - visibleBarsCount);
                            }
                            
                            const newFrom = candleTimesSec[newFromIndex];
                            const newTo = candleTimesSec[newToIndex];
                            
                            if (newFrom && newTo && newFrom < newTo) {
                                chart.setVisibleRange({ from: newFrom, to: newTo });
                            }
                        }
                    } else if (visibleRange) {
                        // Fallback if candles array is not available
                        const rangeWidth = visibleRange.to - visibleRange.from;
                        const barPosition = (targetTime - visibleRange.from) / rangeWidth;
                        
                        if (barPosition < 0.1 || barPosition > 0.9) {
                            const newFrom = targetTime - rangeWidth / 2;
                            const newTo = targetTime + rangeWidth / 2;
                            if (newFrom < newTo) {
                                chart.setVisibleRange({ from: newFrom, to: newTo });
                            }
                        }
                    }
                } catch (e) {
                    console.warn('[TVChart] Could not adjust visible range:', e);
                }
                
                // Create a combination of two shapes:
                // 1. White icon marker sitting above the candle high
                // 2. White dashed vertical line to mark the time axis
                const shapesToCreate = [
                    {
                        point: { time: targetTime, price: targetPrice },
                        options: {
                            shape: 'icon',
                            lock: true,
                            disableSelection: true,
                            disableSave: true,
                            overrides: {
                                color: '#FFFFFF',
                                size: 10,
                            },
                            icon: 0xf0ab,
                        }
                    },
                    {
                        point: { time: targetTime, price: targetPrice },
                        options: {
                            shape: 'vertical_line',
                            lock: true,
                            disableSelection: true,
                            disableSave: true,
                            overrides: {
                                color: '#FFFFFF',
                                linestyle: 2,
                                linewidth: 1,
                                showLabel: false,
                            }
                        }
                    }
                ];

                shapesToCreate.forEach(({ point, options }) => {
                    try {
                        const shapeId = chart.createShape(point, options);

                        // Handle both synchronous IDs and Promises
                        if (shapeId && typeof shapeId.then === 'function') {
                            shapeId.then(id => {
                                if (isCancelled) {
                                    // Effect was cancelled, remove the shape immediately
                                    if (id) {
                                        try { chart.removeEntity(id); } catch (e) { /* ignore */ }
                                    }
                                } else if (id) {
                                    interactionMarkersRef.current.push(id);
                                }
                            }).catch(err => console.error('[TVChart] Error creating interaction shape:', err));
                        } else if (shapeId) {
                            interactionMarkersRef.current.push(shapeId);
                        }
                    } catch (e) {
                        console.warn('[TVChart] Error creating interaction shape:', e);
                    }
                });
            }
        } catch (e) {
            console.warn('[TVChart] Error drawing interaction marker:', e);
        }

        return () => {
            isCancelled = true;
        };
    }, [selectedInteraction, isPlaying]);

    // Handle Visibility Toggles
    useEffect(() => {
        if (!widgetRef.current) return;

        let chart;
        try {
            chart = widgetRef.current.activeChart();
        } catch (innerError) {
            console.warn('[TVChart] activeChart not ready yet, skipping visibility update.');
            return; // Early return if chart is still initializing
        }

        try {
            const visibleLabels = props.visibleFanLabels || [];
            console.log('[TVChart] Updating fan visibility:', visibleLabels);

            Object.keys(fanLabelsRef.current).forEach(drawingId => {
                const identity = fanLabelsRef.current[drawingId];
                const shapeId = studyShapesRef.current[drawingId];

                if (shapeId && identity) {
                    const isVisible = visibleLabels.includes(identity) || identity === 'Unknown';
                    // processStudyResponse handles IDs that might be promises or direct
                    if (typeof shapeId === 'object' && typeof shapeId.then === 'function') {
                        shapeId.then(id => {
                            if (id) {
                                const shape = chart.getShapeById(id);
                                if (shape) shape.setProperties({ visible: isVisible });
                            }
                        });
                    } else {
                        const shape = chart.getShapeById(shapeId);
                        if (shape) shape.setProperties({ visible: isVisible });
                    }
                }
            });
        } catch (e) {
            console.warn('[TVChart] Error updating visibility:', e);
        }
    }, [props.visibleFanLabels]);

    // Helper to convert time to seconds (for TradingView shape API)
    const toSeconds = (time) => {
        if (time < 2000000000) return time; // Already seconds
        return Math.floor(time / 1000); // Convert ms to s
    };

    // Helper to convert time to milliseconds (for internal data)
    const toMilliseconds = (time) => {
        if (time > 2000000000) return time; // Already ms
        return time * 1000; // Convert s to ms
    };

    // Helper to find the matching bar time in custom data
    // This snaps trade times to actual candlestick times so shapes appear on the right bars

    // Playback Controls
    const handlePlayPause = () => {
        if (!datafeedRef.current) return;
        if (isPlaying) {
            datafeedRef.current.playback_stop();
        } else {
            datafeedRef.current.playback_start();
        }
        setIsPlaying(!isPlaying);
    };

    const handleStep = () => {
        if (datafeedRef.current) datafeedRef.current.playback_step();
    };

    const handleSpeedChange = (speed) => {
        setPlaybackSpeed(speed);
        if (datafeedRef.current) datafeedRef.current.playback_set_speed(speed);
    };

    // Store the current candles for time matching in plotTradeShape
    const currentCandlesRef = useRef([]);

    // Track recent marker positions to prevent stacking
    // Key: time bucket (rounded to nearest 5 min), Value: array of { price, type, offsetLevel }
    const recentMarkersRef = useRef({});

    // Track which trades have been plotted to prevent duplicate markers
    // Key: unique trade identifier (time_type_price), Value: true
    const plottedTradesRef = useRef({});
    const tradeShapeIdsRef = useRef([]);

    const clearTradeMarkerShapes = (chart) => {
        tradeShapeIdsRef.current.forEach(id => {
            try { chart.removeEntity(id); } catch (_) {}
        });
        tradeShapeIdsRef.current = [];
        tradeMarkersRef.current = {};
        plottedTradesRef.current = {};
        recentMarkersRef.current = {};
    };

    const plotSingleTradeMarker = (chart, trade) => {
        const isLong = trade.side === 'LONG';

        if (trade.entry_time && trade.entry_price) {
            const entryMarker = {
                time: trade.entry_time,
                type: 'entry',
                price: trade.entry_price,
                side: trade.side,
                isBuy: isLong
            };
            plotTradeShape(chart, entryMarker);
        }
        
        if (trade.exit_time && trade.exit_price) {
            const exitMarker = {
                time: trade.exit_time,
                type: 'exit',
                price: trade.exit_price,
                side: trade.side,
                isBuy: !isLong
            };
            plotTradeShape(chart, exitMarker);
        }
    };

    // Track pattern label markers to prevent stacking
    // Key: time bucket, Value: array of { price, time }
    const patternMarkersRef = useRef({});

    // Handle pattern dots visibility toggle
    useEffect(() => {
        console.log('[TVChart] Pattern dots toggle changed: showPatternDots =', showPatternDots);

        if (!widgetRef.current) {
            console.log('[TVChart] widgetRef.current is null, skipping');
            return;
        }

        let chart;
        try {
            chart = widgetRef.current.activeChart();
        } catch (innerError) {
            console.warn('[TVChart] activeChart not ready yet, skipping pattern dots visibility update.');
            return;
        }
        if (!chart) {
            console.log('[TVChart] chart is null, skipping');
            return;
        }

        // Iterate all pattern markers and toggle visibility
        const buckets = patternMarkersRef.current;
        const bucketKeys = Object.keys(buckets);
        console.log('[TVChart] Pattern markers buckets:', bucketKeys.length, bucketKeys);

        if (bucketKeys.length === 0) {
            console.log('[TVChart] No pattern markers to toggle');
        }

        bucketKeys.forEach(bucketKey => {
            const markers = buckets[bucketKey];
            console.log(`[TVChart] Bucket ${bucketKey} has ${markers.length} markers`);
            markers.forEach(marker => {
                console.log('[TVChart] Processing marker:', marker);
                if (marker.shapeId) {
                    try {
                        const shape = chart.getShapeById(marker.shapeId);
                        if (shape) {
                            shape.setProperties({ visible: showPatternDots });
                        }
                    } catch (e) {
                        console.warn('[TVChart] Error toggling shape:', e.message);
                    }
                }
            });
        });
    }, [showPatternDots]);

    const loadTradeFanGeometry = (chart, trade) => {
        if (!chart || !trade?.fan_geometry) return;

        clearAllStudyDrawings(chart, studyShapesRef.current);
        studyShapesRef.current = {};
        Object.values(indicatorLinesRef.current).forEach(ids => {
            const idList = Array.isArray(ids) ? ids : [ids];
            idList.forEach(id => { try { chart.removeEntity(id); } catch (e) {} });
        });
        indicatorLinesRef.current = {};

        const g = trade.fan_geometry;

        const studyData = {
            drawings: (g.rays || []).map(ray => ({
                id: ray.id || `${trade.fan || 'fan'}_ray`,
                type: 'trend_line',
                points: ray.points || [],
                options: {
                    linecolor: ray.color || '#2196F3',
                    linewidth: ray.width || 2,
                    linestyle: 0,
                    extendRight: true,
                    fanIdentity: trade.fan || '',
                    fanLabel: trade.fan || ''
                }
            })),
            pivot_markers: (() => {
                const markers = [];
                if (g.origin?.time) {
                    markers.push({
                        type: g.origin.label === 'high' ? 'pivot_high' : 'pivot_low',
                        time: g.origin.time,
                        price: g.origin.price,
                        text: trade.fan || ''
                    });
                }
                if (g.anchor?.time) {
                    markers.push({
                        type: g.anchor.label === 'high' ? 'pivot_high' : 'pivot_low',
                        time: g.anchor.time,
                        price: g.anchor.price
                    });
                }
                return markers;
            })()
        };

        studyShapesRef.current = processStudyResponse(chart, studyData, studyShapesRef.current);
    };

    // Plot a single trade shape - now accepts optional candles for time snapping
    const plotTradeShape = (chart, trade, candles = null) => {
        // Validate trade data before calling TradingView API
        if (!trade || trade.time === undefined || trade.time === null || trade.price === undefined || trade.price === null) {
            console.warn("Invalid trade data, skipping:", trade);
            return false;
        }

        const tradeKey = `${trade.time}_${trade.type}_${trade.price}`;
        if (plottedTradesRef.current[tradeKey]) {
            return false;
        }
        plottedTradesRef.current[tradeKey] = true;

        const isEntry = trade.type === 'entry';
        const isExit = trade.type === 'exit';
        const color = isEntry ? '#2196F3' : isExit ? '#FF9800' : '#FF9800'; // Blue for entry, Orange for exit
        
        let isBuy = trade.isBuy;
        if (isBuy === undefined) {
            if (trade.type === 'buy') isBuy = true;
            else if (trade.type === 'sell') isBuy = false;
            else if (trade.type === 'entry' && trade.side === 'LONG') isBuy = true;
            else if (trade.type === 'entry' && trade.side === 'SHORT') isBuy = false;
            else if (trade.type === 'exit' && trade.side === 'LONG') isBuy = false;
            else if (trade.type === 'exit' && trade.side === 'SHORT') isBuy = true;
            else isBuy = true; // Fallback
        }

        const shapeTime = toSeconds(trade.time);
        const shapePrice = trade.price;

        // Find matching candle to scale the line
        const allCandles = candles || currentCandlesRef.current || [];
        let matchedCandle = null;
        if (allCandles.length > 0) {
            const candleTimesSec = allCandles.map(c => toSeconds(c.time));
            let matchedIndex = -1;
            for (let i = 0; i < candleTimesSec.length - 1; i++) {
                if (shapeTime >= candleTimesSec[i] && shapeTime < candleTimesSec[i + 1]) {
                    matchedIndex = i;
                    break;
                }
            }
            if (matchedIndex === -1) {
                if (shapeTime >= candleTimesSec[candleTimesSec.length - 1]) matchedIndex = candleTimesSec.length - 1;
                else if (shapeTime < candleTimesSec[0]) matchedIndex = 0;
            }
            if (matchedIndex !== -1) {
                matchedCandle = allCandles[matchedIndex];
            }
        }
        
        // Fallback to datafeed if candle not found in current view
        if (!matchedCandle && datafeedRef.current && typeof datafeedRef.current.getBarAtTime === 'function') {
            matchedCandle = datafeedRef.current.getBarAtTime(shapeTime);
        }

        let price1, price2;
        // Use a fixed percentage of the price to ensure consistent gap and line length
        // regardless of the individual candle's size.
        const gap = shapePrice * 0.0015;
        const length = shapePrice * 0.00125; // Reduced length to half

        if (matchedCandle) {
            if (isBuy) {
                price1 = parseFloat(matchedCandle.low) - gap;
                price2 = parseFloat(matchedCandle.low) - gap - length;
            } else {
                price1 = parseFloat(matchedCandle.high) + gap;
                price2 = parseFloat(matchedCandle.high) + gap + length;
            }
        } else {
            if (isBuy) {
                price1 = shapePrice - gap;
                price2 = shapePrice - gap - length;
            } else {
                price1 = shapePrice + gap;
                price2 = shapePrice + gap + length;
            }
        }

        const tradeDate = new Date(trade.time * 1000);
        const dateStr = tradeDate.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' });
        const timeStr = tradeDate.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false });

        console.log(`[plotTradeShape] ${trade.type.toUpperCase()} at ${dateStr} ${timeStr}, time=${shapeTime}, isBuy=${isBuy}`);

        try {
            const createdShape = chart.createMultipointShape(
                [{ time: shapeTime, price: price1 }, { time: shapeTime, price: price2 }],
                {
                    shape: 'trend_line',
                    lock: true,
                    disableUndo: true,
                    overrides: {
                        linecolor: color,
                        linewidth: 3,
                        linestyle: 0
                    }
                }
            );

            const storeId = (id) => {
                if (id) tradeShapeIdsRef.current.push(id);
            };
            if (createdShape && typeof createdShape.then === 'function') {
                createdShape.then(storeId).catch(() => {});
            } else if (createdShape) {
                storeId(createdShape);
            }

            if (trade.fan_geometry) {
                tradeMarkersRef.current[`${shapeTime}_${shapePrice}`] = trade;
            }
            return true;
        } catch (err) {
            console.error("[plotTradeShape] Error creating shape:", err);
            return false;
        }
    };

    // Pattern color map
    const PATTERN_COLORS = {
        'PINBAR':          '#00BCD4',  // Cyan
        'DOJI':            '#FFEB3B',  // Yellow
        'SHOOTING_STAR':   '#E91E63',  // Magenta
        'INVERTED_HAMMER': '#AEEA00',  // Lime
        'MARUBOZU':        '#E0E0E0',  // White
        'SPINNING_TOP':    '#F48FB1',  // Pink
    };

    // Position logic: bearish/neutral above, bullish below
    const PATTERN_POSITION = {
        'PINBAR': 'above',
        'SHOOTING_STAR': 'above',
        'MARUBOZU': 'above',
        'DOJI': 'above',
        'SPINNING_TOP': 'above',
        'INVERTED_HAMMER': 'below'
    };

    const plotPatternLabel = (chart, pattern, candle, intervalSeconds = 60) => {
        if (!chart || !pattern || pattern === 'NO_PATTERN' || !candle) return false;

        const patternColor = PATTERN_COLORS[pattern];
        if (!patternColor) return false;

        const position = PATTERN_POSITION[pattern] || 'above';
        const candleTime = toSeconds(candle.time);
        console.log(`[plotPatternLabel] candleTime=${candleTime}, date=${new Date(candleTime * 1000).toLocaleString()}`);
        const candleHigh = parseFloat(candle.high);
        const candleLow = parseFloat(candle.low);

        // Add a gap between the circle and candle high/low
        const candleRange = candleHigh - candleLow;
        const gapOffset = candleRange * 0.15; // 15% of candle range as gap
        const shapePrice = position === 'below' ? candleLow - gapOffset : candleHigh + gapOffset;

        // Time bucket stacking prevention (same as trade shapes)
        const timeBucket = Math.floor(candleTime / 300) * 300;
        const bucketKey = `${timeBucket}_pattern_${pattern}`;
        if (!patternMarkersRef.current) patternMarkersRef.current = {};
        if (!patternMarkersRef.current[bucketKey]) patternMarkersRef.current[bucketKey] = [];

        // Check if this exact pattern is already tracked in this bucket
        const existingMarker = patternMarkersRef.current[bucketKey].find(m => m.pattern === pattern);
        if (existingMarker) {
            console.log(`[plotPatternLabel] Skipping duplicate ${pattern} dot at ${new Date(candleTime * 1000).toLocaleString()}`);
            return false; // Already created
        }

        console.log(`[plotPatternLabel] ${pattern} dot at ${new Date(candleTime * 1000).toLocaleString()}, price=${shapePrice.toFixed(2)}, color=${patternColor}`);

        try {
            const shapeType = position === 'below' ? 'arrow_up' : 'arrow_down';
            const shapeIdOrPromise = chart.createShape({ time: candleTime, price: shapePrice }, {
                shape: shapeType,
                lock: true,
                disableSelection: true,
                disableSave: true,
                overrides: {
                    color: patternColor,
                    backgroundColor: patternColor,
                    borderColor: patternColor,
                    size: 1, // smaller marker for patterns
                }
            });

            // Handle both synchronous IDs and Promises
            if (shapeIdOrPromise && typeof shapeIdOrPromise.then === 'function') {
                // It's a Promise, resolve it before storing
                shapeIdOrPromise.then(resolvedId => {
                    console.log(`[plotPatternLabel] Shape created with ID: ${resolvedId}`);
                    patternMarkersRef.current[bucketKey].push({ price: shapePrice, time: candleTime, pattern, shapeId: resolvedId });
                    
                    // If showPatternDots is currently false, explicitly hide the new shape
                    if (!showPatternDots) {
                        try {
                            const shape = chart.getShapeById(resolvedId);
                            if (shape) shape.setProperties({ visible: false });
                        } catch(e) {}
                    }
                }).catch(err => console.warn("[plotPatternLabel] Error resolving shape promise:", err.message));
            } else {
                // Direct ID
                console.log(`[plotPatternLabel] Shape created with direct ID: ${shapeIdOrPromise}`);
                patternMarkersRef.current[bucketKey].push({ price: shapePrice, time: candleTime, pattern, shapeId: shapeIdOrPromise });
                
                // If showPatternDots is currently false, explicitly hide the new shape
                if (!showPatternDots) {
                    try {
                        const shape = chart.getShapeById(shapeIdOrPromise);
                        if (shape) shape.setProperties({ visible: false });
                    } catch(e) {}
                }
            }
            return true;
        } catch (err) {
            console.warn("[plotPatternLabel] Error creating dot:", err.message);
            return false;
        }
    };

    // --- ADDED: Extract available fan identities from incoming drawings ---
    // Tracks identity -> latest display label mapping
    const fanDisplayMapRef = useRef({});

    const clearAvailableFans = () => {
        fanDisplayMapRef.current = {};
        if (props.onAvailableFansUpdated) {
            props.onAvailableFansUpdated([]);
        }
    };

    const updateAvailableFans = (drawings) => {
        if (!props.onAvailableFansUpdated) return;

        if (!drawings || !Array.isArray(drawings)) return;

        let foundNew = false;
        let newIdentities = [];

        drawings.forEach(d => {
            if (d.options && d.options.fanIdentity && d.options.fanIdentity !== 'Unknown') {
                const identity = d.options.fanIdentity;
                const displayLabel = d.options.fanLabel || identity;

                // Always update the display label (it may change as priorities shift)
                fanDisplayMapRef.current[identity] = displayLabel;

                // Track if this is a brand new identity
                if (!fanLabelsRef.current || !Object.values(fanLabelsRef.current).includes(identity)) {
                    // Check if we already know about this identity
                    const existingIdentities = new Set(Object.values(fanLabelsRef.current || {}));
                    if (!existingIdentities.has(identity)) {
                        foundNew = true;
                        newIdentities.push(identity);
                    }
                }
            }
        });

        // Always rebuild the available fans list with latest display labels
        const allIdentities = Object.keys(fanDisplayMapRef.current);
        if (allIdentities.length > 0) {
            const fanObjects = allIdentities
                .map(id => ({ identity: id, displayLabel: fanDisplayMapRef.current[id] }))
                .sort((a, b) => {
                    // Sort by priority number extracted from displayLabel
                    const matchA = a.displayLabel.match(/^P(\d+)/);
                    const matchB = b.displayLabel.match(/^P(\d+)/);
                    const numA = matchA ? parseInt(matchA[1]) : 999;
                    const numB = matchB ? parseInt(matchB[1]) : 999;
                    return numA - numB;
                });

            props.onAvailableFansUpdated(fanObjects);

            // Auto-enable visibility for newly discovered fans
            if (foundNew && newIdentities.length > 0 && props.onAutoEnableVisibility) {
                props.onAutoEnableVisibility(newIdentities);
            }
        }
    };

    // Expose methods to parent (App.jsx)
    useImperativeHandle(ref, () => ({
        // Get current chart resolution
        // Get current chart resolution
        getResolution: () => {
            if (widgetRef.current) {
                try {
                    const res = widgetRef.current.activeChart().resolution();
                    console.log(`[TVChart] getResolution calls -> Widget reports: ${res}`);
                    return res;
                } catch (e) {
                    console.warn("[TVChart] Failed to get resolution from active widget:", e);
                }
            }
            console.log(`[TVChart] Widget not ready or failed, falling back to prop interval: ${interval}`);
            return interval || '1'; // Default to prop or '1'
        },

        // Get chart's Price-to-Bar ratio for angle calculations
        getPriceToBarRatio: () => {
            if (widgetRef.current) {
                try {
                    const ratio = widgetRef.current.activeChart().getPriceToBarRatio();
                    console.log("[TVChart] Price-to-Bar ratio:", ratio);
                    return ratio;
                } catch (e) {
                    console.warn("[TVChart] Failed to get price-to-bar ratio:", e);
                }
            }
            return null; // Let backend use default
        },

        // --- ADDED: Extract available fan labels from incoming drawings ---
        updateAvailableFans: updateAvailableFans,

        // Navigate to a hypothesis event: pan chart, draw arrow marker, render fan geometry
        navigateToHypothesisEvent: (event) => {
            const requestedRunPath = props.hypothesisRunPath || null;
            const hasCustomData = Boolean(datafeedRef.current?.customData?.length);
            const isCustomMode = Boolean(datafeedRef.current?.isCustomMode);
            if (shouldLoadHypothesisRunCandles({
                requestedRunPath,
                loadedRunPath: loadedHypothesisRunPathRef.current,
                hasCustomData,
                isCustomMode,
                isLoadingRunCandles: isLoadingRunCandlesRef.current,
            })) {
                pendingHypothesisEventRef.current = event;
                if (requestedRunPath) {
                    loadHypothesisRunCandles(requestedRunPath);
                }
                return;
            }
            if (!widgetRef.current) return;
            if (shouldDeferHypothesisNavigation({
                hasCustomData,
                isLoadingRunCandles: isLoadingRunCandlesRef.current,
            })) {
                pendingHypothesisEventRef.current = event;
                return;
            }
            executeHypothesisNavigation(event);
        },

        navigateToTrade: (trade) => {
            if (!widgetRef.current || !trade) return;
            const chart = widgetRef.current.activeChart();
            if (!chart) return;

            clearTradeMarkerShapes(chart);

            const g = trade.fan_geometry;
            let centerTime = trade.entry_time || trade.time;
            if (g?.origin?.time) {
                centerTime = g.origin.time;
            }

            let rangeWidth = 28 * 3600;
            try {
                const visibleRange = chart.getVisibleRange();
                if (visibleRange && visibleRange.to - visibleRange.from > 0) {
                    rangeWidth = visibleRange.to - visibleRange.from;
                }
            } catch (_) {}

            const newFrom = centerTime - rangeWidth / 2;
            const newTo = centerTime + rangeWidth / 2;

            chart.setVisibleRange({ from: newFrom, to: newTo }).then(() => {
                setTimeout(() => {
                    loadTradeFanGeometry(chart, trade);
                    plotSingleTradeMarker(chart, trade);
                }, 400);
            }).catch(() => {
                loadTradeFanGeometry(chart, trade);
                plotSingleTradeMarker(chart, trade);
            });
        },

        clearTradeMarkers: () => {
            if (!widgetRef.current) return;
            const chart = widgetRef.current.activeChart();
            if (!chart) return;
            clearTradeMarkerShapes(chart);
        },

        // INSTANT MODE: Plot all candles and signals at once
        startBacktestInstant: (candles, trades, resolution = '1', markers = [], drawings = [], indicator_series = null) => {
            console.log("Starting Instant Backtest", candles.length, "candles,", trades.length, "trades, resolution:", resolution);
            console.log("Instant Study Data:", markers.length, "markers,", drawings.length, "drawings");

            if (!datafeedRef.current || !widgetRef.current) {
                console.error("Chart not ready");
                return;
            }

            // Clear old study UI state
            clearAvailableFans();
            studyShapesRef.current = {};

            // Clear existing indicator lines
            try {
                const chart = widgetRef.current.activeChart();
                Object.values(indicatorLinesRef.current).forEach(ids => {
                    const idList = Array.isArray(ids) ? ids : [ids];
                    idList.forEach(id => {
                        try { chart.removeEntity(id); } catch (e) { /* ignore */ }
                    });
                });
            } catch (e) { /* ignore */ }
            indicatorLinesRef.current = {};

            // Ensure candle times are in milliseconds for datafeed
            const normalizedCandles = candles.map(c => ({
                ...c,
                time: toMilliseconds(c.time)
            }));

            // CRITICAL: Store candles for trade time matching
            currentCandlesRef.current = normalizedCandles;

            // Store trades
            tradesRef.current = trades;

            // Helper: Find nearest candle time for a trade time
            const snapToNearestCandle = (tradeTimeSec, candlesMs) => {
                // Convert to seconds for comparison
                const candleTimesSec = candlesMs.map(c => toSeconds(c.time));

                // Find the candle with the closest time
                let closestTime = candleTimesSec[0];
                let minDiff = Math.abs(tradeTimeSec - closestTime);

                for (let i = 1; i < candleTimesSec.length; i++) {
                    const diff = Math.abs(tradeTimeSec - candleTimesSec[i]);
                    if (diff < minDiff) {
                        minDiff = diff;
                        closestTime = candleTimesSec[i];
                    }
                    // Early exit if we've passed the trade time (candles are sorted)
                    if (candleTimesSec[i] > tradeTimeSec + 3600) break;
                }

                return closestTime;
            };

            // Load data into datafeed with resolution
            // CRITICAL FIX: Pass callback to plot markers AFTER data finishes loading
            datafeedRef.current.setBacktestData(normalizedCandles, resolution, () => {
                console.log("===BACKTEST DATA LOADED===");

                const chart = widgetRef.current.activeChart();
                chart.removeAllShapes();
                recentMarkersRef.current = {};
                patternMarkersRef.current = {};
                studyShapesRef.current = {}; // Clear study shapes
                fanLabelsRef.current = {};
                fanDisplayMapRef.current = {};
                indicatorLinesRef.current = {};

                // CRITICAL FIX: Set visible range FIRST to force TradingView to index all bars
                // This ensures that when we call createShape later, the bars exist in the chart
                if (normalizedCandles.length > 0) {
                    const firstTime = toSeconds(normalizedCandles[0].time);
                    const lastTime = toSeconds(normalizedCandles[normalizedCandles.length - 1].time);

                    console.log(`[FIX] Setting visible range FIRST: ${new Date(firstTime * 1000).toISOString()} to ${new Date(lastTime * 1000).toISOString()}`);

                    chart.setVisibleRange({
                        from: firstTime,
                        to: lastTime + (30 * 60)
                    }).then(() => {
                        console.log("[FIX] Visible range set - now waiting for bars to be indexed...");

                        // Wait a bit for TradingView to fully index the bars after range change
                        setTimeout(() => {
                            console.log("[FIX] Now plotting markers/trades (post-range-set)...");

                            // Plot all trades - snap each trade time to nearest candle
                            let plotted = 0;
                            trades.forEach(t => {
                                try {
                                    // Create a modified trade with snapped time
                                    const snappedTime = snapToNearestCandle(toSeconds(t.time), normalizedCandles);
                                    const snappedTrade = { ...t, time: snappedTime };

                                    if (plotTradeShape(chart, snappedTrade)) {
                                        plotted++;
                                        if (onTradeLogged) onTradeLogged(t); // Log original trade data
                                    }
                                } catch (err) {
                                    console.warn("Failed to plot trade:", t, err);
                                }
                            });
                            console.log(`Successfully plotted ${plotted}/${trades.length} trades`);

                            // PLOT STUDY MARKERS (Pivots/Drawings)
                            if (markers.length > 0 || drawings.length > 0) {
                                console.log(`Plotting ${markers.length} study markers and ${drawings.length} drawings`);
                                try {
                                    updateAvailableFans(drawings);

                                    studyShapesRef.current = processStudyResponse(chart, {
                                        pivot_markers: markers,
                                        drawings: drawings
                                    }, studyShapesRef.current);

                                    // Track Fan Labels & Apply Visibility
                                    const visibleLabels = visibleFanLabelsRef.current;
                                    drawings.forEach(d => {
                                        if (d.options && (d.options.fanIdentity || d.options.fanLabel)) {
                                            const identity = d.options.fanIdentity || d.options.fanLabel;
                                            fanLabelsRef.current[d.id] = identity;

                                            // Apply immediate visibility
                                            const shapeId = studyShapesRef.current[d.id];
                                            const isVisible = visibleLabels.includes(identity);

                                            if (shapeId) {
                                                if (typeof shapeId === 'object' && typeof shapeId.then === 'function') {
                                                    shapeId.then(id => {
                                                        if (id) {
                                                            const shape = chart.getShapeById(id);
                                                            if (shape) shape.setProperties({ visible: isVisible });
                                                        }
                                                    });
                                                } else {
                                                    const shape = chart.getShapeById(shapeId);
                                                    if (shape) shape.setProperties({ visible: isVisible });
                                                }
                                            }
                                        }
                                    });

                                } catch (studyErr) {
                                    console.error("Error plotting study data:", studyErr);
                                }
                            }

                            // Render indicator lines (EMA 9, EMA 21) on instant backtest
                            if (indicator_series && chart) {
                                const colors = { ema_9: '#2196F3', ema_21: '#FF9800' };
                                const labels = { ema_9: 'EMA 9', ema_21: 'EMA 21' };
                                Object.entries(indicator_series).forEach(([key, data]) => {
                                    if (!data || data.length === 0) return;
                                    const points = data.filter(p => p.time && (p.value != null)).map(p => ({
                                        time: toSeconds(p.time),
                                        price: p.value
                                    })).sort((a, b) => a.time - b.time);
                                    if (points.length > 1) {
                                        if (indicatorLinesRef.current[key]) {
                                            try { chart.removeEntity(indicatorLinesRef.current[key]); } catch (e) {}
                                        }
                                        const id = chart.createMultipointShape(points, {
                                            shape: 'polyline',
                                            zOrder: 'top',
                                            color: colors[key] || '#888888',
                                            lineWidth: 2,
                                        });
                                        indicatorLinesRef.current[key] = id;
                                    }
                                });
                            }

                        }, 500); // 500ms delay to allow bar indexing
                    }).catch(err => {
                        console.error("Error setting visible range:", err);
                        // Fall back to plotting without range set
                        trades.forEach(t => {
                            try {
                                if (plotTradeShape(chart, t)) {
                                    if (onTradeLogged) onTradeLogged(t);
                                }
                            } catch (err2) {
                                console.warn("Failed to plot trade:", t, err2);
                            }
                        });

                        // Fallback study plotting
                        if (markers.length > 0 || drawings.length > 0) {
                            try {
                                updateAvailableFans(drawings);
                                studyShapesRef.current = processStudyResponse(chart, {
                                    pivot_markers: markers,
                                    drawings: drawings
                                }, studyShapesRef.current);
                            } catch (studyErr) {
                                console.error("Error plotting study data:", studyErr);
                            }
                        }

                        // Render indicator lines fallback (EMA 9, EMA 21)
                        if (indicator_series && chart) {
                            const colors = { ema_9: '#2196F3', ema_21: '#FF9800' };
                            Object.entries(indicator_series).forEach(([key, data]) => {
                                if (!data || data.length === 0) return;
                                const points = data.filter(p => p.time && (p.value != null)).map(p => ({
                                    time: toSeconds(p.time),
                                    price: p.value
                                })).sort((a, b) => a.time - b.time);
                                if (points.length > 1) {
                                    if (indicatorLinesRef.current[key]) {
                                        try { chart.removeEntity(indicatorLinesRef.current[key]); } catch (e) {}
                                    }
                                    const id = chart.createMultipointShape(points, {
                                        shape: 'polyline',
                                        zOrder: 'top',
                                        color: colors[key] || '#888888',
                                        lineWidth: 2,
                                    });
                                    indicatorLinesRef.current[key] = id;
                                }
                            });
                        }
                    });
                } else {
                    console.warn("No candles to set visible range");
                }
            });

            // Skip the old onChartReady/dataReady logic below - callback handles everything
            setIsPlaybackMode(false);
        },

        // REPLAY MODE: Start candle-by-candle playback
        startBacktestReplay: (candles, trades, resolution = '1', replayStartTimestamp = null, onProgressCallback = null) => {
            console.log("Starting Replay Mode", candles.length, "candles,", trades.length, "trades, resolution:", resolution);
            if (replayStartTimestamp) {
                console.log("Replay will start from timestamp:", replayStartTimestamp, "date:", new Date(replayStartTimestamp * 1000).toISOString());
            }

            if (!datafeedRef.current || !widgetRef.current) {
                console.error("Chart not ready");
                return;
            }

            // Clear old study UI state
            clearAvailableFans();
            studyShapesRef.current = {};

            // Clear existing indicator lines
            try {
                const chart = widgetRef.current.activeChart();
                Object.values(indicatorLinesRef.current).forEach(ids => {
                    const idList = Array.isArray(ids) ? ids : [ids];
                    idList.forEach(id => {
                        try { chart.removeEntity(id); } catch (e) { /* ignore */ }
                    });
                });
            } catch (e) { /* ignore */ }
            indicatorLinesRef.current = {};

            // TradingView-style replay logic:
            // 1. Show ALL candles for context (don't filter)
            // 2. Set the replay "current step" to the start date index
            // 3. Filter trades to only appear from the replay point forward

            let replayStartIndex = 0; // Default: start from beginning
            let filteredTrades = trades;

            if (replayStartTimestamp) {
                // Find the index where replay should start
                const foundIndex = candles.findIndex(c => {
                    const candleTime = toSeconds(c.time);
                    return candleTime >= replayStartTimestamp;
                });

                if (foundIndex !== -1) {
                    // Show context: Start showing from ~50 candles before the replay point
                    // This gives users chart context before the replay starts
                    // Start exactly from the previous candle (yesterday's close)
                    replayStartIndex = Math.max(0, foundIndex - 1);

                    console.log(`[Replay] Replay point at candle index ${foundIndex}`);
                    console.log(`[Replay] Showing context from index ${replayStartIndex} (${foundIndex - replayStartIndex} candles before replay point)`);
                    console.log(`[Replay] Initial visible range: ${new Date(candles[replayStartIndex].time * 1000).toLocaleString()} to ${new Date(candles[foundIndex].time * 1000).toLocaleString()}`);

                    // Filter trades to only include those AT OR AFTER the replay start time
                    filteredTrades = trades.filter(t => t.time >= replayStartTimestamp);
                    console.log(`[Replay] Filtered trades: ${filteredTrades.length}/${trades.length} trades from replay point forward`);
                } else {
                    console.warn("[Replay] Could not find candle matching replay start timestamp, starting from beginning");
                }
            } else {
                console.log("[Replay] No start date specified, replaying from beginning");
            }

            // Ensure candle times are in milliseconds
            const normalizedCandles = candles.map(c => ({
                ...c,
                time: toMilliseconds(c.time)
            }));

            // CRITICAL: Store ALL candles for chart rendering
            currentCandlesRef.current = normalizedCandles;

            // Store filtered trades (only from replay point forward)
            tradesRef.current = filteredTrades;

            // Configure datafeed for replay with trade callback and resolution
            datafeedRef.current.setBacktestDataForReplay(
                normalizedCandles,
                filteredTrades,
                (trade) => {
                    // This callback fires when a trade time is reached during replay
                    const chart = widgetRef.current.activeChart();
                    console.log("[Replay] Trade callback triggered for:", trade.type, "at", new Date(trade.time * 1000).toLocaleString());
                    plotTradeShape(chart, trade, normalizedCandles);
                    if (onTradeLogged) onTradeLogged(trade);
                },
                resolution,
                replayStartIndex, // Pass the starting index to datafeed
                onProgressCallback // Pass progress callback to datafeed
            );

            widgetRef.current.onChartReady(() => {
                const chart = widgetRef.current.activeChart();
                chart.removeAllShapes();
                recentMarkersRef.current = {}; // Clear marker tracking
                patternMarkersRef.current = {};
                plottedTradesRef.current = {};  // Reset trade tracking for new replay

                console.log("[Replay] Chart ready - cleared existing shapes");


            });

            setIsPlaybackMode(true);
            setIsPlaying(false);
        },

        // PROGRESSIVE REPLAY MODE: Evaluate strategy dynamically as candles appear
        startProgressiveReplay: (candles, strategy, resolution, replayStartTimestamp, datafeedUrl, instrumentType, onProgressCallback, onTradeCallback, pivotSettings = {}) => {
            console.log("[Progressive Replay] Starting with", candles.length, "candles, strategy:", strategy, "instrument:", instrumentType, "pivotSettings:", pivotSettings);

            if (!datafeedRef.current || !widgetRef.current) {
                console.error("Chart not ready");
                return;
            }

            let replayStartIndex = 0;

            if (replayStartTimestamp) {
                const foundIndex = candles.findIndex(c => {
                    const candleTime = toSeconds(c.time);
                    return candleTime >= replayStartTimestamp;
                });

                if (foundIndex !== -1) {
                    // Start exactly from the previous candle (yesterday's close)
                    replayStartIndex = Math.max(0, foundIndex - 1);
                    console.log(`[Progressive Replay] Replay point at index ${foundIndex}, starting from ${replayStartIndex} (with context)`);
                } else {
                    // If start date is AFTER all available data (e.g. future date or weekend gap at end),
                    // start from the very last candle so full history is visible.
                    replayStartIndex = Math.max(0, candles.length - 1);
                    console.log(`[Progressive Replay] Replay start time ${replayStartTimestamp} is beyond data range. Starting from end: index ${replayStartIndex}`);
                }
            }

            const normalizedCandles = candles.map(c => ({
                ...c,
                time: toMilliseconds(c.time)
            }));

            currentCandlesRef.current = normalizedCandles;

            // Start with null scale ratio - will be updated when chart is ready
            let scaleRatio = null;

            // Set up the progressive replay data first (without scale ratio)
            datafeedRef.current.setProgressiveReplayData(
                normalizedCandles,
                strategy,
                datafeedUrl,
                replayStartIndex,
                onProgressCallback,
                (trade) => {
                    // Safety check: ensure widget is ready before plotting
                    if (!widgetRef.current) {
                        console.warn("[Progressive Replay] Widget not ready, skipping trade plot");
                        if (onTradeCallback) onTradeCallback(trade);
                        return;
                    }
                    try {
                        const chart = widgetRef.current.activeChart();
                        console.log("[Progressive Replay] Trade signal:", trade.type, "at", new Date(trade.time * 1000).toLocaleString());
                        plotTradeShape(chart, trade, normalizedCandles);
                    } catch (err) {
                        console.warn("[Progressive Replay] Error plotting trade:", err.message);
                    }
                    if (onTradeCallback) onTradeCallback(trade);
                },
                resolution,
                instrumentType,
                // Study callback - handles drawing_update responses
                (studyData) => {
                    if (!widgetRef.current) {
                        console.warn("[Study] Widget not ready, skipping drawings");
                        return;
                    }
                    try {
                        const chart = widgetRef.current.activeChart();
                        studyShapesRef.current = processStudyResponse(chart, studyData, studyShapesRef.current);

                        // Render indicator lines (EMA 9, EMA 21) from indicator_series
                        // OPTIMIZED: Only draw the one new segment each step instead of
                        // removing and recreating ALL segments (was O(n²) API calls per step).
                        if (studyData.indicator_series && chart) {
                            const colors = { ema_9: '#2196F3', ema_21: '#FF9800' };

                            Object.entries(studyData.indicator_series).forEach(([key, data]) => {
                                if (!data || data.length < 2) return;

                                const points = data.map(p => ({
                                    time: p.time,
                                    price: p.value
                                })).filter(p => p.time != null && p.price != null && !isNaN(p.time) && !isNaN(p.price));

                                if (points.length < 2) return;

                                const overrideColor = colors[key] || '#888888';
                                const options = {
                                    shape: 'trend_line',
                                    lock: true,
                                    disableUndo: true,
                                    overrides: {
                                        linecolor: overrideColor,
                                        linewidth: 1,
                                        linestyle: 0
                                    },
                                    zOrder: 'top'
                                };

                                // Track how many segments exist for incremental updates
                                if (!indicatorLinesRef.current[key]) {
                                    indicatorLinesRef.current[key] = [];
                                }
                                const existingSegments = indicatorLinesRef.current[key];
                                const existingCount = existingSegments.length;
                                const totalSegmentsNeeded = points.length - 1;

                                // If we somehow lost segments or this is a replay restart, rebuild
                                if (existingCount === 0 || existingCount >= totalSegmentsNeeded) {
                                    existingSegments.forEach(id => {
                                        try { chart.removeEntity(id); } catch (e) { /* ignore */ }
                                    });
                                    const newSegments = [];
                                    for (let i = 0; i < totalSegmentsNeeded; i++) {
                                        const result = chart.createMultipointShape(
                                            [points[i], points[i + 1]],
                                            options
                                        );
                                        if (result) newSegments.push(result);
                                    }
                                    indicatorLinesRef.current[key] = newSegments;
                                } else {
                                    // Incremental: only add the one new segment
                                    const i = existingCount;
                                    if (i < totalSegmentsNeeded) {
                                        const result = chart.createMultipointShape(
                                            [points[i], points[i + 1]],
                                            options
                                        );
                                        if (result) existingSegments.push(result);
                                    }
                                }
                            });
                        }

                        // Plot candle pattern label if present
                        if (studyData.candle_pattern && studyData.candle_pattern !== 'NO_PATTERN') {
                            // Use current step from datafeed to get the correct candle
                            const datafeed = datafeedRef.current;
                            const stepIndex = datafeed && datafeed.customData
                                ? Math.min(datafeed.currentStep, datafeed.customData.length - 1)
                                : 0;
                            const candle = datafeed && datafeed.customData && datafeed.customData[stepIndex];
                            // Compute bar interval from first two candles for centering
                            const intervalSeconds = (datafeed && datafeed.customData && datafeed.customData.length > 1)
                                ? (toSeconds(datafeed.customData[1].time) - toSeconds(datafeed.customData[0].time))
                                : 60;
                            console.log(`[Pattern Debug] raw candle.time=${candle?.time}, stepIndex=${stepIndex}, intervalSeconds=${intervalSeconds}, toSeconds(candle.time)=${candle ? toSeconds(candle.time) : 'N/A'}, offset=${intervalSeconds / 2}`);
                            if (candle) {
                                plotPatternLabel(chart, studyData.candle_pattern, candle, intervalSeconds);
                            }
                        }

                        // --- SYNC AVAILABLE FANS based on actual remaining shapes ---
                        if (props.onAvailableFansUpdated) {
                            let foundNew = false;
                            const newIdentities = [];
                            
                            // 1. Register new drawings first
                            if (studyData.drawings && studyData.drawings.length > 0) {
                                studyData.drawings.forEach(d => {
                                    if (d.options && (d.options.fanIdentity || d.options.fanLabel)) {
                                        const identity = d.options.fanIdentity || d.options.fanLabel;
                                        const displayLabel = d.options.fanLabel || identity;
                                        
                                        fanDisplayMapRef.current[identity] = displayLabel;
                                        
                                        // Track if this is a brand new identity
                                        const existingIdentities = new Set(Object.values(fanLabelsRef.current || {}));
                                        if (!existingIdentities.has(identity)) {
                                            foundNew = true;
                                            newIdentities.push(identity);
                                        }
                                        
                                        fanLabelsRef.current[d.id] = identity;
                                    }
                                });
                            }

                            // 2. Clean up fanLabelsRef to only contain active drawings
                            const activeDrawingIds = Object.keys(studyShapesRef.current);
                            console.log("[DEBUG] activeDrawingIds:", activeDrawingIds.length, activeDrawingIds.slice(0, 5));
                            console.log("[DEBUG] fanLabelsRef before:", Object.keys(fanLabelsRef.current).length);

                            Object.keys(fanLabelsRef.current).forEach(drawingId => {
                                if (!activeDrawingIds.includes(drawingId)) {
                                    delete fanLabelsRef.current[drawingId];
                                }
                            });
                            console.log("[DEBUG] fanLabelsRef after:", Object.keys(fanLabelsRef.current).length);

                            // 3. Rebuild active identities from the cleaned fanLabelsRef
                            const activeIdentities = new Set(Object.values(fanLabelsRef.current));
                            
                            // 4. Clean up fanDisplayMapRef to only contain active identities
                            const newFanDisplayMap = {};
                            activeIdentities.forEach(id => {
                                if (fanDisplayMapRef.current[id]) {
                                    newFanDisplayMap[id] = fanDisplayMapRef.current[id];
                                } else {
                                    newFanDisplayMap[id] = id;
                                }
                            });
                            fanDisplayMapRef.current = newFanDisplayMap;

                            // 5. Emit auto-enable for new fans BEFORE updating the available list
                            if (foundNew && newIdentities.length > 0 && props.onAutoEnableVisibility) {
                                props.onAutoEnableVisibility(newIdentities);
                                // Immediately update the ref so the visibility loop below sees them!
                                newIdentities.forEach(id => {
                                    if (!visibleFanLabelsRef.current.includes(id)) {
                                        visibleFanLabelsRef.current.push(id);
                                    }
                                });
                            }

                            // 6. Emit updated list of available fans
                            const allIdentities = Array.from(activeIdentities);
                            const fanObjects = allIdentities
                                .map(id => ({ identity: id, displayLabel: fanDisplayMapRef.current[id] }))
                                .sort((a, b) => {
                                    const matchA = a.displayLabel.match(/^P(\d+)/);
                                    const matchB = b.displayLabel.match(/^P(\d+)/);
                                    const numA = matchA ? parseInt(matchA[1]) : 999;
                                    const numB = matchB ? parseInt(matchB[1]) : 999;
                                    return numA - numB;
                                });

                            props.onAvailableFansUpdated(fanObjects);
                        }

                        // Emit price interaction events from backend intersection_events (always present)
                        if (props.onPriceInteraction && studyData.intersection_events && studyData.intersection_events.length > 0) {
                            console.log(`[TVChart] Emitting ${studyData.intersection_events.length} price interactions to App.jsx`);
                            studyData.intersection_events.forEach(evt => {
                                const sd = evt.strategy_data || {};
                                props.onPriceInteraction({
                                    time: evt.time,
                                    fan: sd.fan || evt.fan || '',
                                    fanIdentity: sd.fanIdentity || sd.fan || evt.fanIdentity || evt.fan || '',
                                    fraction: sd.fraction || evt.fraction || '',
                                    price: evt.price,
                                    type: evt.type,
                                    details: evt.details,
                                    open: evt.open,
                                    high: evt.high,
                                    low: evt.low,
                                    close: evt.close,
                                    activeAngles: sd.activeAngles || evt.activeAngles || {},
                                    cluster: sd.cluster !== undefined ? sd.cluster : (evt.cluster || false),
                                    zone: sd.zone || evt.zone || '',
                                    zoneExtremes: sd.zoneExtremes || evt.zoneExtremes || {},
                                    nextAngleLine: sd.nextAngleLine || evt.nextAngleLine || '',
                                    strategy_data: sd
                                });
                            });
                        }

                        // Forward strategy_meta to App.jsx (column schema, filter options)
                        if (onStrategyMeta && studyData.strategy_meta) {
                            onStrategyMeta(studyData.strategy_meta);
                        }

                        // Handle Fan Visibility
                        if (studyData.drawings && studyData.drawings.length > 0) {
                            const visibleLabels = visibleFanLabelsRef.current;
                            studyData.drawings.forEach(d => {
                                if (d.options && (d.options.fanIdentity || d.options.fanLabel)) {
                                    const identity = d.options.fanIdentity || d.options.fanLabel;
                                    fanLabelsRef.current[d.id] = identity;

                                    // Apply immediate visibility
                                    const shapeId = studyShapesRef.current[d.id];
                                    const isVisible = visibleLabels.includes(identity);

                                    if (shapeId) {
                                        if (typeof shapeId === 'object' && typeof shapeId.then === 'function') {
                                            shapeId.then(id => {
                                                if (id) {
                                                    const shape = chart.getShapeById(id);
                                                    if (shape) shape.setProperties({ visible: isVisible });
                                                }
                                            }).catch(e => console.warn("[Study] Error setting shape visibility:", e));
                                        } else {
                                            const shape = chart.getShapeById(shapeId);
                                            if (shape) shape.setProperties({ visible: isVisible });
                                        }
                                    }
                                }
                            });
                        }

                    } catch (err) {
                        console.warn("[Study] Error processing drawings:", err.message);
                    }
                },
                scaleRatio,  // Initially null
                pivotSettings
            );

            widgetRef.current.onChartReady(async () => {
                if (!widgetRef.current) {
                    console.warn("[Progressive Replay] Widget lost during init, skipping setup");
                    return;
                }
                const chart = widgetRef.current.activeChart();
                chart.removeAllShapes();
                recentMarkersRef.current = {};
                patternMarkersRef.current = {};
                plottedTradesRef.current = {};  // Reset trade tracking for new replay
                studyShapesRef.current = {};    // Reset study shape tracking
                fanLabelsRef.current = {};
                fanDisplayMapRef.current = {};
                indicatorLinesRef.current = {};
                console.log("[Progressive Replay] Chart ready - cleared existing shapes");

                // COORD: Promise to ensure visible range is set BEFORE we lock the scale
                let resolveRangeSet;
                const rangeSetPromise = new Promise(resolve => { resolveRangeSet = resolve; });
                // Safety timeout: if dataReady/setVisibleRange stalls, proceed after 2s
                setTimeout(() => resolveRangeSet(false), 2000);

                // AUTO-FOCUS: Set visible range to show context leading up to the start point
                // Wrapped in dataReady() to ensure chart has ingested the new candles
                chart.dataReady(() => {
                    if (normalizedCandles.length > 0) {
                        try {
                            const startIndex = Math.max(0, replayStartIndex - 100); // Show ~100 bars of context
                            const endIndex = replayStartIndex;
                            
                            if (normalizedCandles[startIndex] && normalizedCandles[endIndex]) {
                                const fromTime = toSeconds(normalizedCandles[startIndex].time);
                                const toTime = toSeconds(normalizedCandles[endIndex].time);
                                
                                // Add buffer to the right (e.g. 10 bars worth of time)
                                let intervalSeconds = 60; // Default 1m
                                if (normalizedCandles.length > 1) {
                                    intervalSeconds = toSeconds(normalizedCandles[1].time) - toSeconds(normalizedCandles[0].time);
                                }
                                const rightBuffer = intervalSeconds * 15;

                                console.log(`[Progressive Replay] dataReady fired - Setting visible range: ${new Date(fromTime * 1000).toLocaleString()} to ${new Date((toTime + rightBuffer) * 1000).toLocaleString()}`);
                                
                                // Small delay to ensure layout is recalculated
                                setTimeout(() => {
                                    chart.setVisibleRange({
                                        from: fromTime,
                                        to: toTime + rightBuffer
                                    }).then(() => {
                                        console.log("[Progressive Replay] Visible range set successfully");
                                        resolveRangeSet(true);
                                    }).catch(e => {
                                        console.warn("[Progressive Replay] Failed to set visible range:", e);
                                        resolveRangeSet(false);
                                    });
                                }, 50);
                            } else {
                                console.warn("[Progressive Replay] Invalid start/end index for visible range", { startIndex, endIndex, candlesLength: normalizedCandles.length });
                                resolveRangeSet(false);
                            }
                            
                        } catch (err) {
                            console.warn("[Progressive Replay] Error calculating visible range:", err);
                            resolveRangeSet(false);
                        }
                    } else {
                        resolveRangeSet(true); // No candles, nothing to set
                    }
                });

                // Fetch authoritative scale ratio for angle calculations from backend
                const currentResolution = chart.resolution();
                // Get the ACTIVE symbol directly from the chart instance (accounts for user UI changes)
                let currentChartSymbol = chart.symbolExt ? chart.symbolExt().symbol : chart.symbol();
                let cleanSymbol = currentChartSymbol || symbol;
                if (cleanSymbol && cleanSymbol.endsWith(':YF')) {
                    cleanSymbol = cleanSymbol.replace(':YF', '');
                }

                try {
                    const res = await fetch(`http://localhost:8005/api/scale_ratio?symbol=${encodeURIComponent(cleanSymbol)}&resolution=${encodeURIComponent(currentResolution)}&cycle_type=${encodeURIComponent(cycleType)}&session_duration=${encodeURIComponent(sessionDuration)}`);
                    const data = await res.json();
                    if (data && data.scale_ratio) {
                        scaleRatio = data.scale_ratio;
                        chart.setPriceToBarRatio(scaleRatio, { disableUndo: true });
                        console.log(`[Progressive Replay] Fetched and locked authoritative Price-to-Bar Ratio to ${scaleRatio}`);
                    } else {
                        scaleRatio = 5.5;
                        chart.setPriceToBarRatio(scaleRatio, { disableUndo: true });
                        console.log(`[Progressive Replay] Fetched backend missing scale_ratio property, locked default 5.5`);
                    }
                } catch (err) {
                    scaleRatio = 5.5;
                    try { chart.setPriceToBarRatio(scaleRatio, { disableUndo: true }); } catch (e) { }
                    console.warn("[Progressive Replay] Failed to fetch backend scale ratio for replay, locked default 5.5:", err);
                }

                // WAIT for visible range to be applied (or timeout)
                // This ensures we don't lock the scale (and freeze Y-axis) until the chart has positioned itself
                console.log("[Progressive Replay] Waiting for visible range to be applied...");
                await rangeSetPromise;
                console.log("[Progressive Replay] Visible range handling complete, now locking scale...");

                // Explicitly lock the price-to-bar ratio so UI resizer doesn't distort it
                try {
                    if (typeof chart.setPriceToBarRatioLocked === 'function') {
                        chart.setPriceToBarRatioLocked(true, { disableUndo: true });
                    } else {
                        chart.getPriceScale().setMode({ autoScale: false });
                        chart.executeActionById("priceScaleLockRatio");
                    }
                    console.log("[Progressive Replay] Explicitly locked price axis scale");
                } catch (e) {
                    // Silent fail if TV library version doesn't support these exact lock methods
                }

                // Plot Initial Markers AND Initial Drawings (Fans) if provided
                if (pivotSettings && (
                    (pivotSettings.initialMarkers && pivotSettings.initialMarkers.length > 0) ||
                    (pivotSettings.initialDrawings && pivotSettings.initialDrawings.length > 0)
                )) {
                    console.log(`[Progressive Replay] Plotting ${pivotSettings.initialMarkers?.length || 0} initial markers and ${pivotSettings.initialDrawings?.length || 0} initial drawings`);
                    try {
                        console.log("[Progressive Replay] Marker/Drawing processing started");

                        const initMarkers = pivotSettings.initialMarkers || [];
                        const initDrawings = pivotSettings.initialDrawings || [];

                        // Pre-register fan visibility labels for initial fans BEFORE plotting
                        if (initDrawings.length > 0) {
                            updateAvailableFans(initDrawings);
                            initDrawings.forEach(d => {
                                if (d.options && (d.options.fanIdentity || d.options.fanLabel)) {
                                    fanLabelsRef.current[d.id] = d.options.fanIdentity || d.options.fanLabel;
                                }
                            });
                        }

                        // Use processStudyResponse to handle plotting both markers and drawings
                        studyShapesRef.current = processStudyResponse(chart, {
                            pivot_markers: initMarkers,
                            drawings: initDrawings
                        }, studyShapesRef.current);

                        // Apply visibility to initial drawings
                        if (initDrawings.length > 0) {
                            const visibleLabels = visibleFanLabelsRef.current || [];
                            initDrawings.forEach(d => {
                                if (d.options && (d.options.fanIdentity || d.options.fanLabel)) {
                                    const identity = d.options.fanIdentity || d.options.fanLabel;
                                    const shapeId = studyShapesRef.current[d.id];
                                    const isVisible = visibleLabels.includes(identity);
                                    if (shapeId) {
                                        if (typeof shapeId === 'object' && typeof shapeId.then === 'function') {
                                            shapeId.then(id => {
                                                if (id) {
                                                    const shape = chart.getShapeById(id);
                                                    if (shape) shape.setProperties({ visible: isVisible });
                                                }
                                            }).catch(e => console.warn("[Progressive Replay] Error setting shape visibility:", e));
                                        } else {
                                            const shape = chart.getShapeById(shapeId);
                                            if (shape) shape.setProperties({ visible: isVisible });
                                        }
                                    }
                                }
                            });
                        }

                        console.log("[Progressive Replay] Marker/Drawing processing complete");
                    } catch (err) {
                        console.error("[Progressive Replay] Failed to plot initial markers/drawings:", err);
                    }
                } else {
                    console.log("[Progressive Replay] No initial markers/drawings found in pivotSettings");
                }

                // Update datafeed with scale ratio and pivot settings
                if (datafeedRef.current) {
                    datafeedRef.current.setReplayStrategy(
                        strategy,
                        instrumentType,
                        onTradeCallback,
                        scaleRatio,
                        pivotSettings
                    );
                }


            });

            setIsPlaybackMode(true);
            setIsPlaying(false);
        },

        togglePlayPause: handlePlayPause,
        stepForward: handleStep,
        setSpeed: handleSpeedChange,

        isReplayMode: () => isPlaybackMode,

        isPlaying: () => isPlaying,

        exitReplay: () => {
            if (datafeedRef.current) {
                datafeedRef.current.exitCustomMode();
            }
            indicatorLinesRef.current = {};
            setIsPlaybackMode(false);
            setIsPlaying(false);
        },

        // Load a symbol at a specific resolution on the chart
        loadSymbolResolution: (symbolName, resolution) => {
            if (!widgetRef.current) return;
            const chart = widgetRef.current.activeChart();
            // Restore ^ prefix if it was sanitized to _ (Windows-safe path encoding)
            let fixedSymbol = symbolName;
            if (fixedSymbol.startsWith('_') && fixedSymbol.length > 1 && /[A-Za-z]/.test(fixedSymbol[1])) {
                fixedSymbol = '^' + fixedSymbol.slice(1);
            }
            currentCleanSymbolRef.current = fixedSymbol;
            // Pick the right data source: Binance for crypto, YFinance for indices
            const isCrypto = /^[A-Z0-9]{2,12}USDT$/.test(fixedSymbol);
            const suffix = isCrypto ? ':BN' : (fixedSymbol.includes(':YF') ? '' : ':YF');
            const ticker = fixedSymbol + suffix;
            chart.setSymbol(ticker, () => {
                chart.setResolution(String(resolution), () => {
                    console.log(`[TVChart] Loaded ${ticker} @ ${resolution}m`);
                });
            });
        },

        // Reset the navigation dedup state (call when switching reports)
        resetNavigationState: () => {
            lastNavigatedEventKeyRef.current = null;
            navigationGenerationRef.current = 0;
            selectedHypothesisEventRef.current = null;
        },

        // Load candles from a hypothesis run into the chart
        loadRunCandles: async (runPath) => {
            await loadHypothesisRunCandles(runPath);
        },
    }));

    return (
        <div style={{ position: 'relative', height: '100%' }}>
            <div
                ref={chartContainerRef}
                style={{ height: '100%', width: '100%' }}
            />
            {showPatternLegend && (
                /* Floating Pattern Legend — upper-right corner, within chart canvas only */
                <div style={{
                    position: 'absolute',
                    top: 12,
                    right: 12,
                    left: 'auto',
                    zIndex: 100,
                    pointerEvents: 'none',
                    backgroundColor: 'rgba(30, 34, 45, 0.92)',
                    border: '1px solid #434651',
                    borderRadius: 8,
                    padding: '10px 14px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 6,
                    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
                    minWidth: 148,
                }}>
                    <div style={{ fontSize: 9, fontWeight: 700, color: '#787b86', textTransform: 'uppercase', letterSpacing: '0.8px', marginBottom: 2 }}>
                        Patterns
                    </div>
                    {[
                        { label: 'Pinbar',          color: '#00BCD4' },
                        { label: 'Doji',            color: '#FFEB3B' },
                        { label: 'Shooting Star',   color: '#E91E63' },
                        { label: 'Inverted Hammer', color: '#AEEA00' },
                        { label: 'Marubozu',        color: '#E0E0E0' },
                        { label: 'Spinning Top',     color: '#F48FB1' },
                    ].map(({ label, color }) => (
                        <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11, color: '#d1d4dc' }}>
                            <span style={{ display: 'inline-block', width: 9, height: 9, borderRadius: '50%', backgroundColor: color, flexShrink: 0 }} />
                            {label}
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
});
