// datafeedManager.js

// Import your datafeed implementations here
// For now, we only have Kraken. When you add more, import them:
// import someOtherDatafeed from './someOtherDatafeed.js';

// Assume krakenDatafeed is globally available if not using modules,
// or you would import it if your setup supports ES modules.
// For this example, we'll assume krakenDatafeed is defined in krakenDatafeed.js
// and that krakenDatafeed.js is loaded before this manager in an HTML script tag.

const registeredDatafeeds = {
    kraken: krakenDatafeed, // This needs to be the actual object from krakenDatafeed.js
    // 'anotherSource': anotherDatafeedImplementation,
};

let activeSourceName = 'kraken'; // Default active source

const datafeedManager = {
    setActiveSource: (sourceName) => {
        if (registeredDatafeeds[sourceName]) {
            activeSourceName = sourceName;
            console.log(`[DatafeedManager] Active source set to: ${activeSourceName}`);
            // You might need to trigger a chart reload or symbol change here
            // if the chart is already initialized.
        } else {
            console.error(`[DatafeedManager] Error: Datafeed source "${sourceName}" not registered.`);
        }
    },

    getActiveSource: () => {
        return registeredDatafeeds[activeSourceName];
    },

    // This is the object that will be passed to the TradingView widget
    getTradingViewDatafeed: () => {
        // Create a proxy or wrapper around the active datafeed
        // This ensures that the charting library always calls methods on the currently active source
        const feed = {};
        const delegateMethods = [
            'onReady',
            'searchSymbols',
            'resolveSymbol',
            'getBars',
            'subscribeBars',
            'unsubscribeBars',
            'getServerTime',
            'getMarks',
            'getTimescaleMarks',
            'getVolumeProfileResolutionForPeriod'
        ];

        delegateMethods.forEach(methodName => {
            feed[methodName] = (...args) => {
                const activeFeed = datafeedManager.getActiveSource();
                if (activeFeed && typeof activeFeed[methodName] === 'function') {
                    return activeFeed[methodName](...args);
                } else {
                    console.error(`[DatafeedManager] Method "${methodName}" not found on active source "${activeSourceName}" or source not active.`);
                    // TradingView expects certain callbacks to be called, e.g., onResolveErrorCallback or onErrorCallback for getBars
                    // Handle appropriately, e.g., by calling the error callback if available in args
                    if (methodName === 'resolveSymbol' && args[2] && typeof args[2] === 'function') {
                        args[2]('Datafeed method not implemented');
                    }
                    if (methodName === 'getBars' && args[3] && typeof args[3] === 'function') {
                        args[3]('Datafeed method not implemented');
                    }
                    // For onReady, it might just hang if not implemented, or TV might use defaults.
                }
            };
        });

        return feed;
    }
};

// If not using modules, ensure this is available globally or attached to window e.g.
window.datafeedManager = datafeedManager; 