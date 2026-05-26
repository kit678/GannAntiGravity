import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import './App.css'
import { TVChartContainer } from './TVChartContainer'

// Constants and utility functions
const TODAY = new Date();
const formatDate = (date) => date.toISOString().split('T')[0];
const DEFAULT_END_DATE = formatDate(TODAY);
const DEFAULT_START_DATE = '2025-11-07'; // User requested default
const LOOKBACK_BARS = 5000;
const DATAFEED_URL = "http://localhost:8005";
const INTERVAL_TO_TV = { '1m': '1', '5m': '5', '15m': '15', '1h': '60', '4h': '240', '1d': 'D', '1w': 'W', '1M': 'M' };

// Calculate P&L summary - moved outside to stay pure and stable
const calculateSummary = (trades) => {
    let totalPnL = 0;
    let wins = 0;
    let losses = 0;

    trades.forEach(t => {
        if (t.type === 'sell' && t.pnl != null) {
            totalPnL += t.pnl;
            if (t.pnl > 0) wins++;
            else losses++;
        }
    });

    return {
        totalTrades: trades.length,
        completedTrades: wins + losses,
        wins,
        losses,
        totalPnL: Number(totalPnL.toFixed(2)),
        winRate: (wins + losses > 0) ? Number(((wins / (wins + losses)) * 100).toFixed(1)) : 0
    };
};

const resolveNestedKey = (obj, key) => {
    if (!obj || !key) return null;
    const parts = key.split('.');
    let current = obj;
    for (const part of parts) {
        if (current == null) return null;
        current = current[part];
    }
    return current;
};

function App() {
    const [strategy, setStrategy] = useState('mechanical_3day')
    const [filterFan, setFilterFan] = useState('all') // Filter by fan in Price Interactions tab
    const [interactionColumnSchema, setInteractionColumnSchema] = useState(null)
    const [interactionFilterField, setInteractionFilterField] = useState(null)
    const [interactionFilterOptions, setInteractionFilterOptions] = useState([])

    const [instrumentType, setInstrumentType] = useState('spot') // User requested default
    const [dataSource, setDataSource] = useState('yfinance') // User requested default
    
    // Session Configuration
    const [cycleType, setCycleType] = useState('24_hour')
    const [sessionDuration, setSessionDuration] = useState('standard')

    // Pivot settings for Angular Coverage study
    const [pivotLeftBars, setPivotLeftBars] = useState(5)
    const [pivotRightBars, setPivotRightBars] = useState(5)
    const [showIntersectionLabels, setShowIntersectionLabels] = useState(false)
    const [showPatternDots, setShowPatternDots] = useState(false)

    // Fan Visibility Settings
    // 'availableFanLabels' is dynamically populated by the chart based on actually drawn fans
    // Each entry is { identity: 'L131-H130', displayLabel: 'P1 (L131-H130)' }
    const [availableFanLabels, setAvailableFanLabels] = useState([])
    // 'visibleFanLabels' tracks identity keys the user has checked ON (auto-populated as fans appear)
    const [visibleFanLabels, setVisibleFanLabels] = useState([])

    // Use Ref for active symbol to avoid re-rendering chart on every internal symbol change
    // This prevents the "flicker" loop when syncing chart state
    const activeSymbolRef = useRef('^NSEI')
    // This state controls the *initial* symbol passed to the chart when mounting or switching sources
    const [chartMountSymbol, setChartMountSymbol] = useState('^NSEI')
    const [chartMountInterval, setChartMountInterval] = useState('1')

    const [isReplayMode, setIsReplayMode] = useState(false)
    const [tradeLog, setTradeLog] = useState([])
    const [backtestSummary, setBacktestSummary] = useState(null)
    const [replayProgress, setReplayProgress] = useState(0)
    const [replayCurrentDate, setReplayCurrentDate] = useState('')
    const [resultsHeight, setResultsHeight] = useState(35) // Default to closed (just header)
    const [isResizing, setIsResizing] = useState(false)
    const [bottomPanelTab, setBottomPanelTab] = useState('backtest') // 'backtest' | 'interactions'
    const [priceInteractions, setPriceInteractions] = useState([]) // Live interaction log
    const [selectedInteractionIndex, setSelectedInteractionIndex] = useState(0) // Track selected interaction
    const [isChartPlaying, setIsChartPlaying] = useState(false)

    // Hypothesis Navigator State
    const [hypothesisReports, setHypothesisReports] = useState([]);
    const [selectedSymbolRes, setSelectedSymbolRes] = useState('');
    const [selectedRun, setSelectedRun] = useState('');
    const [selectedTimestamp, setSelectedTimestamp] = useState('');
    const [selectedReport, setSelectedReport] = useState('');
    const [hypothesisEvents, setHypothesisEvents] = useState([]);
    const [selectedHypothesisEvent, setSelectedHypothesisEvent] = useState(null);
    const [hypothesisFilter, setHypothesisFilter] = useState('all'); // 'all' | 'win' | 'miss'

    const [strategyTrades, setStrategyTrades] = useState(null);
    const [strategyTradesMode, setStrategyTradesMode] = useState('retest_baseline');
    const [strategyTradesResolution, setStrategyTradesResolution] = useState('1h');
    const [selectedTrade, setSelectedTrade] = useState(null);

    // Cascading dropdown options
    const symbolResOptions = useMemo(() => {
        const seen = new Set();
        return hypothesisReports.filter(r => {
            const key = `${r.symbol}/${r.resolution}`;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        });
    }, [hypothesisReports]);

    const runOptions = useMemo(() => {
        if (!selectedSymbolRes) return [];
        const [sym, res] = selectedSymbolRes.split('/');
        const seen = new Set();
        return hypothesisReports
            .filter(r => r.symbol === sym && r.resolution === res)
            .filter(r => { const k = r.run_id; if (seen.has(k)) return false; seen.add(k); return true; });
    }, [hypothesisReports, selectedSymbolRes]);

    const timestampOptions = useMemo(() => {
        if (!selectedSymbolRes || !selectedRun) return [];
        const [sym, res] = selectedSymbolRes.split('/');
        const seen = new Set();
        return hypothesisReports
            .filter(r => r.symbol === sym && r.resolution === res && r.run_id === selectedRun)
            .filter(r => {
                // Extract timestamp from path: .../hypothesis_reports/HHMMSS_all/...
                const parts = r.path.split('/');
                const ts = parts.find(p => p.match(/^\d{6}(_all)?$/));
                if (!ts) return false;
                if (seen.has(ts)) return false;
                seen.add(ts);
                return true;
            });
    }, [hypothesisReports, selectedSymbolRes, selectedRun]);

    const reportOptions = useMemo(() => {
        if (!selectedSymbolRes || !selectedRun || !selectedTimestamp) return [];
        const [sym, res] = selectedSymbolRes.split('/');
        return hypothesisReports
            .filter(r => r.symbol === sym && r.resolution === res && r.run_id === selectedRun && r.path.includes(selectedTimestamp));
    }, [hypothesisReports, selectedSymbolRes, selectedRun, selectedTimestamp]);

    // Fetch available hypothesis reports on mount
    useEffect(() => {
        fetch('http://localhost:8005/api/hypothesis-reports')
            .then(r => r.json())
            .then(data => setHypothesisReports(data.reports || []))
            .catch(() => {});
    }, []);

    // Reset selected interaction when filter changes
    useEffect(() => {
        setSelectedInteractionIndex(0);
    }, [filterFan]);

    // Handle keyboard navigation for interactions table
    useEffect(() => {
        if (bottomPanelTab !== 'interactions' || priceInteractions.length === 0) return;

        const handleKeyDown = (e) => {
            if (e.key === 'ArrowUp') {
                e.preventDefault();
                setSelectedInteractionIndex(prev => Math.max(0, prev - 1));
            } else if (e.key === 'ArrowDown') {
                e.preventDefault();
                const filterField = interactionFilterField || 'fanIdentity';
                const filteredCount = priceInteractions.filter(hit => {
                    if (filterFan === 'all') return true;
                    const val = resolveNestedKey(hit, filterField);
                    return val === filterFan || (hit.fanIdentity || hit.fan) === filterFan;
                }).length;
                setSelectedInteractionIndex(prev => Math.min(filteredCount - 1, prev + 1));
            }
        };

        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [bottomPanelTab, priceInteractions, filterFan, interactionFilterField]);

    // Replay Toolbar Position State
    const [replayPos, setReplayPos] = useState({ x: window.innerWidth / 2 - 300, y: window.innerHeight - 200 });
    const [isDraggingUI, setIsDraggingUI] = useState(false); // New state to disable chart interaction during drag
    const isDraggingReplay = useRef(false);
    const dragOffset = useRef({ x: 0, y: 0 });



    const chartRef = useRef(null);
    const startDateRef = useRef(null);
    const endDateRef = useRef(null);

    // Sync Active Symbol from Chart
    const handleSymbolChange = useCallback((newSymbol) => {
        // Strip suffixes if present for clean backtest usage? 
        // TradingView might return "RELIANCE" or "^NSEI:YF" depending on feed.
        // We store it as is for now, the backend handles cleaning.
        activeSymbolRef.current = newSymbol;
        console.log("Active Symbol Updated:", activeSymbolRef.current);
    }, []);

    // Handle Data Source Switch
    const handleDataSourceChange = (newSource) => {
        setDataSource(newSource);
        if (newSource === 'yfinance') {
            setChartMountSymbol('^NSEI');
            activeSymbolRef.current = '^NSEI';
        } else if (newSource === 'binance') {
            setChartMountSymbol('BTCUSDT');
            activeSymbolRef.current = 'BTCUSDT';
        } else {
            setChartMountSymbol('NIFTY 50');
            activeSymbolRef.current = 'NIFTY 50';
        }
    };


    // Handle trade logged callback
    const handleTradeLogged = useCallback((trade) => {
        setTradeLog(prev => [...prev, trade]);
    }, []);

    // Run Backtest (Instant Mode)
    const handleRunBacktest = async () => {
        if (!startDateRef.current || !endDateRef.current) return;

        const fromDate = startDateRef.current.value;
        const toDate = endDateRef.current.value;
        setResultsHeight(250); // Auto-open results panel on run

        console.log(`Running Backtest: ${strategy} from ${fromDate} to ${toDate}`);
        setTradeLog([]);
        setBacktestSummary(null);

        try {
            // Get resolution from chart
            let currentResolution = '1';
            let currentSymbol = activeSymbolRef.current; // Use the synced symbol logic

            if (chartRef.current) {
                currentResolution = chartRef.current.getResolution();
                console.log("Using Chart Resolution for Backtest:", currentResolution);
            }

            console.log("Backtesting Symbol:", currentSymbol);

            const response = await fetch(`${DATAFEED_URL}/run_backtest`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    strategy: strategy,
                    symbol: currentSymbol, // Use active symbol
                    from_date: fromDate,
                    to_date: toDate,
                    days: 0,
                    resolution: currentResolution, // Send resolution to backend
                    data_source: dataSource,
                    pivotSettings: {
                        leftBars: pivotLeftBars,
                        rightBars: pivotRightBars,
                        showIntersectionLabels: showIntersectionLabels
                    }
                })
            });

            if (!response.ok) {
                alert("Backtest Failed: " + response.statusText);
                return;
            }

            const result = await response.json();
            console.log("Backtest Result:", result);

            // Calculate summary
            const summary = calculateSummary(result.trades);
            setBacktestSummary(summary);

            // Trigger Instant Chart Update
            if (chartRef.current) {
                // Pass the requested resolution to ensure chart alignment
                chartRef.current.startBacktestInstant(result.candles, result.trades, currentResolution, result.markers, result.drawings, result.indicator_series);
            }

            // Hide replay controls in instant mode
            setIsReplayMode(false);

        } catch (error) {
            console.error("Backtest Error:", error);
            alert("Error running backtest: " + error.message);
        }
    };

    // Start Step-by-Step Simulation Mode
    const handleStartReplay = async () => {
        const fromDate = startDateRef.current?.value;
        const toDate = endDateRef.current?.value;

        if (!fromDate || !toDate) {
            alert("Please select a simulation range (Start/End dates).");
            return;
        }

        // Use bar-based lookback - backend will fetch extra bars for context
        const fetchFrom = fromDate;
        const fetchTo = toDate;
        // Use ISO format to ensure consistent parsing across browsers
        const replayStartTimestamp = new Date(fromDate + 'T00:00:00').getTime() / 1000;
        console.log('[Step-by-Step] Simulation start:', fromDate, 'timestamp:', replayStartTimestamp);

        setTradeLog([]);
        setBacktestSummary(null);
        setPriceInteractions([]);
        // Reset position to reasonable default if offscreen
        setReplayPos({ x: window.innerWidth / 2 - 300, y: window.innerHeight - 250 });

        try {
            let currentResolution = '1';
            const currentSymbol = activeSymbolRef.current; // Sync logic

            if (chartRef.current) {
                currentResolution = chartRef.current.getResolution();
            }

            console.log(`[Step-by-Step] Fetching candles: ${fetchFrom} to ${fetchTo}, resolution: ${currentResolution}, strategy: ${strategy}`);

            const response = await fetch(`${DATAFEED_URL}/fetch_candles`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    symbol: currentSymbol,
                    from_date: fetchFrom,
                    to_date: fetchTo,
                    resolution: currentResolution,
                    strategy: strategy,
                    data_source: dataSource,
                    lookback_bars: LOOKBACK_BARS,
                    pivotSettings: {
                        leftBars: pivotLeftBars,
                        rightBars: pivotRightBars,
                        showIntersectionLabels: showIntersectionLabels
                    }
                })
            });

            if (!response.ok) {
                // Try to parse error details
                let errorMessage = response.statusText;
                try {
                    const errorData = await response.json();
                    if (errorData && errorData.detail) {
                        errorMessage = errorData.detail;
                    }
                } catch (e) {
                    console.log("Could not parse error details", e);
                }

                alert("Failed to fetch candles: " + errorMessage);
                setIsReplayMode(false);
                return;
            }

            const data = await response.json();
            console.log(`[Step-by-Step] Fetched ${data.candles.length} candles (includes ${LOOKBACK_BARS} lookback bars for context). Initial Markers: ${data.markers ? data.markers.length : 0}`);

            if (data.strategy_meta && data.strategy_meta.column_schema) {
                setInteractionColumnSchema(data.strategy_meta.column_schema);
                setInteractionFilterField(data.strategy_meta.filter_field || null);
                setInteractionFilterOptions(data.strategy_meta.filter_options || []);
            }

            // Activate UI only after data is ready to prevent race conditions
            setIsReplayMode(true);
            setReplayProgress(0);
            setReplayCurrentDate('');

            if (chartRef.current) {
                chartRef.current.startProgressiveReplay(
                    data.candles,
                    strategy,
                    currentResolution,
                    replayStartTimestamp,
                    DATAFEED_URL,
                    instrumentType,
                    (progress, currentTime) => {
                        setReplayProgress(progress);
                        if (currentTime) {
                            setReplayCurrentDate(new Date(currentTime * 1000).toLocaleString());
                        }
                    },
                    (trade) => {
                        handleTradeLogged(trade);
                    },
                    {
                        leftBars: pivotLeftBars,
                        rightBars: pivotRightBars,
                        showIntersectionLabels: showIntersectionLabels,
                        initialMarkers: data.markers || [], // Pass markers if available
                        initialDrawings: data.drawings || [] // Pass initial drawings (fans) if available
                    }
                );
            }
        } catch (error) {
            console.error("[Step-by-Step] Error:", error);
            alert("Error starting step-by-step simulation: " + error.message);
            setIsReplayMode(false);
        }
    };

    const fetchStrategyTrades = async () => {
        try {
            const sym = activeSymbolRef.current || 'BTCUSDT';
            const res = strategyTradesResolution || '1h';
            const resp = await fetch(`${DATAFEED_URL}/api/binance-strategy-trades?symbol=${encodeURIComponent(sym)}&interval=${encodeURIComponent(res)}`);
            const data = await resp.json();
            setStrategyTrades(data);

            const tradeSymbol = data.symbol || sym;
            const tradeInterval = data.interval || res;
            const tvInterval = INTERVAL_TO_TV[tradeInterval] || '60';
            setStrategyTradesResolution(tradeInterval);

            const isCrypto = /^[A-Z0-9]{2,12}USDT$/.test(tradeSymbol);
            const neededSource = isCrypto ? 'binance' : 'dhan';

            if (dataSource !== neededSource) {
                setDataSource(neededSource);
                setChartMountSymbol(tradeSymbol);
                setChartMountInterval(tvInterval);
                activeSymbolRef.current = tradeSymbol;
            } else if (chartRef.current?.loadSymbolResolution) {
                chartRef.current.loadSymbolResolution(tradeSymbol, tvInterval);
                activeSymbolRef.current = tradeSymbol;
            }

            const mode = 'retest_baseline';
            const trades = data.modes?.[mode] || data.model_a || [];
            if (trades.length > 0) {
                chartRef.current?.clearTradeMarkers?.();
            }
        } catch (e) {
            console.error('Failed to fetch strategy trades:', e);
        }
    };

    // Replay Controls
    const handleReplayAction = (action) => {
        if (!chartRef.current) return;
        if (action === 'play') chartRef.current.togglePlayPause();
        if (action === 'step') chartRef.current.stepForward();
    };

    const handleExitReplay = () => {
        if (chartRef.current) {
            chartRef.current.exitReplay();
        }
        setIsReplayMode(false);
    };

    // Handle resize of results panel
    const handleResizeStart = (e) => {
        setIsResizing(true);
        setIsDraggingUI(true); // Disable chart interaction
        e.preventDefault();
    };

    const handleResizeMove = useCallback((e) => {
        // Handle Panel Resize
        if (isResizing) {
            const windowHeight = window.innerHeight;
            const mouseY = e.clientY;
            const newHeight = windowHeight - mouseY;
            const constrainedHeight = Math.max(35, Math.min(windowHeight * 0.8, newHeight));
            setResultsHeight(constrainedHeight);
        }

        // Handle Replay Toolbar Drag
        if (isDraggingReplay.current) {
            setReplayPos({
                x: e.clientX - dragOffset.current.x,
                y: e.clientY - dragOffset.current.y
            });
        }
    }, [isResizing]);

    const handleResizeEnd = useCallback(() => {
        setIsResizing(false);
        if (isDraggingReplay.current || isResizing) {
            setIsDraggingUI(false); // Re-enable chart interaction
        }
        isDraggingReplay.current = false;
    }, [isResizing]);

    // Replay Drag Handlers
    const handleReplayMouseDown = (e) => {
        // Don't drag if clicking a button/input
        if (['BUTTON', 'SELECT', 'INPUT'].includes(e.target.tagName)) return;

        isDraggingReplay.current = true;
        setIsDraggingUI(true); // Disable chart interaction
        const rect = e.currentTarget.getBoundingClientRect();
        dragOffset.current = {
            x: e.clientX - rect.left,
            y: e.clientY - rect.top
        };
    };

    // Global mouse listeners
    useEffect(() => {
        document.addEventListener('mousemove', handleResizeMove);
        document.addEventListener('mouseup', handleResizeEnd);
        return () => {
            document.removeEventListener('mousemove', handleResizeMove);
            document.removeEventListener('mouseup', handleResizeEnd);
        };
    }, [handleResizeMove, handleResizeEnd]); // Dependency updated to handle stable callbacks

    // Hypothesis Navigator Filter
    const filteredHypothesisEvents = hypothesisEvents.filter(evt => {
        if (hypothesisFilter === 'win') return evt.outcome === 'WIN' || evt.status === 'ACCEPTED';
        if (hypothesisFilter === 'miss') return evt.outcome === 'MISS' || evt.status === 'REJECTED' || evt.status === 'NO_PULLBACK_FOUND';
        return true;
    });

    const filterField = interactionFilterField || 'fanIdentity';
    const filteredInteractions = priceInteractions.filter(hit => {
        if (filterFan === 'all') return true;
        const val = resolveNestedKey(hit, filterField);
        return val === filterFan || (hit.fanIdentity || hit.fan) === filterFan;
    });
    const selectedInteraction = filteredInteractions[selectedInteractionIndex] || null;

    return (
        <div className="app-container">
            <header className="app-header">
                <div className="controls">
                    <select value={strategy} onChange={(e) => setStrategy(e.target.value)}>
                        <option value="mechanical_3day">Mechanical 3-Day Swing</option>
                        <option value="five_ema">5 EMA Breakout Strategy</option>
                        <option value="ema_crossover">9/21 EMA Crossover Strategy</option>
                        <option value="angular_coverage">Angular Price Coverage Study</option>
                        <option value="pivot_points_only">Pivot Points Only</option>
                        <option value="ichimoku_cloud">Ichimoku Cloud Breakout</option>
                        <option value="gann_square_9">Gann Square of 9</option>
                    </select>

                    <select value={instrumentType} onChange={(e) => setInstrumentType(e.target.value)} className="instrument-select">
                        <option value="options">Options</option>
                        <option value="spot">Spot</option>
                    </select>

                    <select value={dataSource} onChange={(e) => handleDataSourceChange(e.target.value)} className="data-source-select">
                        <option value="dhan">Dhan API</option>
                        <option value="yfinance">Yahoo Finance (Free)</option>
                        <option value="binance">Binance (Crypto)</option>
                    </select>
                    
                    <select value={cycleType} onChange={(e) => setCycleType(e.target.value)} className="cycle-type-select">
                        <option value="24_hour">24-Hour Cycle</option>
                        <option value="trading_day">Trading Day Cycle</option>
                    </select>
                    
                    <select value={sessionDuration} onChange={(e) => setSessionDuration(e.target.value)} className="session-duration-select">
                        <option value="standard">Standard</option>
                        <option value="390_minute">6.5 Hours (390 min)</option>
                        <option value="360_minute">6 Hours (360 min)</option>
                    </select>

                    <div className="date-range-picker">
                        <label>Start: <input type="date" defaultValue={DEFAULT_START_DATE} ref={startDateRef} /></label>
                        <label>End: <input type="date" defaultValue={DEFAULT_END_DATE} ref={endDateRef} /></label>
                    </div>

                    {/* Pivot settings - only show for Angular Coverage study and Pivot Points Only */}
                    {(strategy === 'angular_coverage' || strategy === 'pivot_points_only') && (
                        <div className="pivot-settings">
                            <label title="Bars to the left of candidate candle for pivot detection">
                                L: <input type="number" min="1" max="50" value={pivotLeftBars}
                                    onChange={(e) => setPivotLeftBars(Math.max(1, parseInt(e.target.value, 10) || 5))}
                                    style={{ width: '40px' }} />
                            </label>
                            <label title="Bars to the right of candidate candle for pivot detection">
                                R: <input type="number" min="1" max="50" value={pivotRightBars}
                                    onChange={(e) => setPivotRightBars(Math.max(1, parseInt(e.target.value, 10) || 5))}
                                    style={{ width: '40px' }} />
                            </label>

                            {strategy === 'angular_coverage' && (
                                <label title="Draw text labels showing hit prices on intersections" style={{ display: 'flex', alignItems: 'center' }}>
                                    <input type="checkbox"
                                        checked={showIntersectionLabels}
                                        onChange={(e) => setShowIntersectionLabels(e.target.checked)}
                                    /> Show Intersections
                                </label>
                            )}

                            <label title="Show candle pattern circles above/below candles" style={{ display: 'flex', alignItems: 'center' }}>
                                <input type="checkbox"
                                    checked={showPatternDots}
                                    onChange={(e) => setShowPatternDots(e.target.checked)}
                                /> Show Patterns
                            </label>

                            {strategy === 'angular_coverage' && availableFanLabels.length > 0 && (
                                <div className="fan-toggles" style={{ display: 'flex', gap: '8px', marginLeft: '10px', fontSize: '11px', alignItems: 'center' }}>
                                    <button
                                        onClick={() => setVisibleFanLabels(availableFanLabels.map(f => f.identity))}
                                        style={{ padding: '2px 6px', fontSize: '10px', cursor: 'pointer' }}
                                    >
                                        Show All
                                    </button>
                                    <button
                                        onClick={() => setVisibleFanLabels([])}
                                        style={{ padding: '2px 6px', fontSize: '10px', cursor: 'pointer' }}
                                    >
                                        Clear All
                                    </button>
                                    {availableFanLabels.map(fan => (
                                        <label key={fan.identity} style={{ display: 'flex', alignItems: 'center' }}>
                                            <input type="checkbox"
                                                checked={visibleFanLabels.includes(fan.identity)}
                                                onChange={(e) => {
                                                    const newLabels = e.target.checked
                                                        ? [...visibleFanLabels, fan.identity]
                                                        : visibleFanLabels.filter(l => l !== fan.identity);
                                                    setVisibleFanLabels(newLabels);
                                                }}
                                            /> {fan.displayLabel}
                                        </label>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}

                    <button className="run-backtest-btn" onClick={handleRunBacktest}>
                        ⚡ Run Instant
                    </button>

                    <button className="replay-btn" onClick={handleStartReplay}>
                        ▶ Run Step-by-Step
                    </button>
                </div>
            </header>

            <div className="main-content">
                <div className="chart-wrapper" style={{ pointerEvents: isDraggingUI ? 'none' : 'auto' }}>
                    <TVChartContainer
                        ref={chartRef}
                        symbol={chartMountSymbol}
                        datafeedUrl={DATAFEED_URL}
                        dataSource={dataSource}
                        cycleType={cycleType}
                        sessionDuration={sessionDuration}
                        onTradeLogged={handleTradeLogged}
                        onSymbolChange={handleSymbolChange}
                        instrumentType={instrumentType}
                        interval={chartMountInterval}
                        visibleFanLabels={visibleFanLabels}
                        showPatternLegend={strategy === 'angular_coverage'}
                        showPatternDots={showPatternDots}
                        onAvailableFansUpdated={setAvailableFanLabels}
                        onPlayingStateChange={setIsChartPlaying}
                        selectedInteraction={selectedInteraction}
                        onAutoEnableVisibility={(newIds) => setVisibleFanLabels(prev => [...new Set([...prev, ...newIds])])}
                        onPriceInteraction={(hit) => {
                            console.log("[App] Received interaction:", hit);
                            setPriceInteractions(prev => {
                                // Prevent exact duplicates if backend sends them twice in the same bar
                                const isDup = prev.some(p =>
                                    p.time === hit.time &&
                                    p.fanIdentity === hit.fanIdentity &&
                                    p.type === hit.type &&
                                    p.fraction === hit.fraction
                                );
                                if (isDup) return prev;
                                return [...prev, hit];
                            });
                        }}
                        onStrategyMeta={(meta) => {
                            if (meta.column_schema) {
                                setInteractionColumnSchema(meta.column_schema);
                            }
                            if (meta.filter_field) {
                                setInteractionFilterField(meta.filter_field);
                            }
                            if (meta.filter_options) {
                                setInteractionFilterOptions(meta.filter_options);
                            }
                        }}
                    />
                </div>

                <div className="resize-handle" onMouseDown={handleResizeStart}></div>

                <div className="bottom-panel" style={{ height: `${resultsHeight}px` }}>
                    {/* Tab Bar */}
                    <div className="panel-tabs">
                        <button
                            className={`panel-tab${bottomPanelTab === 'backtest' ? ' active' : ''}`}
                            onClick={() => setBottomPanelTab('backtest')}
                        >
                            Backtest Results
                        </button>
                        <button
                            className={`panel-tab${bottomPanelTab === 'interactions' ? ' active' : ''}`}
                            onClick={() => { setBottomPanelTab('interactions'); if (resultsHeight <= 40) setResultsHeight(180); }}
                        >
                            Price Interactions {priceInteractions.length > 0 && <span className="tab-badge">{priceInteractions.length}</span>}
                        </button>
                        <button
                            className={`panel-tab${bottomPanelTab === 'hypothesis' ? ' active' : ''}`}
                            onClick={() => { setBottomPanelTab('hypothesis'); if (resultsHeight <= 40) setResultsHeight(200); }}
                        >
                            Hypothesis Navigator {hypothesisEvents.length > 0 && <span className="tab-badge">{hypothesisEvents.length}</span>}
                        </button>
                        <button
                            className={`panel-tab${bottomPanelTab === 'strategy_trades' ? ' active' : ''}`}
                            onClick={() => { 
                                setBottomPanelTab('strategy_trades'); 
                                if (resultsHeight <= 40) setResultsHeight(200); 
                            }}
                        >
                            Strategy Trades
                        </button>
                        <span className="panel-drag-hint">
                            {resultsHeight <= 40 ? '↑ Drag to expand' : ''}
                        </span>
                    </div>

                    {/* Tab Content */}
                    <div className="results-content">
                        {bottomPanelTab === 'backtest' && (
                            <>
                                {backtestSummary ? (
                                    <div className="summary">
                                        <p><strong>Strategy:</strong> {strategy}</p>
                                        <p><strong>Total Signals:</strong> {backtestSummary.totalTrades}</p>
                                        <p><strong>Completed Trades:</strong> {backtestSummary.completedTrades}</p>
                                        <p><strong>Win Rate:</strong> {backtestSummary.winRate}%</p>
                                        <p><strong>Total P&L:</strong> <span style={{ color: backtestSummary.totalPnL >= 0 ? '#00E676' : '#FF5252' }}>{backtestSummary.totalPnL}</span></p>
                                    </div>
                                ) : (
                                    <p>Select a strategy and run backtest to see results here.</p>
                                )}

                                {tradeLog.length > 0 && (
                                    <div className="trade-log">
                                        <h4>Trade Log ({tradeLog.length})</h4>
                                        <ul>
                                            {tradeLog.map((t, i) => (
                                                <li key={i} style={{ color: t.type === 'buy' ? '#00E676' : '#FF5252' }}>
                                                    {t.label ? (
                                                        <span>
                                                            {t.label}
                                                            {t.option_price && <span style={{ color: '#FFD700' }}> @ ₹{t.option_price.toFixed(2)}</span>}
                                                        </span>
                                                    ) : (
                                                        <span>{t.type.toUpperCase()} @ {t.price != null ? t.price.toFixed(2) : 'N/A'}</span>
                                                    )}
                                                    {t.pnl != null && ` | P&L: ${t.pnl.toFixed(2)}`}
                                                    <span style={{ color: '#888', marginLeft: '10px' }}>
                                                        ({new Date(t.time * 1000).toLocaleString()})
                                                    </span>
                                                </li>
                                            ))}
                                        </ul>
                                    </div>
                                )}
                            </>
                        )}

                        {bottomPanelTab === 'interactions' && (
                            <div className="interactions-list">
                                {priceInteractions.length === 0 ? (
                                    <p>No price interactions recorded yet. Start a step-by-step simulation with Show Intersections enabled.</p>
                                ) : (
                                    (() => {
                                        const schema = interactionColumnSchema || [
                                            {"key": "time",                          "label": "Time",            "width": "140px", "format": "datetime"},
                                            {"key": "strategy_data.fan",             "label": "Fan",             "width": "120px", "format": "text"},
                                            {"key": "strategy_data.fraction",        "label": "Fraction",        "width": "70px",  "format": "text"},
                                            {"key": "type",                          "label": "Type",            "width": "110px", "format": "text"},
                                            {"key": "price",                         "label": "Price",           "width": "80px",  "format": "price"},
                                            {"key": "details",                       "label": "Details",         "width": "200px", "format": "text"},
                                            {"key": "open",                          "label": "O",               "width": "60px",  "format": "price"},
                                            {"key": "high",                          "label": "H",               "width": "60px",  "format": "price"},
                                            {"key": "low",                           "label": "L",               "width": "60px",  "format": "price"},
                                            {"key": "close",                         "label": "C",               "width": "60px",  "format": "price"},
                                            {"key": "strategy_data.cluster",         "label": "Cluster",         "width": "70px",  "format": "text"},
                                            {"key": "strategy_data.zone",            "label": "Zone",            "width": "80px",  "format": "text"},
                                            {"key": "strategy_data.zoneExtremes",    "label": "Zone Extremes",   "width": "140px", "format": "text"},
                                            {"key": "strategy_data.nextAngleLine",   "label": "Next Angle Line", "width": "110px", "format": "text"},
                                        ];
                                        
                                        const filterFieldLocal = interactionFilterField || 'fanIdentity';
                                        const filterOptions = interactionFilterOptions.length > 0 
                                            ? interactionFilterOptions 
                                            : [...new Set(priceInteractions.map(h => resolveNestedKey(h, filterFieldLocal)))]
                                                .filter(Boolean).sort();
                                        
                                        const filteredData = priceInteractions.filter(hit => {
                                            if (filterFan === 'all') return true;
                                            const val = resolveNestedKey(hit, filterFieldLocal);
                                            return val === filterFan || (hit.fanIdentity || hit.fan) === filterFan;
                                        });

                                        const formatCell = (hit, col) => {
                                            const val = resolveNestedKey(hit, col.key);
                                            if (val == null || val === '') return '-';
                                            if (col.format === 'datetime') return new Date(val * 1000).toLocaleString().replace(/,/g, '');
                                            if (col.format === 'price' && typeof val === 'number') return val.toFixed(2);
                                            if (typeof val === 'object') {
                                                if (val.highest_close != null) return `${val.lowest_close?.toFixed(2) || '-'} - ${val.highest_close?.toFixed(2)}`;
                                                return JSON.stringify(val).replace(/,/g, ';');
                                            }
                                            if (typeof val === 'boolean') return val ? 'Yes' : 'No';
                                            return String(val);
                                        };

                                        const buildCsvRows = (data, includeHeader) => {
                                            const rows = [];
                                            if (includeHeader) rows.push(schema.map(c => c.label));
                                            data.forEach((hit) => {
                                                rows.push(schema.map(c => formatCell(hit, c)));
                                            });
                                            return rows;
                                        };

                                        const displayLabel = interactionFilterField 
                                            ? interactionFilterField.split('.').pop().replace(/_/g, ' ') 
                                            : 'Fan';

                                        return (
                                            <>
                                                <div style={{ marginBottom: '10px', display: 'flex', gap: '10px', alignItems: 'center', justifyContent: 'space-between', position: 'sticky', top: 0, zIndex: 10, backgroundColor: '#1e1e1e', paddingTop: '4px' }}>
                                                    <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                                                        <label style={{ fontSize: '12px' }}>
                                                            Filter by {displayLabel}:
                                                            <select
                                                                value={filterFan}
                                                                onChange={(e) => setFilterFan(e.target.value)}
                                                                style={{ marginLeft: '5px', padding: '2px 5px', fontSize: '11px', textTransform: 'capitalize' }}
                                                            >
                                                                <option value="all">All</option>
                                                                {filterOptions.map(opt => (
                                                                    <option key={String(opt)} value={String(opt)}>{String(opt)}</option>
                                                                ))}
                                                            </select>
                                                        </label>
                                                        <span style={{ fontSize: '11px', color: '#888' }}>
                                                            Showing {filteredData.length} of {priceInteractions.length} events
                                                        </span>
                                                    </div>
                                                    <div style={{ display: 'flex', gap: '8px' }}>
                                                        <button 
                                                            onClick={() => {
                                                                const rows = buildCsvRows(filteredData, true);
                                                                const tsvContent = rows.map(e => e.join("\t")).join("\n");
                                                                navigator.clipboard.writeText(tsvContent).then(() => {
                                                                    alert("Table copied to clipboard!");
                                                                }).catch(err => console.error(err));
                                                            }}
                                                            style={{ padding: '4px 8px', fontSize: '11px', cursor: 'pointer', backgroundColor: '#4CAF50', color: 'white', border: 'none', borderRadius: '3px' }}
                                                        >Copy Table</button>
                                                        <button 
                                                            onClick={() => {
                                                                const rows = buildCsvRows(priceInteractions, true);
                                                                const csvContent = rows.map(e => e.join(",")).join("\n");
                                                                const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
                                                                const url = URL.createObjectURL(blob);
                                                                const link = document.createElement("a");
                                                                link.setAttribute("href", url);
                                                                link.setAttribute("download", "frontend_price_interactions.csv");
                                                                document.body.appendChild(link);
                                                                link.click();
                                                                document.body.removeChild(link);
                                                                URL.revokeObjectURL(url);
                                                            }}
                                                            style={{ padding: '4px 8px', fontSize: '11px', cursor: 'pointer', backgroundColor: '#2196F3', color: 'white', border: 'none', borderRadius: '3px' }}
                                                        >Export CSV</button>
                                                    </div>
                                                </div>
                                                <div className="table-container" style={{ overflowX: 'auto' }}>
                                                    <table className="interactions-table" style={{ whiteSpace: 'nowrap' }}>
                                                        <thead>
                                                            <tr>
                                                                <th>#</th>
                                                                {schema.map(col => (
                                                                    <th key={col.key} style={col.width ? {minWidth: col.width} : {}}>
                                                                        {col.label}
                                                                    </th>
                                                                ))}
                                                            </tr>
                                                        </thead>
                                                        <tbody>
                                                            {filteredData.map((hit, i) => (
                                                                <tr 
                                                                    key={i}
                                                                    className={i === selectedInteractionIndex ? 'selected-row' : ''}
                                                                    onClick={() => setSelectedInteractionIndex(i)}
                                                                    style={{ cursor: 'pointer' }}
                                                                >
                                                                    <td>{i + 1}</td>
                                                                    {schema.map(col => (
                                                                        <td key={col.key} style={{ fontSize: '11px' }}>
                                                                            {formatCell(hit, col)}
                                                                        </td>
                                                                    ))}
                                                                </tr>
                                                            ))}
                                                        </tbody>
                                                    </table>
                                                </div>
                                            </>
                                        );
                                    })()
                                )}
                            </div>
                        )}

                        {bottomPanelTab === 'hypothesis' && (
                            <div className="hypothesis-navigator">
                                <div style={{ marginBottom: '10px', display: 'flex', gap: '6px', alignItems: 'center', flexWrap: 'wrap' }}>
                                    <select
                                        value={selectedSymbolRes}
                                        onChange={(e) => {
                                            const val = e.target.value;
                                            setSelectedSymbolRes(val);
                                            setSelectedRun('');
                                            setSelectedTimestamp('');
                                            setSelectedReport('');
                                            setHypothesisEvents([]);
                                            setSelectedHypothesisEvent(null);
                                            // Load the symbol at the selected resolution on the chart
                                            if (val && chartRef.current?.loadSymbolResolution) {
                                                const [sym, res] = val.split('/');
                                                chartRef.current.loadSymbolResolution(sym, res);
                                            }
                                        }}
                                        style={{ padding: '2px 5px', fontSize: '11px', maxWidth: '120px' }}
                                    >
                                        <option value="">Symbol / TF</option>
                                        {symbolResOptions.map(r => (
                                            <option key={`${r.symbol}/${r.resolution}`} value={`${r.symbol}/${r.resolution}`}>
                                                {r.symbol} / {r.resolution}m
                                            </option>
                                        ))}
                                    </select>
                                    <select
                                        value={selectedRun}
                                        onChange={(e) => {
                                            setSelectedRun(e.target.value);
                                            setSelectedTimestamp('');
                                            setSelectedReport('');
                                            setHypothesisEvents([]);
                                            setSelectedHypothesisEvent(null);
                                        }}
                                        disabled={!selectedSymbolRes}
                                        style={{ padding: '2px 5px', fontSize: '11px', maxWidth: '170px' }}
                                    >
                                        <option value="">Run</option>
                                        {runOptions.map(r => (
                                            <option key={r.run_id} value={r.run_id}>{r.run_id}</option>
                                        ))}
                                    </select>
                                    <select
                                        value={selectedTimestamp}
                                        onChange={(e) => {
                                            setSelectedTimestamp(e.target.value);
                                            setSelectedReport('');
                                            setHypothesisEvents([]);
                                            setSelectedHypothesisEvent(null);
                                        }}
                                        disabled={!selectedRun}
                                        style={{ padding: '2px 5px', fontSize: '11px', maxWidth: '110px' }}
                                    >
                                        <option value="">Timestamp</option>
                                        {timestampOptions.map(r => {
                                            const parts = r.path.split('/');
                                            const ts = parts.find(p => p.match(/^\d{6}(_all)?$/)) || '';
                                            const hour = ts.slice(0, 2);
                                            const min = ts.slice(2, 4);
                                            const sec = ts.slice(4, 6);
                                            return <option key={ts} value={ts}>{hour}:{min}:{sec}</option>;
                                        })}
                                    </select>
                                    <select
                                        value={selectedReport}
                                        onChange={(e) => {
                                            const path = e.target.value;
                                            setSelectedReport(path);
                                            setHypothesisEvents([]);
                                            setSelectedHypothesisEvent(null);
                                            if (chartRef.current?.resetNavigationState) {
                                                chartRef.current.resetNavigationState();
                                            }
                                            if (!path) return;
                                            fetch(`http://localhost:8005/api/hypothesis-reports/${path}`)
                                                .then(r => r.json())
                                                .then(data => {
                                                    let raw = [];
                                                    if (data.live_events || data.retro_events) {
                                                        raw = [
                                                            ...(data.live_events || []).map(e => ({ ...e, is_retro: false })),
                                                            ...(data.retro_events || []).map(e => ({ ...e, is_retro: true })),
                                                        ];
                                                    } else if (data.events) {
                                                        raw = data.events;
                                                    }
                                                    const events = raw.map((evt, i) => {
                                                        const timeStr = evt.time || evt.datetime || '';
                                                        let timestamp = null;
                                                        if (timeStr && typeof timeStr === 'string') {
                                                            // pandas format: "4/29/2026, 1:35:00 PM" — strip commas for reliable parsing
                                                            const clean = timeStr.replace(/,/g, '');
                                                            const ts = new Date(clean).getTime();
                                                            if (!isNaN(ts)) timestamp = Math.floor(ts / 1000);
                                                        }
                                                        return {
                                                            ...evt,
                                                            event_id: i + 1,
                                                            event_type: evt.event_type || evt.type || '-',
                                                            datetime: timeStr || '-',
                                                            timestamp: timestamp,  // numeric unix seconds
                                                            fan_display: evt.fan_display || evt.fan || evt.fan_identity || 'Unknown',
                                                            price: evt.price != null ? evt.price : (evt.target_price != null ? evt.target_price : null),
                                                            mfe: evt.mfe != null ? evt.mfe : (evt.mfe_10 != null ? evt.mfe_10 : null),
                                                            mae: evt.mae != null ? evt.mae : (evt.mae_10 != null ? evt.mae_10 : null),
                                                            outcome: evt.outcome || evt.status || null,
                                                            fan_geometry: evt.fan_geometry || null,
                                                        };
                                                    });
                                                    setHypothesisEvents(events);
                                                })
                                                .catch(err => {
                                                    console.error("[Hypothesis] Failed to load report:", err);
                                                    alert("Failed to load hypothesis report");
                                                });
                                        }}
                                        disabled={!selectedRun}
                                        style={{ padding: '2px 5px', fontSize: '11px', maxWidth: '220px' }}
                                    >
                                        <option value="">Report</option>
                                        {reportOptions.map(r => (
                                            <option key={r.path} value={r.path}>{r.report_name}</option>
                                        ))}
                                    </select>
                                    <select
                                        value={hypothesisFilter}
                                        onChange={(e) => setHypothesisFilter(e.target.value)}
                                        style={{ padding: '2px 5px', fontSize: '11px' }}
                                    >
                                        <option value="all">All Events</option>
                                        <option value="win">WIN Only</option>
                                        <option value="miss">MISS Only</option>
                                    </select>
                                    <span style={{ fontSize: '11px', color: '#888' }}>
                                        {filteredHypothesisEvents.length} of {hypothesisEvents.length} events
                                    </span>
                                    {selectedHypothesisEvent && (
                                        <span style={{ fontSize: '11px', color: '#FFEB3B' }}>
                                            Selected: {selectedHypothesisEvent.datetime} | {selectedHypothesisEvent.fan_display} | {selectedHypothesisEvent.event_type}
                                        </span>
                                    )}
                                </div>
                                {hypothesisEvents.length === 0 ? (
                                    <p style={{ fontSize: '12px', color: '#888' }}>Select a report to begin verification.</p>
                                ) : (
                                    <div className="table-container" style={{ overflowX: 'auto' }}>
                                        <table className="interactions-table" style={{ whiteSpace: 'nowrap', fontSize: '11px' }}>
                                            <thead>
                                                <tr>
                                                    <th>#</th>
                                                    <th>Type</th>
                                                    <th>DateTime</th>
                                                    <th>Fan</th>
                                                    <th>Frac</th>
                                                    <th>Target</th>
                                                    <th>Price</th>
                                                    <th>Breach</th>
                                                    <th>Outcome</th>
                                                    <th>MFE</th>
                                                    <th>MAE</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {filteredHypothesisEvents.map((evt, i) => (
                                                    <tr
                                                        key={i}
                                                        className={selectedHypothesisEvent === evt ? 'selected-row' : ''}
                                                        onClick={() => {
                                                            setSelectedHypothesisEvent(evt);
                                                            if (chartRef.current?.navigateToHypothesisEvent) {
                                                                chartRef.current.navigateToHypothesisEvent(evt);
                                                            }
                                                        }}
                                                        style={{ cursor: 'pointer' }}
                                                    >
                                                        <td>{evt.event_id}</td>
                                                        <td style={{ color: evt.is_retro ? '#FF9800' : '#4CAF50', fontSize: '10px' }}>
                                                            {evt.is_retro ? 'RETRO' : 'LIVE'}
                                                        </td>
                                                        <td style={{ fontSize: '10px' }}>{evt.datetime}</td>
                                                        <td style={{ color: '#90CAF9', fontSize: '10px' }}>{evt.fan_display}</td>
                                                        <td style={{ color: '#FFEB3B' }}>{evt.fraction != null ? evt.fraction : '-'}</td>
                                                        <td style={{ color: '#FFEB3B' }}>{evt.next_angle != null ? evt.next_angle : '-'}</td>
                                                        <td>{evt.price != null ? Number(evt.price).toFixed(2) : '-'}</td>
                                                        <td style={{ fontSize: '9px' }}>
                                                            {evt.breach_time ? `${evt.breach_time} ${(evt.breach_direction||'').toUpperCase()}${evt.breach_fraction ? ' @'+evt.breach_fraction : ''}${evt.breach_price ? ' '+Number(evt.breach_price).toFixed(2) : ''}` : '-'}
                                                        </td>
                                                        <td style={{ color: evt.outcome === 'WIN' || evt.status === 'ACCEPTED' ? '#4CAF50' : evt.outcome === 'MISS' || evt.status === 'REJECTED' || evt.status === 'NO_PULLBACK_FOUND' ? '#F44336' : '#888', fontWeight: 600 }}>
                                                            {evt.outcome || (evt.status ? evt.status.replace(/_/g, ' ') : '-')}
                                                        </td>
                                                        <td>{evt.mfe != null ? Number(evt.mfe).toFixed(2) : '-'}</td>
                                                        <td>{evt.mae != null ? Number(evt.mae).toFixed(2) : '-'}</td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                )}
                            </div>
                        )}

                        {bottomPanelTab === 'strategy_trades' && (
                            <div className="strategy-trades-panel">
                                <div style={{ padding: '10px' }}>
                                    <div style={{ marginBottom: '8px', display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
                                        <span style={{ fontSize: '11px', color: '#888' }}>
                                            Chart: <b>{activeSymbolRef.current}</b>
                                        </span>
                                        <label style={{ fontSize: '11px' }}>
                                            Res:
                                            <select
                                                value={strategyTradesResolution}
                                                onChange={e => setStrategyTradesResolution(e.target.value)}
                                                style={{ marginLeft: '3px', padding: '2px 5px', fontSize: '11px' }}
                                            >
                                                <option value="15m">15m</option>
                                                <option value="30m">30m</option>
                                                <option value="1h">1h</option>
                                                <option value="4h">4h</option>
                                                <option value="1d">1D</option>
                                            </select>
                                        </label>
                                        <button onClick={fetchStrategyTrades} style={{ padding: '4px 10px', cursor: 'pointer', fontSize: '11px' }}>
                                            {strategyTrades ? 'Reload Trades' : 'Load Trades'}
                                        </button>
                                        {strategyTrades && (
                                            <>
                                                <label style={{ fontSize: '11px' }}>
                                                    Mode:
                                                    <select
                                                        value={strategyTradesMode}
                                                        onChange={e => setStrategyTradesMode(e.target.value)}
                                                        style={{ marginLeft: '3px', padding: '2px 5px', fontSize: '11px' }}
                                                    >
                                                        <option value="retest_baseline">Retest Baseline</option>
                                                        <option value="breach_immediate">Breach Immediate</option>
                                                        <option value="retest_momentum">Retest Momentum-Gated</option>
                                                        <option value="model_a">Model A (Generic)</option>
                                                    </select>
                                                </label>
                                                <span style={{ fontSize: '11px', color: '#888' }}>
                                                    {(strategyTradesMode === 'model_a' 
                                                        ? (strategyTrades.model_a || []).filter(t => t.outcome && t.outcome !== 'OPEN').length
                                                        : (strategyTrades.modes?.[strategyTradesMode] || []).filter(t => t.outcome && t.outcome !== 'OPEN').length
                                                    )} closed
                                                </span>
                                                {strategyTrades.file_mtime_iso && (
                                                    <span style={{ fontSize: '10px', color: '#666', marginLeft: '8px' }}>
                                                        📄 {strategyTrades.file_name || ''} · {strategyTrades.file_mtime_iso.replace('T', ' ')}
                                                    </span>
                                                )}
                                            </>
                                        )}
                                    </div>
                                    {!strategyTrades ? (
                                        <div style={{ padding: '12px', background: '#1a1a2e', borderRadius: '4px' }}>
                                            <p style={{ fontSize: '12px', color: '#aaa', margin: 0, lineHeight: '1.6' }}>
                                                <b>How to use:</b><br />
                                                1. Switch data source to <b>Binance</b> and load a chart<br />
                                                2. Run replay in terminal:<br />
                                                <code style={{ display: 'block', background: '#333', padding: '4px 8px', margin: '4px 0', borderRadius: '3px', fontSize: '11px' }}>
                                                    cd backend && python run_binance_live.py BTCUSDT 1h 500 --target-progression
                                                </code>
                                                3. Click <b>Load Trades</b> above<br />
                                                4. Click any row to see fan rays on the chart
                                            </p>
                                        </div>
                                    ) : (
                                        (() => {
                                            const fmtTs = (ts) => {
                                                if (!ts || ts < 100000) return '-';
                                                const d = new Date(ts * 1000);
                                                return d.toISOString().replace('T', ' ').slice(0, 16);
                                            };
                                            const fmtPivot = (g, key) => {
                                                const p = g?.[key];
                                                if (!p?.time) return '-';
                                                const d = new Date(p.time * 1000);
                                                const ds = d.toISOString().replace('T', ' ').slice(5, 16);
                                                const lbl = (p.label || '').toUpperCase();
                                                return `${lbl} ${ds}`;
                                            };
                                            const copyTrade = (t, i) => {
                                                const lines = [
                                                    `#${i + 1} | ${t.fan || '-'} | ${t.side || '-'} | ${t.progression_step || '-'}`,
                                                    `Entry: ${fmtTs(t.entry_time)} @ ${t.entry_price != null ? t.entry_price.toFixed(2) : '-'}`,
                                                    `Exit:  ${fmtTs(t.exit_time)} @ ${t.exit_price != null ? t.exit_price.toFixed(2) : '-'}`,
                                                    `PnL:   ${t.pnl != null ? (t.pnl >= 0 ? '+' : '') + t.pnl.toFixed(2) : '-'} | ${t.outcome || '-'}`,
                                                    `Target: ${t.current_target || '-'} | Mom: ${t.momentum_state || '-'} | Retest: ${t.retest_type || t.entry_path || '-'}${t.stop_triggered ? ' | STOPPED' : ''}`,
                                                    `Origin: ${fmtPivot(t.fan_geometry, 'origin')} | Anchor: ${fmtPivot(t.fan_geometry, 'anchor')}`,
                                                ];
                                                navigator.clipboard.writeText(lines.join('\n')).catch(() => {});
                                            };
                                            const filtered = (strategyTradesMode === 'model_a'
                                                    ? (strategyTrades.model_a || [])
                                                    : (strategyTrades.modes?.[strategyTradesMode] || [])
                                                ).filter(t => t.outcome && t.outcome !== 'OPEN');
                                            return (
                                        <div className="table-container" style={{ overflowX: 'auto', maxHeight: '50vh', overflowY: 'auto' }}>
                                            <table className="interactions-table" style={{ whiteSpace: 'nowrap', fontSize: '10px' }}>
                                                <thead>
                                                    <tr>
                                                        <th>#</th>
                                                        <th>Fan</th>
                                                        <th>Side</th>
                                                        <th>Step</th>
                                                        <th>Target</th>
                                                        <th>Entry</th>
                                                        <th>Entry$</th>
                                                        <th>Exit</th>
                                                        <th>Exit$</th>
                                                        <th>PnL</th>
                                                        <th>Out</th>
                                                        <th>Origin Pivot</th>
                                                        <th>Anchor Pivot</th>
                                                        <th>Mom</th>
                                                        <th>Retest</th>
                                                        <th>Stop</th>
                                                        <th></th>
                                                    </tr>
                                                </thead>
                                                <tbody>
                                                    {filtered.map((t, i) => (
                                                        <tr
                                                            key={i}
                                                            className={selectedTrade === t ? 'selected-row' : ''}
                                                            onClick={() => {
                                                                setSelectedTrade(t);
                                                                if (chartRef.current?.navigateToTrade) {
                                                                    chartRef.current.navigateToTrade(t);
                                                                }
                                                            }}
                                                            style={{ cursor: 'pointer' }}
                                                        >
                                                            <td style={{ color: '#888', fontSize: '9px' }}>{i + 1}</td>
                                                            <td style={{ color: '#90CAF9', fontSize: '9px', maxWidth: '90px', overflow: 'hidden', textOverflow: 'ellipsis' }} title={t.fan}>{t.fan || '-'}</td>
                                                            <td style={{ color: t.side === 'LONG' ? '#00E676' : '#FF5252', fontWeight: 'bold' }}>{t.side || '-'}</td>
                                                            <td style={{ fontSize: '9px' }}>{t.progression_step || '-'}</td>
                                                            <td style={{ color: '#FFD54F', fontSize: '9px' }}>{t.current_target || '-'}</td>
                                                            <td style={{ fontSize: '9px' }}>{fmtTs(t.entry_time)}</td>
                                                            <td style={{ fontSize: '9px' }}>{t.entry_price != null ? t.entry_price.toFixed(2) : '-'}</td>
                                                            <td style={{ fontSize: '9px' }}>{fmtTs(t.exit_time)}</td>
                                                            <td style={{ fontSize: '9px' }}>{t.exit_price != null ? t.exit_price.toFixed(2) : '-'}</td>
                                                            <td style={{ color: (t.pnl || 0) >= 0 ? '#00E676' : '#FF5252', fontSize: '9px', fontWeight: 'bold' }}>
                                                                {t.pnl != null ? (t.pnl >= 0 ? '+' : '') + t.pnl.toFixed(2) : '-'}
                                                            </td>
                                                            <td style={{ color: t.outcome === 'WIN' ? '#00E676' : '#FF5252', fontSize: '9px' }}>{t.outcome || '-'}</td>
                                                            <td style={{ fontSize: '9px' }} title={fmtTs(t.fan_geometry?.origin?.time)}>{fmtPivot(t.fan_geometry, 'origin')}</td>
                                                            <td style={{ fontSize: '9px' }} title={fmtTs(t.fan_geometry?.anchor?.time)}>{fmtPivot(t.fan_geometry, 'anchor')}</td>
                                                            <td style={{ color: t.momentum_state === 'momentum' ? '#00E676' : t.momentum_state === 'exhaustion' ? '#FF9800' : '#888', fontSize: '9px' }}>
                                                                {t.momentum_state || '-'}
                                                            </td>
                                                            <td style={{ fontSize: '9px' }}>{t.retest_type || t.entry_path || '-'}</td>
                                                            <td style={{ color: '#FF5252', fontSize: '9px', fontWeight: 'bold' }}>{t.stop_triggered ? '⛔' : ''}</td>
                                                            <td style={{ textAlign: 'center' }}>
                                                                <button
                                                                    onClick={(e) => { e.stopPropagation(); copyTrade(t, i); }}
                                                                    title="Copy trade details"
                                                                    style={{
                                                                        background: 'none',
                                                                        border: '1px solid #555',
                                                                        borderRadius: '3px',
                                                                        color: '#aaa',
                                                                        cursor: 'pointer',
                                                                        fontSize: '9px',
                                                                        padding: '1px 5px',
                                                                    }}
                                                                >📋</button>
                                                            </td>
                                                        </tr>
                                                    ))}
                                                </tbody>
                                            </table>
                                        </div>
                                            );
                                        })()
                                    )}
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* Draggable Replay Bar Overlay */}
            {isReplayMode && (
                <div
                    className="replay-bar-overlay"
                    onMouseDown={handleReplayMouseDown}
                    style={{
                        left: `${replayPos.x}px`,
                        top: `${replayPos.y}px`,
                        // Override fixed positioning from CSS class if needed, or rely on style priority
                        bottom: 'auto',
                        transform: 'none'
                    }}
                >
                    <div className="replay-info">
                        <span className="replay-label">Step-by-Step Mode</span>
                        <span className="replay-value">{replayCurrentDate || 'Ready'}</span>
                    </div>

                    <div className="replay-controls-group">
                        <button className="step-btn" onClick={() => handleReplayAction('step')} title="Step Backward">
                            ⏮
                        </button>
                        <button onClick={() => handleReplayAction('play')} title="Play/Pause">
                            {isChartPlaying ? '⏸' : '▶'} Play
                        </button>
                        <button className="step-btn" onClick={() => handleReplayAction('step')} title="Step Forward">
                            ⏭
                        </button>
                    </div>

                    <div className="replay-progress">
                        <div className="progress-bar">
                            <div className="progress-fill" style={{ width: `${replayProgress}%` }}></div>
                        </div>
                        <div className="progress-text">{Math.round(replayProgress)}% Complete</div>
                    </div>

                    <select onChange={(e) => chartRef.current?.setSpeed(parseInt(e.target.value, 10))} defaultValue="1000">
                        <option value="2000">0.5x</option>
                        <option value="1000">1x</option>
                        <option value="500">2x</option>
                        <option value="200">5x</option>
                        <option value="100">10x</option>
                    </select>

                    <button className="exit-btn" onClick={handleExitReplay}>
                        ✕ Exit
                    </button>
                </div>
            )}
        </div>
    )
}

export default App
