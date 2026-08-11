"""Pull multi-year Binance USD-M futures klines into a flat history corpus.

Why a separate corpus rather than another `logs/backend/runs/<sym>/<tf>/` dir:
those directories carry Gann event streams and are globbed by the existing
hypothesis tooling. This writes price only, to `logs/backend/history/`, so the
RSI research harness can pull large continuous windows without every other
hypothesis trying to score them.

Futures (`fapi`) rather than spot, because the 0.04%/side taker fee the trade
model assumes is the futures fee.

Usage:
    python gann-visualizer/backend/scripts/fetch_binance_history.py
    python gann-visualizer/backend/scripts/fetch_binance_history.py --years 5 \
        --symbols BTCUSDT ETHUSDT --intervals 15m 1h
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = "https://fapi.binance.com/fapi/v1/klines"
LIMIT = 1500
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
OUT_ROOT = os.path.join(REPO_ROOT, "logs", "backend", "history")

INTERVAL_MS = {
    "1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
    "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000, "6h": 21_600_000,
    "12h": 43_200_000, "1d": 86_400_000,
}


def _get(url: str, attempts: int = 5):
    """Binance rate-limits with 429/418; back off rather than hammering."""
    delay = 1.0
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code in (418, 429) or exc.code >= 500:
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            time.sleep(delay)
            delay = min(delay * 2, 60)
    raise RuntimeError(f"gave up fetching {url}")


def fetch(symbol: str, interval: str, start_ms: int, end_ms: int) -> list[list]:
    step = INTERVAL_MS[interval]
    rows: list[list] = []
    cursor = start_ms
    while cursor < end_ms:
        url = (
            f"{BASE}?symbol={symbol}&interval={interval}"
            f"&startTime={cursor}&endTime={end_ms}&limit={LIMIT}"
        )
        batch = _get(url)
        if not batch:
            break
        rows.extend(batch)
        next_cursor = int(batch[-1][0]) + step
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        if len(batch) < LIMIT:
            break
        time.sleep(0.12)
    return rows


def write_csv(path: str, rows: list[list]) -> int:
    """Drop the final kline: it is the still-forming bar and would be a partial."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    seen: set[int] = set()
    written = 0
    now_ms = int(time.time() * 1000)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write("timestamp,open,high,low,close,volume,time,bar_index\n")
        for row in rows:
            open_ms = int(row[0])
            close_ms = int(row[6])
            if close_ms >= now_ms:
                continue
            if open_ms in seen:
                continue
            seen.add(open_ms)
            seconds = open_ms // 1000
            handle.write(
                f"{seconds},{row[1]},{row[2]},{row[3]},{row[4]},{row[5]},{seconds},{written}\n"
            )
            written += 1
    return written


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+",
                        default=["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"])
    parser.add_argument("--intervals", nargs="+", default=["15m", "1h", "4h"])
    parser.add_argument("--years", type=float, default=5.0)
    args = parser.parse_args()

    end = datetime.now(timezone.utc) - timedelta(minutes=5)
    start = end - timedelta(days=int(args.years * 365.25))
    start_ms, end_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)

    print(f"window {start.date()} -> {end.date()}  ({args.years}y)")
    for symbol in args.symbols:
        for interval in args.intervals:
            if interval not in INTERVAL_MS:
                print(f"  skip {symbol} {interval}: unknown interval")
                continue
            path = os.path.join(OUT_ROOT, symbol, interval, "candles.csv")
            try:
                rows = fetch(symbol, interval, start_ms, end_ms)
            except Exception as exc:  # noqa: BLE001 - one bad symbol must not kill the run
                print(f"  FAIL {symbol} {interval}: {type(exc).__name__}: {exc}")
                continue
            count = write_csv(path, rows)
            first = datetime.fromtimestamp(int(rows[0][0]) / 1000, timezone.utc).date() if rows else "-"
            print(f"  {symbol:9s} {interval:4s} {count:7d} bars  from {first}  -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
