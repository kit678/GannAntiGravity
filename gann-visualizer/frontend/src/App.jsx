import { useState, useRef, useEffect, useCallback } from 'react'
import './App.css'
import { TVChartContainer } from './TVChartContainer'

// Constants and utility functions
const TODAY = new Date();
const formatDate = (date) => date.toISOString().split('T')[0];
const DEFAULT_END_DATE = formatDate(TODAY);
const DEFAULT_START_DATE = '2025-11-07'; // User requested default
const LOOKBACK_BARS = 5000;
const DATAFEED_URL = "http://localhost:8005";

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
        totalPnL: totalPnL.toFixed(2),
        winRate: (wins + losses > 0) ? ((wins / (wins + losses)) * 100).toFixed(1) : 0
    };
};

function App() {
    const [strategy, setStrategy] = useState('mechanical_3day')
    const [filterFan, setFilterFan] = useState('all') // Filter by fan in Price Interactions tab

    const [instrumentType, setInstrumentType] = useState('spot') // User requested default
    const [dataSource, setDataSource] = useState('yfinance') // User requested default
    
    // Session Configuration
    const [cycleType, setCycleType] = useState('24_hour')
    const [sessionDuration, setSessionDuration] = useState('standard')

    // Pivot settings for Angular Coverage study
    const [pivotLeftBars, setPivotLeftBars] = useState(5)
    const [pivotRightBars, setPivotRightBars] = useState(5)
    const [showIntersectionLabels, setShowIntersectionLabels] = useState(false)

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

    const [isReplayMode, setIsReplayMode] = useState(false)
    const [tradeLog, setTradeLog] = useState([])
    const [backtestSummary, setBacktestSummary] = useState(null)
    const [replayProgress, setReplayProgress] = useState(0)
    const [replayCurrentDate, setReplayCurrentDate] = useState('')
    const [resultsHeight, setResultsHeight] = useState(35) // Default to closed (just header)
    const [isResizing, setIsResizing] = useState(false)
    const [bottomPanelTab, setBottomPanelTab] = useState('backtest') // 'backtest' | 'interactions'
    const [priceInteractions, setPriceInteractions] = useState([]) // Live interaction log
    const [isChartPlaying, setIsChartPlaying] = useState(false)

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
        // Reset chart to default symbol for that source to ensure validity
        if (newSource === 'yfinance') {
            setChartMountSymbol('^NSEI');
            activeSymbolRef.current = '^NSEI';
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
                chartRef.current.startBacktestInstant(result.candles, result.trades, currentResolution, result.markers, result.drawings);
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

    return (
        <div className="app-container">
            <header className="app-header">
                <div className="controls">
                    <select value={strategy} onChange={(e) => setStrategy(e.target.value)}>
                        <option value="mechanical_3day">Mechanical 3-Day Swing</option>
                        <option value="five_ema">5 EMA Breakout Strategy</option>
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
                        interval="1"
                        visibleFanLabels={visibleFanLabels}
                        onAvailableFansUpdated={setAvailableFanLabels}
                        onPlayingStateChange={setIsChartPlaying}
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
                                    <>
                                        <div style={{ marginBottom: '10px', display: 'flex', gap: '10px', alignItems: 'center' }}>
                                            <label style={{ fontSize: '12px' }}>
                                                Filter by Fan:
                                                <select
                                                    value={filterFan}
                                                    onChange={(e) => setFilterFan(e.target.value)}
                                                    style={{ marginLeft: '5px', padding: '2px 5px', fontSize: '11px' }}
                                                >
                                                    <option value="all">All Fans</option>
                                                    {[...new Set(priceInteractions.map(h => h.fanIdentity || h.fan))].sort().map(identity => (
                                                        <option key={identity} value={identity}>{identity}</option>
                                                    ))}
                                                </select>
                                            </label>
                                            <span style={{ fontSize: '11px', color: '#888' }}>
                                                Showing {priceInteractions.filter(h => filterFan === 'all' || (h.fanIdentity || h.fan) === filterFan).length} of {priceInteractions.length} events
                                            </span>
                                        </div>
                                        <table className="interactions-table">
                                            <thead>
                                                <tr>
                                                    <th>#</th>
                                                    <th>Time</th>
                                                    <th>Fan</th>
                                                    <th>Fraction</th>
                                                    <th>Price</th>
                                                    <th>Type</th>
                                                    <th>Details</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {priceInteractions
                                                    .filter(hit => filterFan === 'all' || (hit.fanIdentity || hit.fan) === filterFan)
                                                    .map((hit, i) => (
                                                        <tr key={i}>
                                                            <td>{i + 1}</td>
                                                            <td>{new Date(hit.time * 1000).toLocaleString()}</td>
                                                            <td style={{ color: '#90CAF9' }}>{hit.fan}</td>
                                                            <td style={{ color: '#FFEB3B' }}>{hit.fraction}</td>
                                                            <td>{hit.price != null ? hit.price.toFixed(2) : 'N/A'}</td>
                                                            <td>{hit.type || 'N/A'}</td>
                                                            <td style={{ fontSize: '11px', color: '#AAA' }}>{hit.details || ''}</td>
                                                        </tr>
                                                    ))}
                                            </tbody>
                                        </table>
                                    </>
                                )}
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
