// krakenDatafeed.js

const KRAKEN_API_BASE_URL = 'https://api.kraken.com/0/public';
const KRAKEN_WS_URL_V1 = 'wss://ws.kraken.com';
// const KRAKEN_WS_URL_V2 = 'wss://ws.kraken.com/v2'; // V2 is preferred for new integrations

// Helper to make API requests
async function makeKrakenApiRequest(path, params) {
    const url = new URL(`${KRAKEN_API_BASE_URL}/${path}`);
    if (params) {
        Object.keys(params).forEach(key => url.searchParams.append(key, params[key]));
    }
    try {
        const response = await fetch(url);
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(`Kraken API error: ${response.status} - ${errorData.error && errorData.error.join(', ')}`);
        }
        const data = await response.json();
        if (data.error && data.error.length > 0) {
            throw new Error(`Kraken API error: ${data.error.join(', ')}`);
        }
        return data.result;
    } catch (error) {
        console.error(`[Kraken API Request Error] ${path}:`, error);
        throw error;
    }
}

// WebSocket management
let krakenSocket = null;
const wsSubscriptions = new Map(); // Key: subscriberUID, Value: { pair: string, onRealtimeCallback: function, resolution: string }
let lastBarsCache = new Map(); // For storing the last bar to update with real-time trades

function connectWebSocket() {
    if (krakenSocket && (krakenSocket.readyState === WebSocket.OPEN || krakenSocket.readyState === WebSocket.CONNECTING)) {
        return;
    }

    krakenSocket = new WebSocket(KRAKEN_WS_URL_V1);

    krakenSocket.onopen = () => {
        console.log('[Kraken WebSocket] Connected');
        // Resubscribe to any existing subscriptions if needed (e.g., after a disconnect)
        wsSubscriptions.forEach((sub, subUID) => {
            if (sub.pair && sub.channel === 'trade') { // Assuming we only have 'trade' subs for now
                 krakenSocket.send(JSON.stringify({
                    event: 'subscribe',
                    pair: [sub.pair],
                    subscription: { name: 'trade' }
                }));
            }
        });
    };

    krakenSocket.onmessage = (event) => {
        const message = JSON.parse(event.data);
        // console.log('[Kraken WebSocket] Message:', message);

        if (Array.isArray(message) && message.length === 4 && message[2] === 'trade') {
            const trades = message[1];
            const pair = message[3]; // e.g., "XBT/USD"

            wsSubscriptions.forEach((sub, subUID) => {
                if (sub.pair === pair && sub.channel === 'trade') {
                    const lastBar = lastBarsCache.get(`${pair}-${sub.resolution}`); // Use a composite key
                    if (!lastBar) return;

                    let updatedBar = {...lastBar};

                    trades.forEach(tradeData => {
                        const price = parseFloat(tradeData[0]);
                        const volume = parseFloat(tradeData[1]);
                        const time = parseFloat(tradeData[2]) * 1000; // Kraken time is in seconds

                        // This is a simplified bar aggregation logic.
                        // For production, you'd need more robust aggregation based on resolution.
                        // This assumes the trade falls into the current bar or starts a new one.
                        if (time >= updatedBar.time) { // If trade is newer or same time
                            if (time > updatedBar.time && time >= updatedBar.time + getResolutionMs(sub.resolution)) {
                                // Start a new bar if trade time is for the next interval
                                updatedBar = {
                                    time: Math.floor(time / getResolutionMs(sub.resolution)) * getResolutionMs(sub.resolution),
                                    open: price,
                                    high: price,
                                    low: price,
                                    close: price,
                                    volume: volume,
                                };
                            } else {
                                // Update existing bar
                                updatedBar.high = Math.max(updatedBar.high, price);
                                updatedBar.low = Math.min(updatedBar.low, price);
                                updatedBar.close = price;
                                updatedBar.volume = (updatedBar.volume || 0) + volume; // Aggregate volume
                            }
                        }
                    });
                    
                    if (updatedBar.time !== lastBar.time || updatedBar.close !== lastBar.close) {
                        sub.onRealtimeCallback(updatedBar);
                        lastBarsCache.set(`${pair}-${sub.resolution}`, updatedBar);
                    }
                }
            });
        } else if (message.event === 'pong') {
            // console.log('[Kraken WebSocket] Pong received');
        } else if (message.event === 'heartbeat') {
            // console.log('[Kraken WebSocket] Heartbeat received');
        } else if (message.event === 'systemStatus' || message.event === 'subscriptionStatus') {
            console.log('[Kraken WebSocket] Status:', message);
        } else if (message.errorMessage) {
            console.error('[Kraken WebSocket] Error:', message.errorMessage);
        }
    };

    krakenSocket.onerror = (error) => {
        console.error('[Kraken WebSocket] Error:', error);
    };

    krakenSocket.onclose = () => {
        console.log('[Kraken WebSocket] Disconnected');
        krakenSocket = null;
        // Implement reconnection logic if desired, respecting rate limits
    };
    
    // Keep connection alive
    setInterval(() => {
        if (krakenSocket && krakenSocket.readyState === WebSocket.OPEN) {
            krakenSocket.send(JSON.stringify({ event: 'ping' }));
        }
    }, 20000); // Ping every 20 seconds
}

function getResolutionMs(resolutionString) {
    const unit = resolutionString.slice(-1);
    const value = parseInt(resolutionString.slice(0, -1), 10);
    if (isNaN(value) && resolutionString === 'D') return 24 * 60 * 60 * 1000; // Daily
    if (isNaN(value) && resolutionString === '1D') return 24 * 60 * 60 * 1000; // Daily


    switch (unit) {
        case 'S': return value * 1000;
        case 'M': return value * 60 * 1000; // TradingView 'M' can mean minutes or Months. We assume minutes here.
        case 'H': return value * 60 * 60 * 1000;
        case 'D': return value * 24 * 60 * 60 * 1000;
        case 'W': return value * 7 * 24 * 60 * 60 * 1000;
        // Note: TradingView 'M' for months is complex as months have variable days.
        // Kraken OHLC uses minutes: 1, 5, 15, 30, 60, 240, 1440, 10080, 21600
        default: return parseInt(resolutionString) * 60 * 1000; // Default to minutes if no unit
    }
}


// Map TradingView resolutions to Kraken intervals (in minutes)
function mapTvResolutionToKraken(resolution) {
    // Standard resolutions: 1, 5, 15, 30, 60 (1H), 240 (4H), 1440 (1D), 10080 (1W), 21600 (15D is not standard, closest is 3W from Kraken)
    // TradingView examples: '1', '5', '15', '30', '60', 'D', 'W', 'M'
    if (resolution === 'D' || resolution === '1D') return 1440;
    if (resolution === 'W' || resolution === '1W') return 10080;
    if (resolution === 'M' || resolution === '1M') return 21600; // Kraken specific, closest to a month. TV expects first trading day of month.
    
    const numericResolution = parseInt(resolution);
    if (!isNaN(numericResolution)) {
        // Check against Kraken's supported minute intervals
        const supportedKrakenIntervals = [1, 5, 15, 30, 60, 240, 1440, 10080, 21600];
        if (supportedKrakenIntervals.includes(numericResolution)) {
            return numericResolution;
        }
        // Potentially find closest or throw error. For now, strict match.
        console.warn(`Kraken does not directly support ${resolution} minute interval. Falling back to 60.`);
        return 60; 
    }
    console.warn(`Unsupported resolution for Kraken: ${resolution}. Falling back to 1D.`);
    return 1440; // Default to 1 day
}

// Map Kraken asset pair names to TradingView symbol format (e.g., XBT/USD -> BTC/USD)
function formatKrakenPairForTv(krakenPair) {
    return krakenPair.replace('XBT', 'BTC').replace('XDG', 'DOGE'); // Common replacements
}
function formatTvPairForKraken(tvPair) {
    return tvPair.replace('BTC', 'XBT').replace('DOGE', 'XDG');
}


const krakenDatafeedInternal = {
    onReady: (callback) => {
        console.log('[Kraken onReady] Called');
        setTimeout(() => callback({
            supported_resolutions: ['1', '5', '15', '30', '60', '240', '1D', '1W'],
            supports_search: true,
            supports_group_request: false,
            supports_marks: false,
            supports_timescale_marks: false,
            supports_time: true,
            exchanges: [{ value: 'Kraken', name: 'Kraken', desc: 'Kraken Exchange' }],
            symbols_types: [{ name: 'Crypto', value: 'crypto' }],
        }), 0);
    },

    searchSymbols: async (userInput, exchange, symbolType, onResultReadyCallback) => {
        console.log('[Kraken searchSymbols] User input:', userInput);
        if (symbolType && symbolType.toLowerCase() !== 'crypto') {
            onResultReadyCallback([]);
            return;
        }
        try {
            const assetPairs = await makeKrakenApiRequest('AssetPairs');
            const symbols = Object.keys(assetPairs)
                .map(key => {
                    const pairInfo = assetPairs[key];
                    const tvPair = formatKrakenPairForTv(pairInfo.wsname || key); // wsname is like "XBT/USD"
                    return {
                        symbol: tvPair,
                        full_name: `Kraken:${tvPair}`, // For TradingView, ticker is often exchange:symbol
                        description: pairInfo.altname || tvPair, // altname is like XXBTZUSD
                        exchange: 'Kraken',
                        type: 'crypto',
                        ticker: `Kraken:${tvPair}` // Ticker used by chart
                    };
                })
                .filter(s => s.symbol.toLowerCase().includes(userInput.toLowerCase()) || s.full_name.toLowerCase().includes(userInput.toLowerCase()));
            
            onResultReadyCallback(symbols);
        } catch (error) {
            console.error('[Kraken searchSymbols] Error:', error);
            onResultReadyCallback([]);
        }
    },

    resolveSymbol: async (symbolName, onSymbolResolvedCallback, onResolveErrorCallback, extension) => {
        console.log('[Kraken resolveSymbol] Symbol name:', symbolName); // symbolName is usually the 'ticker' like 'Kraken:BTC/USD'
        
        const parts = symbolName.split(':');
        const tvPair = parts.length > 1 ? parts[1] : parts[0];
        const krakenPairName = formatTvPairForKraken(tvPair); // e.g. BTC/USD -> XBT/USD for wsname lookup

        try {
            const assetPairs = await makeKrakenApiRequest('AssetPairs');
            let foundPairInfo = null;
            let foundPairKey = null;

            for (const key in assetPairs) {
                if (assetPairs[key].wsname === krakenPairName || key === krakenPairName || formatKrakenPairForTv(assetPairs[key].wsname) === tvPair || formatKrakenPairForTv(key) === tvPair ) {
                    foundPairInfo = assetPairs[key];
                    foundPairKey = key; // The actual key used in OHLC endpoint might be like "XXBTZUSD"
                    break;
                }
            }

            if (!foundPairInfo) {
                onResolveErrorCallback('unknown_symbol');
                return;
            }
            
            const pricescale = Math.pow(10, foundPairInfo.pair_decimals);

            const symbolInfo = {
                name: tvPair, // e.g. BTC/USD
                ticker: symbolName, // Kraken:BTC/USD
                description: foundPairInfo.altname || tvPair,
                type: 'crypto',
                session: '24x7',
                timezone: 'Etc/UTC',
                exchange: 'Kraken',
                listed_exchange: 'Kraken',
                minmov: 1, // Minimum price change
                pricescale: pricescale, // Number of decimal places
                has_intraday: true, // Supports intraday resolutions
                has_daily: true,
                has_weekly_and_monthly: true,
                supported_resolutions: ['1', '5', '15', '30', '60', '240', '1D', '1W'],
                volume_precision: foundPairInfo.lot_decimals || 2,
                data_status: 'streaming', // or 'pulsed' or 'delayed_streaming'
                currency_code: foundPairInfo.quote ? foundPairInfo.quote.substring(1) : tvPair.split('/')[1], // ZUSD -> USD
                original_currency_code: foundPairInfo.quote,
                visible_plots_set: 'ohlcv',
                full_name: symbolName,
                pro_name: symbolName,
                base_name: [tvPair]
            };
            console.log('[Kraken resolveSymbol] Resolved:', symbolInfo)
            onSymbolResolvedCallback(symbolInfo);

        } catch (error) {
            console.error('[Kraken resolveSymbol] Error:', error);
            onResolveErrorCallback('resolve_error');
        }
    },

    getBars: async (symbolInfo, resolution, periodParams, onHistoryCallback, onErrorCallback) => {
        const { from, to, countBack, firstDataRequest } = periodParams;
        console.log(`[Kraken getBars] Symbol: ${symbolInfo.ticker}, Resolution: ${resolution}, From: ${new Date(from * 1000)}, To: ${new Date(to * 1000)}, CountBack: ${countBack}`);

        const krakenInterval = mapTvResolutionToKraken(resolution);
        const tvPair = symbolInfo.name; // "BTC/USD"
        let krakenPairNameForOhlc = formatTvPairForKraken(tvPair); // Default to wsname format

        // Need to find the 'altname' or the key used for OHLC (e.g. XXBTZUSD)
        // This might require another call or caching from resolveSymbol if not passed in symbolInfo
        try {
            const assetPairs = await makeKrakenApiRequest('AssetPairs');
             for (const key in assetPairs) {
                if (assetPairs[key].wsname === formatTvPairForKraken(tvPair) || formatKrakenPairForTv(assetPairs[key].wsname) === tvPair) {
                    krakenPairNameForOhlc = key; // Use the main key like XXBTZUSD for OHLC
                    break;
                }
            }
        } catch(e) {
            onErrorCallback(e);
            return;
        }


        const params = {
            pair: krakenPairNameForOhlc,
            interval: krakenInterval,
        };
        // Kraken's 'since' is for older data, but it only returns last 720 records.
        // We'll rely on 'to' and 'countBack' behavior of TradingView library mostly.
        // If 'since' is used, it acts as a starting point for the 720 records.
        // For simplicity, we let TV handle the 'from' based on 'countBack' from 'to'.
        // If firstDataRequest, TV usually requests a large countBack.

        try {
            const data = await makeKrakenApiRequest('OHLC', params);
            const ohlcData = data[krakenPairNameForOhlc];
            if (!ohlcData) {
                setTimeout(() => onHistoryCallback([], { noData: true }), 0);
                return;
            }
            const bars = ohlcData
                .map(b => {
                    const t = parseFloat(b[0]) * 1000;
                    // shift daily bars to prior midnight UTC
                    const alignedTime = (resolution === 'D' || resolution === '1D') 
                        ? new Date(t).setUTCHours(0,0,0,0) 
                        : t;
                    return {
                        time: alignedTime,
                        open: parseFloat(b[1]),
                        high: parseFloat(b[2]),
                        low: parseFloat(b[3]),
                        close: parseFloat(b[4]),
                        volume: parseFloat(b[6])
                    };
                })
                .filter(b => b.time >= from * 1000 && b.time < to * 1000)
                .sort((a, b) => a.time - b.time);
            setTimeout(() => {
                if (bars.length === 0 && firstDataRequest) {
                    onHistoryCallback([], { noData: true });
                } else if (bars.length === 0) {
                    onHistoryCallback([], { noData: true });
                } else {
                    if (firstDataRequest) {
                        lastBarsCache.set(`${tvPair}-${resolution}`, bars[bars.length - 1]);
                    }
                    onHistoryCallback(bars, { noData: false });
                }
            }, 0);
        } catch (error) {
            console.error('[Kraken getBars] Error:', error);
            onErrorCallback(error);
            setTimeout(() => onHistoryCallback([], { noData: true }), 0);
        }
    },

    subscribeBars: (symbolInfo, resolution, onRealtimeCallback, subscriberUID, onResetCacheNeededCallback) => {
        console.log(`[Kraken subscribeBars] (TEMP DISABLED REALTIME) UID: ${subscriberUID}, Symbol: ${symbolInfo.ticker}, Resolution: ${resolution}`);
        if (typeof onResetCacheNeededCallback === 'function') {
            setTimeout(() => onResetCacheNeededCallback(), 0);
        }
        wsSubscriptions.set(subscriberUID, { 
            pair: formatTvPairForKraken(symbolInfo.name), 
            onRealtimeCallback, 
            subscriberUID, 
            resolution,
            channel: 'trade'
        });
        // Intentionally do not open WebSocket or push realtime updates during diagnostics
    },

    unsubscribeBars: (subscriberUID) => {
        console.log(`[Kraken unsubscribeBars] (TEMP DISABLED REALTIME) UID: ${subscriberUID}`);
        wsSubscriptions.delete(subscriberUID);
    },

    getServerTime: async (callback) => {
        callback(Math.floor(Date.now() / 1000));
    },
};

// Make it globally available for the datafeedManager.js
window.krakenDatafeed = krakenDatafeedInternal; 
