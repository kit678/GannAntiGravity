"""
Batch Simulation Runner — Runs run_simulation.py across multiple tickers/timeframes.

Usage:
    python run_batch_simulation.py --tickers BTCUSDT,ETHUSDT --timeframes 60
    python run_batch_simulation.py --tickers SOLUSDT --timeframes 60 --scale-ratio 54.905
    python run_batch_simulation.py --tickers BTCUSDT --timeframes 60,240 --force
"""
import subprocess
import sys
import os
import argparse
import time

TRACE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "logs", "backend")


def run_batch(tickers, timeframes, scale_ratio=None, force=False):
    """Run simulation for each ticker x timeframe combination."""
    total = len(tickers) * len(timeframes)
    completed = 0
    failed = []

    print(f"Batch: {total} runs ({len(tickers)} tickers x {len(timeframes)} timeframes)")
    print("=" * 60)

    for ticker in tickers:
        for tf in timeframes:
            trace_file = os.path.join(TRACE_DIR, f"simulation_trace_{ticker}_{tf}.log")

            if os.path.exists(trace_file) and not force:
                print(f"SKIP: {ticker} {tf} — trace log already exists")
                completed += 1
                continue

            print(f"RUN : {ticker} {tf} ...", end=" ", flush=True)

            cmd = [
                sys.executable, "run_simulation.py",
                "--symbol", ticker,
                "--resolution", tf,
                "--source", "binance",
            ]
            if scale_ratio is not None:
                cmd.extend(["--scale-ratio", str(scale_ratio)])

            t0 = time.time()

            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                                       cwd=os.path.dirname(os.path.abspath(__file__)))
                elapsed = time.time() - t0

                if result.returncode != 0:
                    print(f"FAIL (exit={result.returncode}, {elapsed:.0f}s)")
                    print(f"  stderr: {result.stderr[-300:] if result.stderr else 'none'}")
                    failed.append((ticker, tf))
                    continue

                # Check trace log was created
                if not os.path.exists(trace_file):
                    print(f"FAIL (no trace log, {elapsed:.0f}s)")
                    failed.append((ticker, tf))
                    continue

                # Quick event count check
                event_count = 0
                with open(trace_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if "| event_type:" in line and "SNAPSHOT" not in line:
                            event_count += 1

                print(f"DONE ({elapsed:.0f}s, {event_count} events)")
                completed += 1

            except subprocess.TimeoutExpired:
                print(f"FAIL (timeout after 600s)")
                failed.append((ticker, tf))
            except Exception as e:
                print(f"FAIL ({e})")
                failed.append((ticker, tf))

    print("=" * 60)
    print(f"Completed: {completed}/{total}")

    if failed:
        print(f"Failed ({len(failed)}):")
        for t, f in failed:
            print(f"  - {t} {f}")

    return len(failed) == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch Gann Angular Price Coverage Simulation")
    parser.add_argument("--tickers", type=str, required=True,
                        help="Comma-separated ticker symbols (e.g., BTCUSDT,ETHUSDT)")
    parser.add_argument("--timeframes", type=str, required=True,
                        help="Comma-separated resolution codes (e.g., 60,240)")
    parser.add_argument("--scale-ratio", type=float, default=None,
                        help="Override scale_ratio for all runs")
    parser.add_argument("--force", action="store_true",
                        help="Re-run even if trace log already exists")
    args = parser.parse_args()

    tickers = [t.strip() for t in args.tickers.split(",") if t.strip()]
    timeframes = [t.strip() for t in args.timeframes.split(",") if t.strip()]

    if not tickers or not timeframes:
        print("ERROR: --tickers and --timeframes are required")
        sys.exit(1)

    # Ensure trace directory exists
    os.makedirs(TRACE_DIR, exist_ok=True)

    success = run_batch(tickers, timeframes, args.scale_ratio, args.force)
    sys.exit(0 if success else 1)
