"""Serve a one-page candlestick chart of AAPL 15-minute bars from Alpaca.

Standalone from the main visualizer: fetches once at startup, embeds the
candles in the HTML, and serves it on localhost. Run it, open the URL.

    python scripts/aapl_15m_page.py
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alpaca_client import AlpacaClient  # noqa: E402

SYMBOL = "AAPL"
RESOLUTION = "15"
FROM_DATE = "2025-03-10"
TO_DATE = "2025-04-01"
PORT = int(os.environ.get("PORT", "8777"))

PAGE = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>AAPL 15m — {from_date} to {to_date}</title>
<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<style>
  body {{ margin: 0; background: #101418; color: #d7dde3;
         font: 14px/1.4 system-ui, sans-serif; }}
  header {{ padding: 14px 18px; border-bottom: 1px solid #222b33; }}
  h1 {{ margin: 0 0 4px; font-size: 16px; font-weight: 600; }}
  .meta {{ color: #8b98a5; font-size: 12px; }}
  #chart {{ height: calc(100vh - 70px); }}
</style>
</head>
<body>
<header>
  <h1>Apple Inc (AAPL) — 15 minute candles</h1>
  <div class="meta">{from_date} to {to_date} &middot; {count} bars &middot;
    source: Alpaca ({feed} feed) &middot; times shown in UTC</div>
</header>
<div id="chart"></div>
<script>
  const candles = {candles};
  const el = document.getElementById('chart');
  const chart = LightweightCharts.createChart(el, {{
    autoSize: true,
    layout: {{ background: {{ color: '#101418' }}, textColor: '#d7dde3' }},
    grid: {{ vertLines: {{ color: '#1c242b' }}, horzLines: {{ color: '#1c242b' }} }},
    timeScale: {{ timeVisible: true, secondsVisible: false, borderColor: '#2a343d' }},
    rightPriceScale: {{ borderColor: '#2a343d' }},
    crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
  }});
  const series = chart.addCandlestickSeries({{
    upColor: '#26a69a', downColor: '#ef5350',
    wickUpColor: '#26a69a', wickDownColor: '#ef5350', borderVisible: false,
  }});
  series.setData(candles);
  chart.timeScale().fitContent();
</script>
</body>
</html>
"""


def build_page() -> bytes:
    client = AlpacaClient()
    df = client.fetch_data(SYMBOL, FROM_DATE, TO_DATE, RESOLUTION)
    if df.empty:
        raise SystemExit(f"No bars returned for {SYMBOL} {FROM_DATE}..{TO_DATE}")

    candles = [
        {
            "time": int(row.timestamp),
            "open": row.open,
            "high": row.high,
            "low": row.low,
            "close": row.close,
        }
        for row in df.itertuples()
    ]

    html = PAGE.format(
        from_date=FROM_DATE,
        to_date=TO_DATE,
        count=len(candles),
        feed=client.feed,
        candles=json.dumps(candles),
    )
    return html.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    page = b""

    def do_GET(self):
        if self.path not in ("/", "/index.html"):
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(self.page)))
        self.end_headers()
        self.wfile.write(self.page)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    Handler.page = build_page()
    print(f"Serving AAPL 15m chart at http://localhost:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
