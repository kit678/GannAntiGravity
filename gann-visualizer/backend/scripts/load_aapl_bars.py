"""
Resample the AAPL 1-minute RTH JSON into the 5-minute bar cache.

Refuses to run until the RELIANCE breach sweep has written a choice file
that names a rule: AAPL bars are not built before the rule is fixed.

Usage (from gann-visualizer/backend/):
    python scripts/load_aapl_bars.py \
        --choice <repo>/docs/superpowers/specs/2026-10-16-gann-breach-sweep-choice.json \
        --json C:/Dev/GannTesting/data_local/aapl_rth_1m.json \
        --cache C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/bars

Prints the bar and session count, the bars-per-session histogram, the extended-hours minutes dropped on
early-close days, the 2024-08-30 close (to check against the published
close in the write-up) and the last close before the window (which fixes
the x6 scale).
"""

import argparse
import os
import sys
from typing import List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from study_tool.aapl_bars import (
    last_close_before, read_minute_json, resample_to_5m, session_close,
    write_bar_cache,
)
from study_tool.bar_cache import cache_path
from study_tool.mining.breach_sweep import read_choice

AAPL_SCALE = 6


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--choice", required=True)
    parser.add_argument("--json", required=True)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--symbol", default="AAPL")
    parser.add_argument("--from", dest="from_date", default="2024-09-02")
    parser.add_argument("--to", dest="to_date", default="2026-09-01")
    parser.add_argument("--interval", default="5")
    parser.add_argument("--check-date", default="2024-08-30")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)

    rule = read_choice(args.choice)   # raises before any AAPL data is read
    print(f"breach rule {rule.name} is chosen; loading AAPL bars")

    minutes = read_minute_json(args.json)
    resampled = resample_to_5m(minutes, args.from_date, args.to_date)
    bars = write_bar_cache(resampled.bars, args.symbol, args.from_date,
                           args.to_date, args.interval, args.cache,
                           overwrite=args.overwrite)
    check_close = session_close(minutes, args.check_date)
    before_date, before_close = last_close_before(minutes, args.from_date)

    print(f"{len(bars)} bars over {resampled.sessions} sessions "
          f"{args.from_date}..{args.to_date}")
    histogram = ", ".join(f"{bars_in} x {sessions}" for bars_in, sessions
                          in resampled.bars_per_session.items())
    print(f"bars per session (bars x sessions): {histogram} "
          "(78 is a full day, 42 an early close; short days are reported, "
          "not refused)")
    print(f"dropped {resampled.early_close_minutes_dropped} minutes after "
          "13:00 on early-close days")
    print(f"{args.check_date} close: {check_close} "
          "(check against the published close)")
    print(f"last close before {args.from_date}: {before_close} on "
          f"{before_date}; x{AAPL_SCALE} = {before_close * AAPL_SCALE:.0f}")
    print(f"wrote {cache_path(args.cache, args.symbol, args.from_date, args.to_date, args.interval)}")


if __name__ == "__main__":
    main()
