// gann-visualizer/frontend/src/chart/ChartDatafeed.js
// Extended TradingView datafeed implementation

class ChartDatafeed {
    constructor(originalDatafeed) {
        console.log("Creating ChartDatafeed wrapper", originalDatafeed);
        this.originalDatafeed = originalDatafeed;
        this.isCustomMode = false;
        this.customData = [];
        this.currentStep = 0;
        this.playbackSpeed = 1000; // 1 second default
        this.playbackInterval = null;
        this.subscribers = {};
        this.isInitialized = false;
        this.lastPlaybackTime = null;
        this.allBarsLoaded = false;

        // Replay trade tracking
        this.backtestTrades = [];
        this.tradeCallback = null;
        this.plottedTradeIndices = new Set();
    }

    // Load external data for Instant Backtest (all data at once, no replay)
    setBacktestData(candles, resolution = '1', onComplete = null) {
        console.log("[ChartDatafeed] Setting backtest data (instant mode):", candles.length, "candles, resolution:", resolution);

        if (candles.length > 0) {
            console.log("[ChartDatafeed] Backtest data range:",
                new Date(candles[0].time).toISOString(), "to",
                new Date(candles[candles.length - 1].time).toISOString());
        }

        // CRITICAL: Unsubscribe from original UDF to stop background fetching
        this._unsubscribeFromOriginal();

        // Set mode BEFORE resetData to ensure getBars returns custom data
        this.customData = candles;
        this.isCustomMode = true;
        this.isInitialized = true;
        this.allBarsLoaded = true;
        this.currentStep = candles.length - 1; // All bars visible
        this.playbackStartTime = candles.length > 0 ? candles[0].time : Date.now();

        // Force chart reset with correct resolution
        if (window.tvWidget) {
            const chart = window.tvWidget.activeChart();

            console.log(`[ChartDatafeed] Forcing ${resolution} resolution and resetting data...`);
            chart.setResolution(resolution, () => {
                console.log(`[ChartDatafeed] Resolution set to ${resolution}, now calling resetData()`);
                chart.resetData();

                // FIX: Use TradingView's dataReady() callback instead of arbitrary timeout
                // This ensures candlesticks are fully rendered before we plot markers
                // Works reliably across browsers including Brave
                chart.dataReady(() => {
                    console.log("[ChartDatafeed] Chart dataReady() fired - candlesticks are rendered");

                    // Small additional delay to ensure visual rendering completes
                    // dataReady fires when data is loaded, but canvas may still be painting
                    setTimeout(() => {
                        console.log("[ChartDatafeed] Triggering onComplete callback");
                        if (onComplete) onComplete();
                    }, 200);
                });
            });
        } else if (onComplete) {
            // Fallback if widget not ready
            onComplete();
        }
    }

    // Load external data for Replay mode (candle by candle)
    setBacktestDataForReplay(candles, trades, onTradeCallback, resolution = '1') {
        console.log("[ChartDatafeed] Setting backtest data (replay mode):", candles.length, "candles,", trades.length, "trades");

        // CRITICAL: Unsubscribe from original UDF to stop background fetching
        this._unsubscribeFromOriginal();

        this.customData = candles;
        this.backtestTrades = trades;
        this.tradeCallback = onTradeCallback;
        this.plottedTradeIndices = new Set();

        this.isCustomMode = true;
        this.isInitialized = true;
        this.allBarsLoaded = true;
        this.currentStep = 0; // Start from beginning
        this.playbackStartTime = candles.length > 0 ? candles[0].time : Date.now();

        // Force chart reset with correct resolution
        if (window.tvWidget) {
            const chart = window.tvWidget.activeChart();

            console.log(`[ChartDatafeed] Replay: Forcing ${resolution} resolution and resetting data...`);
            chart.setResolution(resolution, () => {
                chart.resetData();
            });
        }
    }

    // Helper to unsubscribe from the original UDF datafeed
    _unsubscribeFromOriginal() {
        console.log("[ChartDatafeed] Unsubscribing from original UDF datafeed");
        // Clear any existing original datafeed subscriptions
        if (this._originalSubscriberUIDs) {
            this._originalSubscriberUIDs.forEach(uid => {
                try {
                    this.originalDatafeed.unsubscribeBars(uid);
                } catch (e) {
                    // Ignore errors
                }
            });
        }
        this._originalSubscriberUIDs = [];
    }

    // Standard UDF methods that pass through to original datafeed
    onReady(callback) {
        console.log("ChartDatafeed.onReady called");
        this.originalDatafeed.onReady(callback);
    }

    searchSymbols(userInput, exchange, symbolType, onResult) {
        this.originalDatafeed.searchSymbols(userInput, exchange, symbolType, onResult);
    }

    resolveSymbol(symbolName, onSymbolResolvedCallback, onResolveErrorCallback, extension) {
        console.log("ChartDatafeed.resolveSymbol called for", symbolName);
        this.originalDatafeed.resolveSymbol(symbolName, onSymbolResolvedCallback, onResolveErrorCallback, extension);
    }

    // Core method for historical data
    getBars(symbolInfo, resolution, periodParams, onHistoryCallback, onErrorCallback) {
        // DETAILED LOGGING for debugging pagination
        const fromDate = new Date(periodParams.from * 1000);
        const toDate = new Date(periodParams.to * 1000);
        console.log(`[getBars] Request: ${symbolInfo.ticker} | ${resolution} | from: ${fromDate.toISOString()} | to: ${toDate.toISOString()} | countBack: ${periodParams.countBack} | firstDataRequest: ${periodParams.firstDataRequest} | customMode: ${this.isCustomMode}`);

        // CRITICAL: In custom mode, serve ONLY custom data and stop further requests
        if (this.isCustomMode) {
            // In custom mode, serve from our data
            if (!this.customData || this.customData.length === 0) {
                console.log("[getBars] CUSTOM MODE: No custom data available");
                onHistoryCallback([], { noData: true });
                return;
            }

            // Return bars up to current step
            const visibleBars = this.customData.slice(0, this.currentStep + 1);
            console.log(`[getBars] CUSTOM MODE: Serving ${visibleBars.length}/${this.customData.length} bars (step ${this.currentStep})`);
            if (visibleBars.length > 0) {
                console.log(`[getBars] Custom data range: ${new Date(visibleBars[0].time).toISOString()} to ${new Date(visibleBars[visibleBars.length - 1].time).toISOString()}`);
            }

            // CRITICAL FIX: Set noData: true to STOP TradingView from requesting more history
            // This prevents the infinite loading loop and "..." indicator
            onHistoryCallback(visibleBars, { noData: true });
            return;
        }

        // If not in custom mode, pass through to original UDF datafeed
        console.log("[Wrapper] Delegating getBars to original datafeed...");
        return this.originalDatafeed.getBars(
            symbolInfo,
            resolution,
            periodParams,
            (bars, meta) => {
                // DETAILED LOGGING for debugging
                console.log(`[Wrapper] SUCCESS: ${bars.length} bars | noData: ${meta.noData} | nextTime: ${meta.nextTime}`);
                if (bars.length > 0) {
                    const firstBar = new Date(bars[0].time);
                    const lastBar = new Date(bars[bars.length - 1].time);
                    console.log(`  Range: ${firstBar.toISOString()} to ${lastBar.toISOString()}`);
                } else {
                    console.warn("[Wrapper] 0 bars returned");
                }
                onHistoryCallback(bars, meta);
            },
            (err) => {
                console.error("[Wrapper] Original getBars FAILED:", err);
                onErrorCallback(err);
            }
        );
    }

    // Handle realtime updates
    subscribeBars(symbolInfo, resolution, onRealtimeCallback, subscriberUID, onResetCacheNeededCallback) {
        console.log("[ChartDatafeed] subscribeBars called for", subscriberUID, "customMode:", this.isCustomMode);

        // CRITICAL: In custom mode, do NOT subscribe to original UDF (prevents background loading)
        if (this.isCustomMode) {
            // In custom mode, manage updates ourselves
            this.subscribers[subscriberUID] = {
                symbolInfo,
                resolution,
                callback: onRealtimeCallback,
                lastBarTime: null
            };
            console.log("[ChartDatafeed] Custom mode: Managing subscription internally");
            return subscriberUID;
        }

        // Track subscriptions so we can unsubscribe later
        if (!this._originalSubscriberUIDs) {
            this._originalSubscriberUIDs = [];
        }
        this._originalSubscriberUIDs.push(subscriberUID);

        return this.originalDatafeed.subscribeBars(
            symbolInfo,
            resolution,
            onRealtimeCallback,
            subscriberUID,
            onResetCacheNeededCallback
        );
    }

    unsubscribeBars(subscriberUID) {
        if (!this.isCustomMode) {
            return this.originalDatafeed.unsubscribeBars(subscriberUID);
        }
        delete this.subscribers[subscriberUID];
    }

    // Start automated playback
    playback_start() {
        console.log("ChartDatafeed.playback_start called");

        if (!this.isCustomMode || !this.isInitialized) {
            console.error("Cannot start playback - not in custom mode or not initialized");
            return;
        }

        if (this.playbackInterval) {
            console.log("Playback already running");
            return;
        }

        console.log("Starting playback interval with speed", this.playbackSpeed);
        this.playbackInterval = setInterval(() => {
            this.playback_step();
        }, this.playbackSpeed);
    }

    // Stop automated playback
    playback_stop() {
        console.log("ChartDatafeed.playback_stop called");

        if (this.playbackInterval) {
            clearInterval(this.playbackInterval);
            this.playbackInterval = null;
            console.log("Playback stopped");
        }
    }

    // Move forward one bar
    playback_step() {
        if (!this.isCustomMode || !this.isInitialized) {
            console.error("Cannot step - not in custom mode or not initialized");
            return;
        }

        if (!this.customData || this.customData.length === 0) {
            console.error("No custom data available");
            return;
        }

        // Don't proceed if we're at the end
        if (this.currentStep >= this.customData.length - 1) {
            console.log("Reached end of data");
            this.playback_stop();
            return;
        }

        // Move to next bar
        this.currentStep++;
        const currentBar = this.customData[this.currentStep];
        const currentBarTimeSeconds = currentBar.time / 1000; // Convert ms to s for comparison

        console.log("Moving to bar", this.currentStep, "time:", new Date(currentBar.time).toLocaleString());

        // Check for trades to plot
        this.backtestTrades.forEach((trade, idx) => {
            if (!this.plottedTradeIndices.has(idx)) {
                // Trade time is in seconds from backend
                if (trade.time <= currentBarTimeSeconds) {
                    console.log("Plotting trade at step", this.currentStep, trade);
                    this.plottedTradeIndices.add(idx);
                    if (this.tradeCallback) {
                        this.tradeCallback(trade);
                    }
                }
            }
        });

        // Notify all subscribers about the new bar
        Object.keys(this.subscribers).forEach(subId => {
            const sub = this.subscribers[subId];
            if (!sub.lastBarTime || currentBar.time > sub.lastBarTime) {
                sub.callback(currentBar);
                sub.lastBarTime = currentBar.time;
            }
        });

        // Update the chart display
        this.updateChartDisplay();
    }

    // Helper to update the chart display
    updateChartDisplay() {
        if (!window.tvWidget) return;

        try {
            const chart = window.tvWidget.activeChart();

            // Calculate visible range
            const minWindowSeconds = 2 * 60 * 60; // 2 hours minimum
            const endTime = this.customData[this.currentStep].time / 1000;
            const barsLookback = 100;

            let startTime;
            if (this.currentStep < barsLookback) {
                startTime = endTime - minWindowSeconds;
            } else {
                startTime = this.customData[this.currentStep - barsLookback].time / 1000;
                if (endTime - startTime < minWindowSeconds) {
                    startTime = endTime - minWindowSeconds;
                }
            }

            chart.setVisibleRange({
                from: startTime,
                to: endTime + (15 * 60) // +15 min padding
            }).catch(err => {
                console.error("Error setting visible range:", err);
            });
        } catch (err) {
            console.error("Error updating chart display:", err);
        }
    }

    // Set playback speed
    playback_set_speed(speed) {
        console.log("ChartDatafeed.playback_set_speed called with speed", speed);
        this.playbackSpeed = parseInt(speed);

        if (this.playbackInterval) {
            this.playback_stop();
            this.playback_start();
        }
    }

    // Exit custom mode
    exitCustomMode() {
        console.log("ChartDatafeed.exitCustomMode called");

        this.playback_stop();

        this.isCustomMode = false;
        this.isInitialized = false;
        this.customData = [];
        this.allBarsLoaded = false;
        this.currentStep = 0;
        this.playbackStartTime = null;
        this.backtestTrades = [];
        this.tradeCallback = null;
        this.plottedTradeIndices = new Set();

        localStorage.removeItem('chart_playback');
        localStorage.removeItem('chart_playback_active');

        if (window.tvWidget) {
            const chart = window.tvWidget.activeChart();
            const currentSymbol = chart.symbol();
            const currentResolution = chart.resolution();
            chart.setSymbol(currentSymbol, currentResolution);
        }
    }
}

function createChartDatafeed(originalDatafeed) {
    console.log("createChartDatafeed called");
    return new ChartDatafeed(originalDatafeed);
}

export default createChartDatafeed;
