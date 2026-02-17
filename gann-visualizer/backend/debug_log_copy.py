2026-02-10 14:50:03,833 [INFO] Logging initialized. Output writing to C:\Dev\GannTesting\gann-visualizer\backend\backend_session_20260210_145003.log
2026-02-10 14:50:03,833 [INFO] --- BACKEND RESTART v4 - PNL TRACKING ---
2026-02-10 14:50:03,834 [INFO] Middleware Stack: [Middleware(BaseHTTPMiddleware, dispatch=<function cors_middleware at 0x00000270201D1C60>)]
2026-02-10 14:50:05,233 [INFO] DEBUG CORS: Origin header received: 'http://localhost:5173'
2026-02-10 14:50:05,240 [INFO] DEBUG CORS: Origin header received: 'http://localhost:5173'
2026-02-10 14:50:05,570 [INFO] DEBUG CORS: Origin header received: 'http://localhost:5173'
2026-02-10 14:50:05,805 [INFO] 
2026-02-10 14:50:05,807 [INFO] ============================================================
2026-02-10 14:50:05,808 [INFO] [UDF_HISTORY] === NEW REQUEST ===
2026-02-10 14:50:05,809 [INFO] [UDF_HISTORY] symbol=^NSEI, resolution=1
2026-02-10 14:50:05,810 [INFO] [UDF_HISTORY] from_=1770646145, to=1770715265, data_source=yfinance
2026-02-10 14:50:05,811 [INFO] ============================================================
2026-02-10 14:50:05,812 [INFO] [udf_history] Auto-detected Yahoo Finance symbol: ^NSEI
2026-02-10 14:50:05,814 [INFO] [YFinance] Client initialized
2026-02-10 14:50:05,821 [INFO] 
2026-02-10 14:50:05,822 [INFO] ============================================================
2026-02-10 14:50:05,823 [INFO] [UDF_HISTORY] INCOMING REQUEST
2026-02-10 14:50:05,824 [INFO]   Symbol: ^NSEI
2026-02-10 14:50:05,825 [INFO]   Data Source: yfinance
2026-02-10 14:50:05,826 [INFO]   Resolution: 1
2026-02-10 14:50:05,827 [INFO]   From (Unix): 1770646145 -> 2026-02-09 19:39:05
2026-02-10 14:50:05,828 [INFO]   To (Unix): 1770715265 -> 2026-02-10 14:51:05
2026-02-10 14:50:05,829 [INFO] ============================================================
2026-02-10 14:50:05,830 [INFO] [UDF_HISTORY] Calling client.fetch_data(^NSEI, 2026-02-09 19:39:05, 2026-02-10 14:51:05, interval=1)
2026-02-10 14:50:05,831 [INFO] Cache MISS: ^NSEI:1:2026-02-09 19:39:05:2026-02-10 14:51:05
2026-02-10 14:50:05,832 [INFO] [YFinance] Fetching ^NSEI | interval=1 -> 1m | 2026-02-09 19:39:05 to 2026-02-10 14:51:05
2026-02-10 14:50:05,836 [INFO] [YFinance] Requesting dates: start=2026-02-09, end=2026-02-11 for ^NSEI
2026-02-10 14:50:06,832 [INFO] [YFinance] Received 711 bars
2026-02-10 14:50:06,839 [INFO] [YFinance] Returning 711 bars, range: 2026-02-09 09:15:00 to 2026-02-10 14:50:00
2026-02-10 14:50:06,840 [INFO] Cache PUT: ^NSEI:1:2026-02-09 19:39:05:2026-02-10 14:51:05 (TTL: 300.0s, 711 rows)
2026-02-10 14:50:06,841 [INFO] [UDF_HISTORY] fetch_data returned: type=<class 'pandas.core.frame.DataFrame'>, empty=False
2026-02-10 14:50:06,841 [INFO] [UDF_HISTORY] Raw data shape: (711, 6), columns: ['timestamp', 'open', 'high', 'low', 'close', 'volume']
2026-02-10 14:50:06,842 [INFO] [UDF_HISTORY] Raw timestamp range: 1770608700 - 1770715200
2026-02-10 14:50:06,843 [INFO] [UDF_HISTORY] Raw date range: 2026-02-09 09:15:00 - 2026-02-10 14:50:00
2026-02-10 14:50:06,844 [INFO] DEBUG: fetch_data result type: <class 'pandas.core.frame.DataFrame'>
2026-02-10 14:50:06,845 [INFO] DEBUG: fetch_data result shape: (711, 6)
2026-02-10 14:50:06,858 [INFO] DEBUG: Data Head:
2026-02-10 14:50:06,859 [INFO]     timestamp          open          high           low         close  volume
2026-02-10 14:50:06,860 [INFO] 0  1770608700  25903.099609  25903.099609  25799.300781  25832.650391       0
2026-02-10 14:50:06,860 [INFO] 1  1770608760  25828.099609  25841.449219  25826.199219  25830.199219       0
2026-02-10 14:50:06,861 [INFO] DEBUG: from_=1770646145 (2026-02-09 19:39:05)
2026-02-10 14:50:06,862 [INFO] DEBUG: to=1770715265 (2026-02-10 14:51:05)
2026-02-10 14:50:06,862 [INFO] DEBUG: df['timestamp'] dtype=int64
2026-02-10 14:50:06,863 [INFO] DEBUG: df timestamp range: 1770608700 - 1770715200
2026-02-10 14:50:06,864 [INFO] DEBUG: df timestamp as dates: 2026-02-09T09:15:00 - 2026-02-10T14:50:00
2026-02-10 14:50:06,865 [INFO] Filtered data from 711 to 336 bars (filter_from=1770646145, to=1770715265)
2026-02-10 14:50:06,866 [INFO] PAGINATION: Returning 336 bars for ^NSEI (1)
2026-02-10 14:50:06,875 [INFO] DEBUG CORS: Origin header received: 'http://localhost:5173'
2026-02-10 14:50:08,514 [INFO] 
2026-02-10 14:50:08,515 [INFO] ============================================================
2026-02-10 14:50:08,516 [INFO] [UDF_HISTORY] === NEW REQUEST ===
2026-02-10 14:50:08,516 [INFO] [UDF_HISTORY] symbol=^NSEI, resolution=60
2026-02-10 14:50:08,517 [INFO] [UDF_HISTORY] from_=1764347934, to=1770715268, data_source=yfinance
2026-02-10 14:50:08,518 [INFO] ============================================================
2026-02-10 14:50:08,519 [INFO] [udf_history] Auto-detected Yahoo Finance symbol: ^NSEI
2026-02-10 14:50:08,520 [INFO] [YFinance] Client initialized
2026-02-10 14:50:08,521 [INFO] 
2026-02-10 14:50:08,521 [INFO] ============================================================
2026-02-10 14:50:08,522 [INFO] [UDF_HISTORY] INCOMING REQUEST
2026-02-10 14:50:08,523 [INFO]   Symbol: ^NSEI
2026-02-10 14:50:08,523 [INFO]   Data Source: yfinance
2026-02-10 14:50:08,524 [INFO]   Resolution: 60
2026-02-10 14:50:08,525 [INFO]   From (Unix): 1764347934 -> 2025-11-28 22:08:54
2026-02-10 14:50:08,525 [INFO]   To (Unix): 1770715268 -> 2026-02-10 14:51:08
2026-02-10 14:50:08,526 [INFO] ============================================================
2026-02-10 14:50:08,526 [INFO] [UDF_HISTORY] Calling client.fetch_data(^NSEI, 2025-11-28 22:08:54, 2026-02-10 14:51:08, interval=60)
2026-02-10 14:50:08,527 [INFO] Cache MISS: ^NSEI:60:2025-11-28 22:08:54:2026-02-10 14:51:08
2026-02-10 14:50:08,527 [INFO] [YFinance] Fetching ^NSEI | interval=60 -> 1h | 2025-11-28 22:08:54 to 2026-02-10 14:51:08
2026-02-10 14:50:08,529 [INFO] [YFinance] Requesting dates: start=2025-11-28, end=2026-02-11 for ^NSEI
2026-02-10 14:50:08,734 [INFO] [YFinance] Received 341 bars
2026-02-10 14:50:08,739 [INFO] [YFinance] Returning 341 bars, range: 2025-11-28 09:15:00 to 2026-02-10 14:15:00
2026-02-10 14:50:08,740 [INFO] Cache PUT: ^NSEI:60:2025-11-28 22:08:54:2026-02-10 14:51:08 (TTL: 300.0s, 341 rows)
2026-02-10 14:50:08,741 [INFO] [UDF_HISTORY] fetch_data returned: type=<class 'pandas.core.frame.DataFrame'>, empty=False
2026-02-10 14:50:08,741 [INFO] [UDF_HISTORY] Raw data shape: (341, 6), columns: ['timestamp', 'open', 'high', 'low', 'close', 'volume']
2026-02-10 14:50:08,742 [INFO] [UDF_HISTORY] Raw timestamp range: 1764301500 - 1770713100
2026-02-10 14:50:08,743 [INFO] [UDF_HISTORY] Raw date range: 2025-11-28 09:15:00 - 2026-02-10 14:15:00
2026-02-10 14:50:08,744 [INFO] DEBUG: fetch_data result type: <class 'pandas.core.frame.DataFrame'>
2026-02-10 14:50:08,744 [INFO] DEBUG: fetch_data result shape: (341, 6)
2026-02-10 14:50:08,757 [INFO] DEBUG: Data Head:
2026-02-10 14:50:08,757 [INFO]     timestamp          open          high           low         close  volume
2026-02-10 14:50:08,757 [INFO] 0  1764301500  26246.900391  26267.199219  26172.900391  26240.400391       0
2026-02-10 14:50:08,758 [INFO] 1  1764305100  26240.650391  26280.199219  26218.800781  26266.500000       0
2026-02-10 14:50:08,759 [INFO] DEBUG: from_=1764347934 (2025-11-28 22:08:54)
2026-02-10 14:50:08,760 [INFO] DEBUG: to=1770715268 (2026-02-10 14:51:08)
2026-02-10 14:50:08,761 [INFO] DEBUG: df['timestamp'] dtype=int64
2026-02-10 14:50:08,762 [INFO] DEBUG: df timestamp range: 1764301500 - 1770713100
2026-02-10 14:50:08,763 [INFO] DEBUG: df timestamp as dates: 2025-11-28T09:15:00 - 2026-02-10T14:15:00
2026-02-10 14:50:08,765 [INFO] Filtered data from 341 to 334 bars (filter_from=1764347934, to=1770715268)
2026-02-10 14:50:08,766 [INFO] PAGINATION: Returning 334 bars for ^NSEI (60)
2026-02-10 14:50:08,772 [INFO] DEBUG CORS: Origin header received: 'http://localhost:5173'
2026-02-10 14:50:09,929 [INFO] DEBUG CORS: Origin header received: 'http://localhost:5173'
2026-02-10 14:50:09,942 [INFO] [Step-by-Step] Fetching candles: ^NSEI [yfinance] from 2025-11-07 to 2026-02-10, resolution: 60
2026-02-10 14:50:09,942 [INFO] [Step-by-Step] Lookback bars requested: 5000
2026-02-10 14:50:09,943 [INFO] [YFinance] Client initialized
2026-02-10 14:50:09,943 [INFO] [Step-by-Step] Adjusted from_date: 2025-11-07 -> 2016-08-24 (expanded lookback: 3362 days)
2026-02-10 14:50:09,944 [INFO] Cache MISS: ^NSEI:60:2016-08-24:2026-02-10
2026-02-10 14:50:09,944 [INFO] [YFinance] Fetching ^NSEI | interval=60 -> 1h | 2016-08-24 to 2026-02-10
2026-02-10 14:50:09,945 [INFO] [YFinance] WARNING: Requested 3457 days but 1h limit is 700 days
2026-02-10 14:50:09,945 [INFO] [YFinance] Adjusted start date to 2024-03-12
2026-02-10 14:50:09,946 [INFO] [YFinance] Requesting dates: start=2024-03-12, end=2026-02-11 for ^NSEI
2026-02-10 14:50:10,438 [INFO] [YFinance] Received 3297 bars
2026-02-10 14:50:10,464 [INFO] [YFinance] Returning 3297 bars, range: 2024-03-12 09:15:00 to 2026-02-10 14:15:00
2026-02-10 14:50:10,465 [INFO] Cache PUT: ^NSEI:60:2016-08-24:2026-02-10 (TTL: 300.0s, 3297 rows)
2026-02-10 14:50:10,475 [INFO] [Replay] Returning 3297 candles, option_cache_ready: False
2026-02-10 14:50:10,559 [INFO] DEBUG CORS: Origin header received: 'http://localhost:5173'
2026-02-10 14:50:10,563 [INFO] DEBUG CORS: Origin header received: 'http://localhost:5173'
2026-02-10 14:50:10,666 [INFO] DEBUG CORS: Origin header received: 'http://localhost:5173'
2026-02-10 14:50:11,078 [INFO] DEBUG CORS: Origin header received: 'http://localhost:5173'
2026-02-10 14:50:11,103 [INFO] [Study] Using scale_ratio from chart: 5.499999999999955
2026-02-10 14:50:11,106 [INFO] Initialized AngularPriceCoverageStudy. Config: {'left_bars': 5, 'right_bars': 5, 'fractions': [0.875, 0.75, 0.5, 0.25, 0.125], 'fraction_colors': ['#c62828', '#ad1457', '#6a1b9a', '#283593', '#00695c'], 'main_color': '#FF6600', 'line_extension_bars': 50, 'remove_completed_fans': True, 'main_line_width': 1, 'fraction_line_width': 2, 'scale_ratio': 5.499999999999955, 'show_recursive_inner_fans': True, 'show_recursive_outer_fans': True, 'max_inner_fans': 5, 'max_outer_fans': 3}
2026-02-10 14:50:11,109 [INFO] [Study] Slow path: Rebuilding from 0 to 2850
2026-02-10 14:50:11,110 [INFO] [Study] First process_bar call at index 0. Running initialize_history.
2026-02-10 14:50:11,111 [INFO] [Study] initialize_history called with 1 candles
2026-02-10 14:50:11,111 [INFO] [Study] Not enough candles for pivot detection
2026-02-10 14:50:11,342 [INFO] [Step 3] Context: bearish, Anchor: high @ 25802.5
2026-02-10 14:50:11,343 [INFO] [Step 3] Inner stack size: 2, Outer stack size: 3
2026-02-10 14:50:11,358 [INFO] [AngleEngine] scale_ratio=5.499999999999955, slope_per_bar=8.4233, visual_slope=1.5315, theta=56.86°
2026-02-10 14:50:11,359 [INFO] [Step 3] Primary fan 0 created with 5 lines
2026-02-10 14:50:11,364 [INFO] [AngleEngine] scale_ratio=5.499999999999955, slope_per_bar=6.8444, visual_slope=1.2444, theta=51.22°
2026-02-10 14:50:11,365 [INFO] [Step 3] Primary fan 1 created with 5 lines
2026-02-10 14:50:11,373 [INFO] [AngleEngine] scale_ratio=5.499999999999955, slope_per_bar=8.1510, visual_slope=1.4820, theta=55.99°
2026-02-10 14:50:11,373 [INFO] [Step 3] Primary fan 2 created with 5 lines
2026-02-10 14:50:11,374 [INFO] [Step 3] Outer anchor for secondary fans: low @ 24588.0
2026-02-10 14:50:11,376 [INFO] [AngleEngine] scale_ratio=5.499999999999955, slope_per_bar=11.8886, visual_slope=2.1616, theta=65.17°
2026-02-10 14:50:11,377 [INFO] [Step 3] Secondary fan 0 created with 5 lines
2026-02-10 14:50:11,381 [INFO] [AngleEngine] scale_ratio=5.499999999999955, slope_per_bar=15.4674, visual_slope=2.8122, theta=70.43°
2026-02-10 14:50:11,381 [INFO] [Step 3] Secondary fan 1 created with 5 lines
2026-02-10 14:50:11,382 [INFO] [Step 3] Total drawings created: 25
2026-02-10 14:50:11,382 [INFO] [Study] Index 2850: Added 6 pivot markers from study
2026-02-10 14:50:11,383 [INFO] [Study] Index 2850: Snapshot of 5 active fans
2026-02-10 14:50:11,384 [INFO] [Study] Fan ad94ba47: 5 lines
2026-02-10 14:50:11,384 [INFO] [Study] Fan 5d3853e2: 5 lines
2026-02-10 14:50:11,385 [INFO] [Study] Fan 2e90216e: 5 lines
2026-02-10 14:50:11,385 [INFO] [Study] Fan b22560ca: 5 lines
2026-02-10 14:50:11,386 [INFO] [Study] Fan 8f98a95e: 5 lines
2026-02-10 14:50:11,390 [INFO] DEBUG CORS: Origin header received: 'http://localhost:5173'
