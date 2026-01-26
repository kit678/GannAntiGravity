import React, { useEffect, useRef, useState, useImperativeHandle, forwardRef } from 'react';
import createChartDatafeed from './chart/ChartDatafeed';
import { processStudyResponse, clearAllStudyDrawings } from './study_tool/StudyDrawingUtils';

export const TVChartContainer = forwardRef(({ symbol = 'NIFTY 50', datafeedUrl, interval = '1', onTradeLogged, dataSource = 'dhan', onSymbolChange }, ref) => {
    const chartContainerRef = useRef(null);
    const datafeedRef = useRef(null);
    const widgetRef = useRef(null);

    // Playback state
    const [isPlaybackMode, setIsPlaybackMode] = useState(false);
    const [isPlaying, setIsPlaying] = useState(false);
    const [playbackSpeed, setPlaybackSpeed] = useState(1000);

    // Store trades for replay mode
    const tradesRef = useRef([]);

    // Track study shapes for cleanup
    const studyShapesRef = useRef({});

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

            console.log('[TVChart] Initializing chart with dataSource:', dataSource);

            const udfDatafeed = new window.Datafeeds.UDFCompatibleDatafeed(datafeedUrl);
            const customDatafeed = createChartDatafeed(udfDatafeed, dataSource);
            datafeedRef.current = customDatafeed;

            const widget = new window.TradingView.widget({
                symbol: symbol,
                interval: interval,
                timezone: 'Asia/Kolkata',
                fullscreen: false,
                container: chartContainerRef.current,
                datafeed: customDatafeed,
                library_path: '/charting_library/',
                locale: 'en',
                disabled_features: ['use_localstorage_for_settings', 'header_compare'],
                enabled_features: ['study_templates', 'header_symbol_search', 'symbol_search_hot_key'],
                symbol_search_request_delay: 500,
                charts_storage_url: 'https://saveload.tradingview.com',
                charts_storage_api_version: '1.1',
                client_id: 'tradingview.com',
                user_id: 'public_user_id',
                theme: 'Dark',
                autosize: true,
                time_scale: {
                    right_offset: 5,
                    visible_range: {}
                },
                overrides: {
                    "scalesProperties.showSymbolLabels": true,
                    "mainSeriesProperties.candleStyle.drawBorder": true,

                },
            });

            widgetRef.current = widget;
            window.tvWidget = widget;

            widget.onChartReady(() => {
                console.log("[Chart] Ready");

                // Subscribe to Symbol Changes to keep parent in sync
                try {
                    widget.activeChart().onSymbolChanged().subscribe(null, (symbolInfo) => {
                        console.log("[Chart] Symbol Changed to:", symbolInfo.name);
                        // Extract cleanly if it has suffix
                        let cleanName = symbolInfo.name;
                        // If we are in Yahoo mode and have suffix, maybe strip it for parent state? 
                        // Actually, parent state usually drives this. But if user changes it via search...
                        // Let's pass the raw name back.
                        if (onSymbolChange) onSymbolChange(cleanName);
                    });
                } catch (e) {
                    console.warn("[Chart] Failed to subscribe to symbol changes:", e);
                }


            });
        }

        // Check if TradingView library is already loaded
        if (window.TradingView && window.Datafeeds) {
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
                    widgetRef.current.remove();
                    console.log('[TVChart] Widget destroyed for clean re-init');
                } catch (e) {
                    console.warn('[TVChart] Error removing widget:', e);
                }
                widgetRef.current = null;
            }
            datafeedRef.current = null;

            // Only remove script if we created one
            if (scriptElement && scriptElement.parentNode) {
                scriptElement.parentNode.removeChild(scriptElement);
            }
        };
    }, [symbol, datafeedUrl, interval, dataSource]);

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
    const findMatchingBarTime = (tradeTimeSeconds, candles) => {
        if (!candles || candles.length === 0) return tradeTimeSeconds;

        const tradeTimeMs = tradeTimeSeconds * 1000;

        // Find the candle that contains or is closest to this trade time
        let closestBar = candles[0];
        let closestDiff = Math.abs(candles[0].time - tradeTimeMs);

        for (let i = 0; i < candles.length; i++) {
            const diff = Math.abs(candles[i].time - tradeTimeMs);
            if (diff < closestDiff) {
                closestDiff = diff;
                closestBar = candles[i];
            }
            // If we've passed the trade time, check if current or previous is closer
            if (candles[i].time >= tradeTimeMs) {
                break;
            }
        }

        console.log(`[findMatchingBarTime] Trade at ${new Date(tradeTimeMs).toISOString()} -> Matched to bar at ${new Date(closestBar.time).toISOString()}`);
        return closestBar.time / 1000; // Return as seconds for TradingView
    };

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

    // Plot a single trade shape - now accepts optional candles for time snapping
    const plotTradeShape = (chart, trade, candles = null) => {
        // Validate trade data before calling TradingView API
        if (!trade || trade.time === undefined || trade.time === null || trade.price === undefined || trade.price === null) {
            console.warn("Invalid trade data, skipping:", trade);
            return false;
        }

        // DUPLICATE PREVENTION: Create unique key for this trade
        // Using time + type + price to identify unique trades
        const tradeKey = `${trade.time}_${trade.type}_${trade.price}`;
        if (plottedTradesRef.current[tradeKey]) {
            console.log(`[plotTradeShape] Skipping duplicate trade: ${tradeKey}`);
            return false;
        }
        plottedTradesRef.current[tradeKey] = true;

        const color = trade.type === 'buy' ? '#00E676' : '#FF5252';

        // Use arrows with proper sizing
        const shape = trade.type === 'buy' ? 'arrow_up' : 'arrow_down';

        // Use exact trade time from backend (no snapping)
        const shapeTime = toSeconds(trade.time);

        // Find the matching candle for this trade to get high/low
        let candleHigh = trade.price;
        let candleLow = trade.price;

        if (candles && candles.length > 0) {
            // Find candle that contains this trade time
            const matchingCandle = candles.find(c => {
                const candleTime = toSeconds(c.time);
                // Trade belongs to candle if it's within the candle's time window
                return Math.abs(candleTime - shapeTime) < 60; // Within 1 minute
            });

            if (matchingCandle) {
                candleHigh = matchingCandle.high;
                candleLow = matchingCandle.low;
            }
        }

        // FIX FOR STACKED MARKERS: Track markers in time buckets and apply progressive offsets
        // Round time to nearest 5-minute bucket to group nearby trades
        const timeBucket = Math.floor(shapeTime / 300) * 300; // 300 seconds = 5 minutes
        const bucketKey = `${timeBucket}_${trade.type}`;

        // Initialize or get existing markers in this bucket for this type
        if (!recentMarkersRef.current[bucketKey]) {
            recentMarkersRef.current[bucketKey] = [];
        }

        // Count how many markers of the same type are already in this bucket
        const existingCount = recentMarkersRef.current[bucketKey].length;

        // Position markers just outside the candle extremes
        // Small base offset (0.15% of price) to separate from candle
        const baseOffset = trade.price * 0.0015;

        // Additional offset per stacked marker (0.1% per level)
        const stackOffset = trade.price * 0.001 * existingCount;

        // Calculate final price based on candle high/low
        // Buy arrows: positioned below the candle's LOW, pointing up
        // Sell arrows: positioned above the candle's HIGH, pointing down
        const shapePrice = trade.type === 'buy'
            ? candleLow - baseOffset - stackOffset  // Below lowest point
            : candleHigh + baseOffset + stackOffset; // Above highest point

        // Record this marker in the bucket
        recentMarkersRef.current[bucketKey].push({ price: shapePrice, time: shapeTime });

        // Format trade info for console logging only
        const tradeDate = new Date(trade.time * 1000);
        const dateStr = tradeDate.toLocaleDateString('en-GB', {
            day: '2-digit',
            month: 'short'
        });
        const timeStr = tradeDate.toLocaleTimeString('en-GB', {
            hour: '2-digit',
            minute: '2-digit',
            hour12: false
        });

        console.log(`[plotTradeShape] ${trade.type.toUpperCase()} at ${dateStr} ${timeStr}, time=${shapeTime}, price=${trade.price}, candle H/L=${candleHigh}/${candleLow} -> marker@${shapePrice.toFixed(2)} (stack level ${existingCount})`);

        try {
            const createdShape = chart.createShape({ time: shapeTime, price: shapePrice }, {
                shape: shape,
                text: '',  // No text label - tooltip will show on hover
                overrides: {
                    color: color,
                    backgroundColor: color,
                    size: 1,  // Numeric size: 1 is smallest
                    fontsize: 0,
                    bold: false
                }
            });

            console.log(`[plotTradeShape] Shape created successfully:`, createdShape);
            return true;
        } catch (err) {
            console.error("[plotTradeShape] Error creating shape:", err);
            console.error("[plotTradeShape] Error details:", {
                message: err.message,
                stack: err.stack,
                trade: trade,
                shapeTime: shapeTime,
                shapePrice: shapePrice
            });
            return false;
        }
    };

    // Expose methods to parent (App.jsx)
    useImperativeHandle(ref, () => ({
        // Get current chart resolution
        // Get current chart resolution
        getResolution: () => {
            if (widgetRef.current) {
                try {
                    return widgetRef.current.activeChart().resolution();
                } catch (e) {
                    console.warn("[TVChart] Failed to get resolution from active widget:", e);
                }
            }
            return '1'; // Default
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

        // INSTANT MODE: Plot all candles and signals at once
        startBacktestInstant: (candles, trades, resolution = '1') => {
            console.log("Starting Instant Backtest", candles.length, "candles,", trades.length, "trades, resolution:", resolution);

            if (!datafeedRef.current || !widgetRef.current) {
                console.error("Chart not ready");
                return;
            }

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
                            console.log("[FIX] Now plotting markers (post-range-set)...");

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
                        }, 500); // 500ms delay to allow bar indexing
                    }).catch(err => {
                        console.error("Error setting visible range:", err);
                        // Fall back to plotting without range set
                        let plotted = 0;
                        trades.forEach(t => {
                            try {
                                if (plotTradeShape(chart, t)) {
                                    plotted++;
                                    if (onTradeLogged) onTradeLogged(t);
                                }
                            } catch (err2) {
                                console.warn("Failed to plot trade:", t, err2);
                            }
                        });
                        console.log(`Fallback plotted ${plotted}/${trades.length} trades`);
                    });
                } else {
                    console.warn("No candles to set visible range");
                }
            });

            // Skip the old onChartReady/dataReady logic below - callback handles everything
            return;

            // Wait for chart to be ready, then plot shapes and set range
            widgetRef.current.onChartReady(() => {
                const chart = widgetRef.current.activeChart();

                // Clear existing shapes
                chart.removeAllShapes();

                // Wait for data to be fully loaded after resetData() call
                chart.dataReady(() => {
                    console.log("Chart data is ready, proceeding with backtest visualization");

                    // Set visible range FIRST, then plot shapes
                    if (normalizedCandles.length > 0) {
                        const firstTime = toSeconds(normalizedCandles[0].time);
                        const lastTime = toSeconds(normalizedCandles[normalizedCandles.length - 1].time);

                        console.log("Setting visible range:", new Date(firstTime * 1000), "to", new Date(lastTime * 1000));

                        chart.setVisibleRange({
                            from: firstTime,
                            to: lastTime + (30 * 60) // Add 30 min padding
                        }).then(() => {
                            console.log("Visible range set successfully, now plotting", trades.length, "trades");

                            // Plot all trades AFTER range is set
                            let plotted = 0;
                            trades.forEach(t => {
                                try {
                                    // Pass normalizedCandles for time matching
                                    if (plotTradeShape(chart, t, normalizedCandles)) {
                                        plotted++;
                                        if (onTradeLogged) onTradeLogged(t);
                                    }
                                } catch (err) {
                                    console.warn("Failed to plot trade:", t, err);
                                }
                            });
                            console.log(`Successfully plotted ${plotted}/${trades.length} trades`);
                        }).catch(err => {
                            console.error("Error setting range:", err);
                            // Still try to plot trades even if range fails
                            trades.forEach(t => {
                                try {
                                    plotTradeShape(chart, t, normalizedCandles);
                                    if (onTradeLogged) onTradeLogged(t);
                                } catch (e) {
                                    console.warn("Failed to plot trade:", t, e);
                                }
                            });
                        });
                    } else {
                        console.warn("No candles to set range from");
                    }
                });
            });

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
                }
            }

            const normalizedCandles = candles.map(c => ({
                ...c,
                time: toMilliseconds(c.time)
            }));

            currentCandlesRef.current = normalizedCandles;

            // Query chart's scale ratio for angle calculations
            let scaleRatio = null;
            try {
                scaleRatio = widgetRef.current.activeChart().getPriceToBarRatio();
                console.log("[Progressive Replay] Chart scale ratio:", scaleRatio);
            } catch (e) {
                console.warn("[Progressive Replay] Could not get scale ratio:", e);
            }

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
                    } catch (err) {
                        console.warn("[Study] Error processing drawings:", err.message);
                    }
                },
                scaleRatio,
                pivotSettings  // NEW: pass pivot settings for configurable pivot detection
            );

            widgetRef.current.onChartReady(() => {
                const chart = widgetRef.current.activeChart();
                chart.removeAllShapes();
                recentMarkersRef.current = {};
                plottedTradesRef.current = {};  // Reset trade tracking for new replay
                studyShapesRef.current = {};    // Reset study shape tracking
                console.log("[Progressive Replay] Chart ready - cleared existing shapes");
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
            setIsPlaybackMode(false);
            setIsPlaying(false);
        }
    }));

    return (
        <div style={{ position: 'relative', height: '100%' }}>
            <div
                ref={chartContainerRef}
                style={{ height: '100%', width: '100%' }}
            />
        </div>
    );
});
