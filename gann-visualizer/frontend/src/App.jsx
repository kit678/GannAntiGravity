import { useState, useRef } from 'react'
import './App.css'
import { TVChartContainer } from './TVChartContainer'

function App() {
    const [strategy, setStrategy] = useState('mechanical_3day')
    const [isReplayMode, setIsReplayMode] = useState(false)
    const [tradeLog, setTradeLog] = useState([])
    const [backtestSummary, setBacktestSummary] = useState(null)

    // Store backtest results for replay
    const backtestResultRef = useRef(null)

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
            if (t.type === 'sell' && t.pnl !== undefined) {
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
    const handleStartReplay = () => {
        if (!backtestResultRef.current) {
            alert("Please run a backtest first.");
            return;
        }

        setTradeLog([]);
        setIsReplayMode(true);

        if (chartRef.current && backtestResultRef.current) {
            // Get original resolution used for backtest (stored in result or assume current)
            const res = chartRef.current.getResolution();

            chartRef.current.startBacktestReplay(
                backtestResultRef.current.candles,
                backtestResultRef.current.trades,
                res
            );
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

                    <button className="replay-btn" onClick={handleStartReplay} disabled={!backtestResultRef.current}>
                        Start Replay
                    </button>

                    {isReplayMode && (
                        <div className="replay-controls">
                            <button onClick={() => handleReplayAction('step')}>⏮ Step</button>
                            <button onClick={() => handleReplayAction('play')}>▶/⏸</button>
                            <button onClick={() => handleReplayAction('step')}>Step ⏭</button>
                            <select onChange={(e) => chartRef.current?.setSpeed(parseInt(e.target.value))} defaultValue="1000">
                                <option value="2000">0.5x</option>
                                <option value="1000">1x</option>
                                <option value="500">2x</option>
                                <option value="200">5x</option>
                            </select>
                            <button onClick={handleExitReplay} style={{ marginLeft: '10px', color: '#FF5252' }}>Exit Replay</button>
                        </div>
                    )}
                </div>
            </header>

            <div className="chart-wrapper">
                <TVChartContainer
                    ref={chartRef}
                    symbol="NIFTY 50"
                    datafeedUrl={datafeedUrl}
                    onTradeLogged={handleTradeLogged}
                />
            </div>

            <div className="backtest-results">
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
                                        {t.type.toUpperCase()} @ {t.price.toFixed(2)}
                                        {t.pnl !== undefined && ` | P&L: ${t.pnl.toFixed(2)}`}
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
    )
}

export default App
