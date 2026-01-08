import { useState, useRef, useEffect } from 'react'
import './App.css'
import { TVChartContainer } from './TVChartContainer'

function App() {
    const [strategy, setStrategy] = useState('mechanical_3day')
    const [isReplayMode, setIsReplayMode] = useState(false)
    const [tradeLog, setTradeLog] = useState([])
    const [backtestSummary, setBacktestSummary] = useState(null)
    const [replayProgress, setReplayProgress] = useState(0)
    const [replayCurrentDate, setReplayCurrentDate] = useState('')
    const [resultsHeight, setResultsHeight] = useState(200) // Resizable results panel height
    const [isResizing, setIsResizing] = useState(false)

    // Store backtest results for replay
    const backtestResultRef = useRef(null)
    const replayStartDateRef = useRef(null)

    const datafeedUrl = "http://localhost:8001"

    const chartRef = useRef(null);
    const startDateRef = useRef(null);
    const endDateRef = useRef(null);

    // Calculate P&L summary
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

    // Handle trade logged callback
    const handleTradeLogged = (trade) => {
        setTradeLog(prev => [...prev, trade]);
    };

    // Run Backtest (Instant Mode)
    const handleRunBacktest = async () => {
        if (!startDateRef.current || !endDateRef.current) return;

        const fromDate = startDateRef.current.value;
        const toDate = endDateRef.current.value;

        console.log(`Running Backtest: ${strategy} from ${fromDate} to ${toDate}`);
        setTradeLog([]);
        setBacktestSummary(null);

        try {
            // Get resolution from chart
            let currentResolution = '1';
            if (chartRef.current) {
                currentResolution = chartRef.current.getResolution();
                console.log("Using Chart Resolution for Backtest:", currentResolution);
            }

            const response = await fetch(`${datafeedUrl}/run_backtest`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    strategy: strategy,
                    symbol: "NIFTY OPTIONS",
                    from_date: fromDate,
                    to_date: toDate,
                    days: 0,
                    resolution: currentResolution // Send resolution to backend
                })
            });

            if (!response.ok) {
                alert("Backtest Failed: " + response.statusText);
                return;
            }

            const result = await response.json();
            console.log("Backtest Result:", result);

            // Store for potential replay
            backtestResultRef.current = result;

            // Calculate summary
            const summary = calculateSummary(result.trades);
            setBacktestSummary(summary);

            // Trigger Instant Chart Update
            if (chartRef.current) {
                // Pass the requested resolution to ensure chart alignment
                chartRef.current.startBacktestInstant(result.candles, result.trades, currentResolution);
            }

            // Hide replay controls in instant mode
            setIsReplayMode(false);

        } catch (error) {
            console.error("Backtest Error:", error);
            alert("Error running backtest: " + error.message);
        }
    };

    // Start Replay Mode
    // Start Replay Mode - Independent of Backtest  
    const handleStartReplay = async () => {
        const fromDate = startDateRef.current?.value;
        const toDate = endDateRef.current?.value;

        if (!fromDate || !toDate) {
            alert("Please select a date range first (From/To dates).");
            return;
        }

        const replayStartDate = replayStartDateRef.current?.value;
        let replayStartTimestamp = null;

        if (replayStartDate) {
            replayStartTimestamp = new Date(replayStartDate + ' 00:00:00').getTime() / 1000;
            console.log('[Replay] Will start from:', replayStartDate, 'timestamp:', replayStartTimestamp);
        }

        setTradeLog([]);
        setBacktestSummary(null);
        setIsReplayMode(true);
        setReplayProgress(0);
        setReplayCurrentDate('');

        try {
            let currentResolution = '1';
            if (chartRef.current) {
                currentResolution = chartRef.current.getResolution();
            }

            console.log(`[Replay] Fetching candles: ${fromDate} to ${toDate}, resolution: ${currentResolution}, strategy: ${strategy}`);

            const response = await fetch(`${datafeedUrl}/fetch_candles`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    symbol: "NIFTY 50",
                    from_date: fromDate,
                    to_date: toDate,
                    resolution: currentResolution
                })
            });

            if (!response.ok) {
                alert("Failed to fetch candles: " + response.statusText);
                setIsReplayMode(false);
                return;
            }

            const data = await response.json();
            console.log(`[Replay] Fetched ${data.candles.length} candles`);

            if (chartRef.current) {
                chartRef.current.startProgressiveReplay(
                    data.candles,
                    strategy,
                    currentResolution,
                    replayStartTimestamp,
                    datafeedUrl,
                    (progress, currentTime) => {
                        setReplayProgress(progress);
                        if (currentTime) {
                            setReplayCurrentDate(new Date(currentTime * 1000).toLocaleString());
                        }
                    },
                    (trade) => {
                        handleTradeLogged(trade);
                    }
                );
            }
        } catch (error) {
            console.error("[Replay] Error:", error);
            alert("Error starting replay: " + error.message);
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
        e.preventDefault();
    };

    const handleResizeMove = (e) => {
        if (!isResizing) return;

        const windowHeight = window.innerHeight;
        const headerHeight = document.querySelector('.app-header')?.offsetHeight || 0;
        const mouseY = e.clientY;

        // Calculate new results height (from bottom of window)
        const newHeight = windowHeight - mouseY;

        // Constrain between min and max
        const constrainedHeight = Math.max(100, Math.min(windowHeight * 0.5, newHeight));
        setResultsHeight(constrainedHeight);
    };

    const handleResizeEnd = () => {
        setIsResizing(false);
    };

    // Add/remove mouse event listeners for resize
    useEffect(() => {
        if (isResizing) {
            document.addEventListener('mousemove', handleResizeMove);
            document.addEventListener('mouseup', handleResizeEnd);
            return () => {
                document.removeEventListener('mousemove', handleResizeMove);
                document.removeEventListener('mouseup', handleResizeEnd);
            };
        }
    }, [isResizing]);

    return (
        <div className="app-container">
            <header className="app-header">
                <h1>Gann Visual Backtester</h1>
                <p>Validate Short-Term Options Strategies on Dhan Data</p>

                <div className="controls">
                    <select value={strategy} onChange={(e) => setStrategy(e.target.value)}>
                        <option value="mechanical_3day">Mechanical 3-Day Swing</option>
                        <option value="ichimoku_cloud">Ichimoku Cloud Breakout</option>
                        <option value="gann_square_9">Gann Square of 9</option>
                    </select>

                    <div className="date-range-picker">
                        <label>From: <input type="date" defaultValue="2025-12-20" ref={startDateRef} /></label>
                        <label>To: <input type="date" defaultValue="2025-12-26" ref={endDateRef} /></label>
                    </div>

                    <button className="run-backtest-btn" onClick={handleRunBacktest}>
                        Run Backtest
                    </button>

                    <div className="date-range-picker">
                        <label>Replay From: <input type="date" ref={replayStartDateRef} placeholder="Optional" /></label>
                    </div>

                    <button className="replay-btn" onClick={handleStartReplay}>
                        ▶ Start Replay
                    </button>
                </div>
            </header>

            <div className="main-content">
                <div className="chart-wrapper">
                    <TVChartContainer
                        ref={chartRef}
                        symbol="NIFTY 50"
                        datafeedUrl={datafeedUrl}
                        onTradeLogged={handleTradeLogged}
                    />
                </div>

                <div className="resize-handle" onMouseDown={handleResizeStart}></div>

                <div className="backtest-results" style={{ height: `${resultsHeight}px` }}>
                    <h3>Backtest Results</h3>
                    <div className="results-content">
                        {backtestSummary ? (
                            <div className="summary">
                                <p><strong>Strategy:</strong> {strategy}</p>
                                <p><strong>Total Signals:</strong> {backtestSummary.totalTrades}</p>
                                <p><strong>Completed Trades:</strong> {backtestSummary.completedTrades}</p>
                                <p><strong>Wins:</strong> {backtestSummary.wins} | <strong>Losses:</strong> {backtestSummary.losses}</p>
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
                                            {t.type.toUpperCase()} @ {t.price != null ? t.price.toFixed(2) : 'N/A'}
                                            {t.pnl != null && ` | P&L: ${t.pnl.toFixed(2)}`}
                                            <span style={{ color: '#888', marginLeft: '10px' }}>
                                                ({new Date(t.time * 1000).toLocaleString()})
                                            </span>
                                        </li>
                                    ))}
                                </ul>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* TradingView-style Replay Bar Overlay */}
            {isReplayMode && (
                <div className="replay-bar-overlay">
                    <div className="replay-info">
                        <span className="replay-label">Replay Mode</span>
                        <span className="replay-value">{replayCurrentDate || 'Ready'}</span>
                    </div>

                    <div className="replay-controls-group">
                        <button className="step-btn" onClick={() => handleReplayAction('step')} title="Step Backward">
                            ⏮
                        </button>
                        <button onClick={() => handleReplayAction('play')} title="Play/Pause">
                            {chartRef.current?.isPlaying?.() ? '⏸' : '▶'} Play
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

                    <select onChange={(e) => chartRef.current?.setSpeed(parseInt(e.target.value))} defaultValue="1000">
                        <option value="2000">0.5x</option>
                        <option value="1000">1x</option>
                        <option value="500">2x</option>
                        <option value="200">5x</option>
                        <option value="100">10x</option>
                    </select>

                    <button className="exit-btn" onClick={handleExitReplay}>
                        ✕ Exit Replay
                    </button>
                </div>
            )}
        </div>
    )
}

export default App
