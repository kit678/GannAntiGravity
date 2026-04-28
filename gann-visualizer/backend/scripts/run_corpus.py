"""Generate the MVP corpus: NIFTY × BANKNIFTY × {5m, 15m, 60m} × ~6 months.

Held-out month: 2026-03-28 → 2026-04-28 (most recent month). Excluded here.
In-sample: 2025-09-28 → 2026-03-27 (~6 months prior).

NOTES:
- BANKNIFTY yfinance symbol is "^NSEBANK"
- yfinance limits intraday (5m) history to ~60 days. For 5m slices we use
  a shorter date range.
- Run as: cd gann-visualizer/backend && python -m scripts.run_corpus
"""
import logging
import sys
import os
from typing import Iterable, NamedTuple

sys.path.append(os.path.abspath(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from run_simulation import run_simulation


class Slice(NamedTuple):
    instrument: str
    resolution: str
    from_date: str
    to_date: str
    source: str = "yfinance"


IN_SAMPLE_FROM = "2025-09-28"
IN_SAMPLE_TO   = "2026-03-27"
SHORT_FROM_5M  = "2026-01-28"   # ~60-day limit for yfinance 5m
SHORT_TO_5M    = "2026-03-27"

CORPUS: list[Slice] = [
    # NIFTY
    Slice("^NSEI",    "60", IN_SAMPLE_FROM, IN_SAMPLE_TO),
    Slice("^NSEI",    "15", IN_SAMPLE_FROM, IN_SAMPLE_TO),
    Slice("^NSEI",    "5",  SHORT_FROM_5M,  SHORT_TO_5M),
    # BANKNIFTY
    Slice("^NSEBANK", "60", IN_SAMPLE_FROM, IN_SAMPLE_TO),
    Slice("^NSEBANK", "15", IN_SAMPLE_FROM, IN_SAMPLE_TO),
    Slice("^NSEBANK", "5",  SHORT_FROM_5M,  SHORT_TO_5M),
]


def run_all(slices: Iterable[Slice]) -> None:
    for s in slices:
        logging.info("=" * 80)
        logging.info(f"CORPUS SLICE: {s.instrument} @ {s.resolution}m  {s.from_date} → {s.to_date}")
        logging.info("=" * 80)
        try:
            run_simulation(
                symbol=s.instrument,
                resolution=s.resolution,
                data_source=s.source,
                from_date=s.from_date,
                to_date=s.to_date,
                lookback_bars=5000,
            )
        except Exception:
            logging.exception(f"Slice failed: {s}. Continuing with next slice.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    run_all(CORPUS)
    logging.info("Corpus generation complete.")
