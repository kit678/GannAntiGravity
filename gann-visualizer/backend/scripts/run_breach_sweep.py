"""
The RELIANCE breach definition sweep.

Builds four corpora (close1, wick1, close2, close3) from the cached bars -
never fetching - checks the close2 rebuild against the existing corpus,
scores every rule on every row, applies the pre-registered selection rule,
and writes the choice file and the results document.

Spec: docs/superpowers/specs/2026-10-16-gann-breach-definition-sweep-design.md

Usage (from gann-visualizer/backend/):
    python scripts/run_breach_sweep.py \
        --cache C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/bars \
        --reference C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/reliance_5m_x1/events.parquet \
        --out-root C:/Dev/GannTesting/gann-visualizer/backend/logs/corpus/breach_sweep \
        --choice <repo>/docs/superpowers/specs/2026-10-16-gann-breach-sweep-choice.json \
        --results <repo>/docs/superpowers/specs/2026-10-16-gann-breach-sweep-results.md

`--rules close1 --build-only` builds one corpus and stops, so the slow builds
can run as parallel processes. Corpora already on disk under the same
settings are reused. close2 is always built first and gated at once.
--from, --to and --shadows exist for tests; the sweep uses the defaults.
"""

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Union

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from build_gann_corpus import ensure_corpus
from mine_gann_corpus import load_scored_events
from study_tool.corpus_writer import ALL_SLICES
from study_tool.mining.breach_sweep import (
    RULE_ORDER, RULES_BY_NAME, RuleScore, Selection, choice_record,
    score_rule, select_rule, write_choice,
)
from study_tool.mining.regression_gate import GateResult, check_regression
from study_tool.mining.sweep_report import render_sweep_results

SYMBOL = "RELIANCE"
FROM_DATE = "2024-09-02"
TO_DATE = "2026-09-01"
INTERVAL = "5"
SCALE = 1
SHADOWS = 50
SEED = 7
GATE_RULE = "close2"

PathLike = Union[str, Path]


class RegressionGateError(RuntimeError):
    """The close2 rebuild does not reproduce the existing corpus."""


def peak_memory_gb() -> Optional[float]:
    """
    This process's peak working set in GB, or None off Windows.

    Printed after every build so the RUN task can decide whether the other
    three builds fit in memory side by side. ctypes rather than psutil,
    which is not installed.
    """
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32")
    psapi = ctypes.WinDLL("psapi")
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(ProcessMemoryCounters), wintypes.DWORD]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL

    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    if not psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(),
                                      ctypes.byref(counters), counters.cb):
        return None
    return counters.PeakWorkingSetSize / 1e9


def _print_peak_memory() -> None:
    peak = peak_memory_gb()
    if peak is not None:
        print(f"peak memory so far: {peak:.1f} GB")


def corpus_dir_for(out_root: PathLike, rule: str) -> Path:
    return Path(out_root) / f"reliance_5m_x1_{rule}"


def build_rule(rule: str, out_root: PathLike, cache_dir: PathLike,
               from_date: str = FROM_DATE, to_date: str = TO_DATE,
               shadows: int = SHADOWS) -> str:
    """Build (or reuse) one rule's corpus. Never fetches."""
    spec = RULES_BY_NAME[rule]
    return ensure_corpus(
        symbol=SYMBOL, from_date=from_date, to_date=to_date,
        interval=INTERVAL, price_scale=SCALE, shadow_count=shadows,
        seed=SEED, cache_dir=cache_dir,
        out_dir=corpus_dir_for(out_root, rule),
        breach_mode=spec.breach_mode,
        confirmation_closes=spec.confirmation_closes)


def run_gate(out_root: PathLike, reference: PathLike) -> GateResult:
    result = check_regression(
        reference, corpus_dir_for(out_root, GATE_RULE) / "events.parquet")
    print(f"regression gate: {'PASSED' if result.passed else 'FAILED'} - "
          f"{result.reason}")
    if not result.passed:
        raise RegressionGateError(
            f"close2 rebuild does not match {reference}: {result.reason}. "
            "Stop and find out why before scoring anything.")
    return result


def run_sweep(out_root: PathLike, cache_dir: PathLike, reference: PathLike,
              choice_path: PathLike, results_path: PathLike,
              rules: Sequence[str] = RULE_ORDER, build_only: bool = False,
              from_date: str = FROM_DATE, to_date: str = TO_DATE,
              shadows: int = SHADOWS) -> Optional[Selection]:
    """
    Build, gate, score, select. Returns the Selection, or None when
    build_only. Raises RegressionGateError if close2 does not reproduce the
    reference; nothing is scored or written in that case.
    """
    unknown = [rule for rule in rules if rule not in RULES_BY_NAME]
    if unknown:
        raise ValueError(f"unknown breach rules {unknown}; expected {RULE_ORDER}")
    if not build_only and set(rules) != set(RULE_ORDER):
        raise ValueError(
            "scoring needs all four rules; pass build_only to build a subset")

    # close2 first, so a failing gate stops the run before the other builds.
    ordered = sorted(rules, key=lambda r: (r != GATE_RULE, RULE_ORDER.index(r)))
    gate: Optional[GateResult] = None
    for rule in ordered:
        started = time.time()
        status = build_rule(rule, out_root, cache_dir, from_date, to_date,
                            shadows)
        print(f"{rule}: {status} in {time.time() - started:.0f}s")
        _print_peak_memory()
        if rule == GATE_RULE:
            gate = run_gate(out_root, reference)

    if build_only:
        return None

    scores: Dict[str, RuleScore] = {}
    shadow_counts: Dict[str, int] = {}
    for rule in RULE_ORDER:
        started = time.time()
        scored = load_scored_events(corpus_dir_for(out_root, rule),
                                    slice_name=ALL_SLICES)
        scores[rule] = score_rule(rule, scored.events, scored.meta.shadow_count)
        shadow_counts[rule] = scored.meta.shadow_count
        del scored
        print(f"{rule}: scored in {time.time() - started:.0f}s")

    if len(set(shadow_counts.values())) != 1:
        raise ValueError(
            f"the four corpora disagree on the shadow count: {shadow_counts}")
    corpora = {rule: str(corpus_dir_for(out_root, rule))
               for rule in RULE_ORDER}

    selection = select_rule({name: s.lag_free for name, s in scores.items()})
    record = choice_record(
        selection, scores, gate, shadow_count=shadow_counts[RULE_ORDER[0]],
        corpora=corpora)

    context = {
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "cache_dir": str(cache_dir),
        "reference": str(reference),
        "corpora": corpora,
    }
    results_path = Path(results_path)
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(
        render_sweep_results(scores, selection, gate, context),
        encoding="utf-8")
    # After the results document, so a choice file never exists without it;
    # write_choice refuses to replace a different choice already on disk.
    write_choice(choice_path, record)

    print(f"chosen: {selection.chosen or 'null - AAPL is not built'}")
    print(f"wrote {choice_path}\nwrote {results_path}")
    return selection


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--out-root", required=True)
    parser.add_argument("--choice", required=True)
    parser.add_argument("--results", required=True)
    parser.add_argument("--rules", default=",".join(RULE_ORDER))
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--from", dest="from_date", default=FROM_DATE)
    parser.add_argument("--to", dest="to_date", default=TO_DATE)
    parser.add_argument("--shadows", type=int, default=SHADOWS)
    args = parser.parse_args(argv)

    rules = tuple(r.strip() for r in args.rules.split(",") if r.strip())
    try:
        run_sweep(out_root=args.out_root, cache_dir=args.cache,
                  reference=args.reference, choice_path=args.choice,
                  results_path=args.results, rules=rules,
                  build_only=args.build_only, from_date=args.from_date,
                  to_date=args.to_date, shadows=args.shadows)
    except RegressionGateError as exc:
        print(f"STOPPED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
