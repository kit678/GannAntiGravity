// public/main.js
// ----------------------------------------------------------
// TradingView Advanced Charting Library – demo integration
// ----------------------------------------------------------

(function () {
  /* 
     Custom indicator functions (MyMovingAverage, PivotHighLow) 
     are now expected to be loaded from separate files 
     via <script> tags in index.html before this script.
  */

  /* ------------------------------------------------------------------
   * Bootstrap the chart once DOM is ready
   * ---------------------------------------------------------------- */
  window.addEventListener('DOMContentLoaded', () => {
    // For diagnostics, ensure we are not in replay mode
    localStorage.removeItem('bar_replay');

    if (typeof window.datafeedManager === 'undefined') {
        console.error("CRITICAL: datafeedManager is not available in main.js. Ensure datafeedManager.js and krakenDatafeed.js are loaded and globally expose their objects before main.js runs.");
        return;
    }

    const widgetOptions = {
      container: 'tv-container',
      library_path: './charting_library/',
      locale: 'en',
      symbol: 'AAPL',
      interval: localStorage.getItem('timeframe') || '1D', // Default to Day
      fullscreen: true,
      debug: true,
      datafeed: new Datafeeds.UDFCompatibleDatafeed("https://demo-feed-data.tradingview.com"),
      // disabled_features: ["use_localstorage_for_settings"],

      /* Register the custom indicator */
      custom_indicators_getter: (PineJS) =>
        Promise.resolve([
          MyMovingAverage(PineJS),
          PivotHighLow(PineJS),
          PivotHighLowAngles(PineJS),
          MySimpleMA(PineJS)
        ]),
    };

    // Initialize the chart directly
    const tvWidget = new TradingView.widget(widgetOptions);
    
    // Initialize the pivot fan drawer
    new PivotFanDrawer(tvWidget);

    // Expose for quick debugging in DevTools if desired
    window.tvWidget = tvWidget;
  });
})();
