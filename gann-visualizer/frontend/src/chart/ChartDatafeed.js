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
        this.progressCallback = null; // NEW: callback for replay progress updates
        this.lastSignalType = null; // Track last signal type for stateful filtering
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
    setBacktestDataForReplay(candles, trades, onTradeCallback, resolution = '1', replayStartIndex = 0, onProgressCallback = null) {
        console.log("[ChartDatafeed] Setting backtest data (replay mode):", candles.length, "candles,", trades.length, "trades");

        // CRITICAL: Unsubscribe from original UDF to stop background fetching
        this._unsubscribeFromOriginal();

        this.customData = candles;
        this.backtestTrades = trades;
        this.tradeCallback = onTradeCallback;
        this.progressCallback = onProgressCallback; // Store progress callback
        this.plottedTradeIndices = new Set();

        this.isCustomMode = true;
        this.isInitialized = true;
        this.allBarsLoaded = true;
        this.currentStep = replayStartIndex; // Start from specified index (shows context candles before replay point)
        this.hasSetInitialRange = false; // Reset so initial view gets set once
        this.playbackStartTime = candles.length > 0 ? candles[0].time : Date.now();

        // Force chart reset with correct resolution
        if (window.tvWidget) {
            const chart = window.tvWidget.activeChart();

            console.log(`[ChartDatafeed] Replay: Forcing ${resolution} resolution and resetting data...`);
            chart.setResolution(resolution, () => {
                chart.resetData();

                // Report initial progress based on start index
                if (this.progressCallback && candles.length > 0) {
                    const progress = replayStartIndex > 0 ? (replayStartIndex / (candles.length - 1)) * 100 : 0;
                    const initialTime = candles[replayStartIndex].time / 1000;
                    this.progressCallback(progress, initialTime);
                    console.log(`[ChartDatafeed] Initial replay position: ${progress.toFixed(1)}% at ${new Date(initialTime * 1000).toLocaleString()}`);
                }
            });
        }
    }

    // Progressive Replay: Evaluate strategy dynamically as candles appear
    setProgressiveReplayData(candles, strategy, datafeedUrl, replayStartIndex, onProgressCallback, onTradeCallback, resolution) {
        console.log("[Datafeed] Progressive replay mode:", candles.length, "candles, strategy:", strategy);

        this._unsubscribeFromOriginal();

        this.customData = candles;
        this.strategyName = strategy;
        this.datafeedUrl = datafeedUrl;
        this.progressCallback = onProgressCallback;
        this.tradeCallback = onTradeCallback;
        this.evaluatedIndices = new Set();

        this.isCustomMode = true;
        this.isInitialized = true;
        this.allBarsLoaded = true;
        this.currentStep = replayStartIndex;
        this.hasSetInitialRange = false; // Reset so initial view gets set once
        this._initialRefreshDone = false; // Reset so initial chart refresh can happen
        this.lastSignalType = null; // Reset signal state for new replay
        this.playbackStartTime = candles.length > 0 ? candles[0].time : Date.now();

        if (window.tvWidget) {
            const chart = window.tvWidget.activeChart();

            // CRITICAL FIX: Always reset data first, regardless of resolution
            // This ensures Jan 1st (live) data is cleared before we enter custom mode
            console.log("[Datafeed] Clearing chart data...");

            // Force clear by resetting data immediately
            chart.resetData();

            // Then set resolution (in case it differs)
            const currentRes = chart.resolution();
            if (currentRes !== resolution) {
                console.log(`[Datafeed] Changing resolution from ${currentRes} to ${resolution}`);
                chart.setResolution(resolution, () => {
                    console.log("[Datafeed] Resolution changed, resetting data again");
                    chart.resetData();
                });
            }

            // Set initial progress
            if (this.progressCallback && candles.length > 0) {
                const progress = replayStartIndex > 0 ? (replayStartIndex / (candles.length - 1)) * 100 : 0;
                const initialTime = candles[replayStartIndex].time / 1000;
                this.progressCallback(progress, initialTime);
            }
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

            // CRITICAL FIX: Return noData:false if we're at the leading edge (more data will come)
            // This tells TradingView to call subscribeBars for future updates
            const atLeadingEdge = this.currentStep < this.customData.length - 1;
            console.log(`[getBars] At leading edge: ${atLeadingEdge}`);
            onHistoryCallback(visibleBars, { noData: !atLeadingEdge });
            return;
        }

        // If not in custom mode, pass through to original UDF datafeed
        console.log("[Wrapper] Delegating getBars to original datafeed...");
        console.trace("[TRACE] getBars delegation stack:"); // This will show who called getBars
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

        // Calculate and report progress
        if (this.progressCallback && this.customData.length > 0) {
            const progress = (this.currentStep / (this.customData.length - 1)) * 100;
            this.progressCallback(progress, currentBarTimeSeconds);
        }

        // Check for trades to plot
        this.backtestTrades.forEach((trade, idx) => {
            if (!this.plottedTradeIndices.has(idx)) {
                // Trade time is in seconds from backend
                if (trade.time <= currentBarTimeSeconds) {
                    console.log("[Replay] Plotting trade at step", this.currentStep, ":", trade.type, "@", trade.price, "time:", new Date(trade.time * 1000).toLocaleString());
                    this.plottedTradeIndices.add(idx);
                    if (this.tradeCallback) {
                        this.tradeCallback(trade);
                    }
                }
            }
        });

        // Notify all subscribers about the new bar
        const subscriberCount = Object.keys(this.subscribers).length;
        console.log(`[playback_step] Notifying ${subscriberCount} subscribers about bar ${this.currentStep}`);
        Object.keys(this.subscribers).forEach(subId => {
            const sub = this.subscribers[subId];
            if (!sub.lastBarTime || currentBar.time > sub.lastBarTime) {
                console.log(`[playback_step] Pushing bar to subscriber ${subId}: time=${new Date(currentBar.time).toISOString()}`);
                sub.callback(currentBar);
                sub.lastBarTime = currentBar.time;
            }
        });

        // Update the chart display
        this.updateChartDisplay();

        // PROGRESSIVE STRATEGY EVALUATION
        // If in progressive mode, evaluate strategy at current step
        if (this.strategyName && this.datafeedUrl && !this.evaluatedIndices.has(this.currentStep)) {
            this.evaluatedIndices.add(this.currentStep);

            // Get candles up to current step
            const candlesUpToNow = this.customData.slice(0, this.currentStep + 1).map(c => ({
                ...c,
                time: c.time / 1000  // Backend expects seconds
            }));

            // Call backend to evaluate strategy
            const requestBody = {
                strategy: this.strategyName,
                candles: candlesUpToNow,
                current_index: this.currentStep
            };
            // Only include last_action if it has a value (Pydantic v2 rejects null)
            if (this.lastSignalType) {
                requestBody.last_action = this.lastSignalType;
            }

            fetch(`${this.datafeedUrl}/evaluate_strategy_step`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestBody)
            })
                .then(res => res.json())
                .then(data => {
                    if (data.signal && this.tradeCallback) {
                        console.log("[Progressive] Signal found at step", this.currentStep, ":", data.signal.type, "@", data.signal.price);

                        // Update state and execute callback
                        this.lastSignalType = data.signal.type;
                        this.tradeCallback(data.signal);
                    }
                })
                .catch(err => console.error("[Progressive] Evaluation error:", err));
        }

    }

    // Helper to update the chart display
    updateChartDisplay() {
        if (!window.tvWidget) return;

        try {
            const chart = window.tvWidget.activeChart();

            if (!this.customData || this.currentStep >= this.customData.length) return;

            // Since TradingView's Bar Replay Tool is officially UNSUPPORTED in Advanced Charts,
            // and subscribeBars is designed for live streaming (not simulated playback),
            // we must force chart refresh on each step using resetData().
            // Critical: Use resetCache() first to clear TradingView's internal cache
            // This is the documented pattern for forcing data re-fetch (see docs lines 4920-4924)
            if (window.tvWidget) {
                window.tvWidget.resetCache();
            }
            chart.resetData();

            // Get current candle time for auto-scroll
            const currentTime = this.customData[this.currentStep].time / 1000;

            // Get current visible range
            const visibleRange = chart.getVisibleRange();
            if (!visibleRange) return;

            const visibleDuration = visibleRange.to - visibleRange.from;

            // Only auto-scroll if current time is outside visible range or near the edge
            const bufferPercent = 0.1; // 10% buffer at edges
            const bufferTime = visibleDuration * bufferPercent;

            if (currentTime < visibleRange.from + bufferTime || currentTime > visibleRange.to - bufferTime) {
                // Candle is near edge or outside view - auto-scroll to keep it centered
                const halfDuration = visibleDuration / 2;
                chart.setVisibleRange({
                    from: currentTime - halfDuration,
                    to: currentTime + halfDuration
                }).catch(err => {
                    // Silently ignore - user might be manually scrolling
                });
            }
        } catch (err) {
            // Silently ignore errors to not spam console
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
        this.progressCallback = null;

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
