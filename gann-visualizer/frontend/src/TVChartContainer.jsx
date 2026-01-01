import React, { useEffect, useRef, useState, useImperativeHandle, forwardRef } from 'react';
import createChartDatafeed from './chart/ChartDatafeed';

export const TVChartContainer = forwardRef(({ symbol = 'NIFTY 50', datafeedUrl, interval = '1', onTradeLogged }, ref) => {
    const chartContainerRef = useRef(null);
    const datafeedRef = useRef(null);
    const widgetRef = useRef(null);

    // Playback state
    const [isPlaybackMode, setIsPlaybackMode] = useState(false);
    const [isPlaying, setIsPlaying] = useState(false);
    const [playbackSpeed, setPlaybackSpeed] = useState(1000);

    // Store trades for replay mode
    const tradesRef = useRef([]);

    useEffect(() => {
        const script = document.createElement('script');
        script.src = '/charting_library/charting_library.js';
        script.async = true;
        script.onload = () => {
            initChart();
        };
        document.body.appendChild(script);

        function initChart() {
            if (!window.TradingView) return;

            const udfDatafeed = new window.Datafeeds.UDFCompatibleDatafeed(datafeedUrl);
            const customDatafeed = createChartDatafeed(udfDatafeed);
            datafeedRef.current = customDatafeed;

            const widget = new window.TradingView.widget({
                symbol: symbol,
                interval: interval,
                timezone: 'Asia/Kolkata', // Set explicit timezone to match Dhan data
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
                // Fix white space on right - limit margin beyond last candle
                time_scale: {
                    right_offset: 5,  // Only 5 bars of future space (instead of default ~10%)
                    visible_range: {
                        // Let TradingView auto-calculate based on available data
                    }
                },
                overrides: {
                    "scalesProperties.showSymbolLabels": true,
                    "mainSeriesProperties.candleStyle.drawBorder": true,
                },
            });

            widgetRef.current = widget;
            window.tvWidget = widget;
        }

        return () => {
            if (script.parentNode) script.parentNode.removeChild(script);
        };
    }, [symbol, datafeedUrl, interval]);

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

    // Plot a single trade shape - now accepts optional candles for time snapping
    const plotTradeShape = (chart, trade, candles = null) => {
        // Validate trade data before calling TradingView API
        if (!trade || trade.time === undefined || trade.time === null || trade.price === undefined || trade.price === null) {
            console.warn("Invalid trade data, skipping:", trade);
            return false;
        }

        const color = trade.type === 'buy' ? '#00E676' : '#FF5252';

        // SIMPLIFIED TEXT: Just show date and time for easier alignment verification
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
        const text = `${dateStr} ${timeStr}`; // e.g., "22 Dec 09:15"

        const shape = trade.type === 'buy' ? 'arrow_up' : 'arrow_down';

        // Use exact trade time from backend (no snapping)
        const shapeTime = toSeconds(trade.time);

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

        // Base offset from price (0.3% to clear candlestick body)
        const baseOffset = trade.price * 0.003;

        // Additional offset per stacked marker (0.15% per level)
        const stackOffset = trade.price * 0.0015 * existingCount;

        // Calculate final price with progressive offset
        // Buy arrows stack downward, Sell arrows stack upward
        const shapePrice = trade.type === 'buy'
            ? trade.price - baseOffset - stackOffset  // Buy arrows below, stacking further down
            : trade.price + baseOffset + stackOffset; // Sell arrows above, stacking further up

        // Record this marker in the bucket
        recentMarkersRef.current[bucketKey].push({ price: shapePrice, time: shapeTime });

        console.log(`[plotTradeShape] ${trade.type.toUpperCase()} at ${dateStr} ${timeStr}, time=${shapeTime}, price=${trade.price} -> ${shapePrice.toFixed(2)} (stack level ${existingCount})`);

        try {
            chart.createShape({ time: shapeTime, price: shapePrice }, {
                shape: shape,
                text: text,
                overrides: {
                    color: color,
                    backgroundColor: color,
                    fontsize: 8,  // Reduced from 10 for less clutter
                    bold: false
                }
            });
            return true;
        } catch (err) {
            console.error("[plotTradeShape] Error creating shape:", err);
            return false;
        }
    };

    // Expose methods to parent (App.jsx)
    useImperativeHandle(ref, () => ({
        // Get current chart resolution
        getResolution: () => {
            if (widgetRef.current) {
                return widgetRef.current.activeChart().resolution();
            }
            return '1'; // Default
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
        startBacktestReplay: (candles, trades, resolution = '1') => {
            console.log("Starting Replay Mode", candles.length, "candles,", trades.length, "trades, resolution:", resolution);

            if (!datafeedRef.current || !widgetRef.current) {
                console.error("Chart not ready");
                return;
            }

            // Ensure candle times are in milliseconds
            const normalizedCandles = candles.map(c => ({
                ...c,
                time: toMilliseconds(c.time)
            }));

            // CRITICAL: Store candles for trade time matching
            currentCandlesRef.current = normalizedCandles;

            // Store trades
            tradesRef.current = trades;

            // Configure datafeed for replay with trade callback and resolution
            datafeedRef.current.setBacktestDataForReplay(normalizedCandles, trades, (trade) => {
                // This callback fires when a trade time is reached during replay
                const chart = widgetRef.current.activeChart();
                plotTradeShape(chart, trade, normalizedCandles);
                if (onTradeLogged) onTradeLogged(trade);
            }, resolution);

            widgetRef.current.onChartReady(() => {
                const chart = widgetRef.current.activeChart();
                chart.removeAllShapes();
            });

            setIsPlaybackMode(true);
            setIsPlaying(false);
        },

        togglePlayPause: handlePlayPause,
        stepForward: handleStep,
        setSpeed: handleSpeedChange,

        isReplayMode: () => isPlaybackMode,

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
