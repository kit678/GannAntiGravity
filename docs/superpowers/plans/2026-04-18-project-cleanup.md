# Project Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan step-by-step. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove all stale files, dead code, one-off scripts, and inactive log files. Reorganize the project tree. Update path references affected by reorganization.

**Architecture:** File deletion and move operations with targeted Python path reference updates. No code logic changes.

**Tech Stack:** Bash/shell commands for file ops, Python path edits in 4 files.

---

## File Map

### Files to modify (path references)
- `gann-visualizer/backend/main.py` — line 21: `LOG_DIR` path
- `gann-visualizer/backend/run_simulation.py` — lines 20, 221: `log_dir` path
- `gann-visualizer/backend/study_tool/angular_coverage_study.py` — line 31: `_log_dir` path
- `gann-visualizer/backend/study_tool/unified_state_machine.py` — line 31: `log_dir` path
- `.gitignore` — update logs ignore patterns

### Files to move
- `CommoditiesCourse/` → `docs/research/CommoditiesCourse/`
- `code_references/` → `gann-visualizer/code_references/`
- Docs scattered at root and in `docs/` → reorganize into `docs/architecture/`, `docs/api/`, `docs/strategy/`

### Files to delete
- Root-level: `gemini_test.py`, `repro_main.py`, `test_doc_example.mjs`, `test_v2_fetch.mjs`, `angular_coverage_study_remote.py`, `intersection_detector_remote.py`, `pivot_detector_remote.py`, `backend_scale_check.py`, `extract_log.py`, `setup_env.ps1`, `angle_diff.txt`, `c:DevGannTestingangle_diff2.txt`, `package.json` (root), `package-lock.json` (root)
- `tools/` (entire directory)
- Backend root orphaned scripts: `compare_csv.py`, `debug_cross.py`, `debug_lines.py`, `debug_sweep.py`, `fix.py`, `fix_indent.py`, `inspect_master.py`, `test_agg.py`, `test_bars.py`, `test_debug.py`, `test_diwali.py`, `test_negative_bars.py`, `test_scenario.py`, `test_script.py`, `test_script2.py`, `test_script3.py`, `test_sm.py`, `test_yf.py`
- `gann-visualizer/debug.txt`
- Malformed file: `gann-visualizer/backend/c:DevGannTestinggann-visualizerbackendstudy_toolunified_state_machine.py`
- Frontend eslint outputs: `gann-visualizer/frontend/eslint_err.json`, `eslint_final.json`, `eslint_full.json`, `eslint_others.json`, `eslint_output.json`
- Stale logs: `gann-visualizer/backend/logs/clean.log`, `clean2.log`, `simulation_run_20260319_122732.log`, `simulation_run_20260319_122744.log`, `target_progression_validation.log`, `target_progression_events.txt`, `event_ledger.csv`, `state_matrix.csv`, all of `gann-visualizer/backend/logs/study_debug/`, all of `gann-visualizer/backend/logs/analysis/`
- Frontend stale logs: all `gann-visualizer/logs/localhost-*.log`, `gann-visualizer/sim_output.log`
- All `.~lock.*` files
- All `__pycache__/` and `.pytest_cache/` directories
- Aider cache: `.aider.chat.history.md`, `.aider.input.history`, `.aider.tags.cache.v4`

### Active logs to preserve and move
- `gann-visualizer/backend/logs/backend_session_*.log` (most recent)
- `gann-visualizer/backend/logs/replay_trace.log`
- `gann-visualizer/backend/logs/simulation_trace.log`
- `gann-visualizer/backend/logs/simulation_run.log`
- `gann-visualizer/backend/logs/simulation_events.csv`
- `gann-visualizer/backend/logs/intersections_*.csv`

---

## Phase 1: Pre-cleanup Commit

- [ ] **Step 1: Commit current state**

```bash
git add -A
git commit -m "chore: pre-cleanup commit — all changes before cleanup
```
---

## Phase 2: Remove Stale Files

- [ ] **Step 2: Remove root-level stale scripts (13 files)**

```bash
rm -f \
  gemini_test.py \
  repro_main.py \
  test_doc_example.mjs \
  test_v2_fetch.mjs \
  angular_coverage_study_remote.py \
  intersection_detector_remote.py \
  pivot_detector_remote.py \
  backend_scale_check.py \
  extract_log.py \
  setup_env.ps1 \
  angle_diff.txt \
  'c:DevGannTestingangle_diff2.txt' \
  package.json \
  package-lock.json
```

- [ ] **Step 3: Remove `tools/` directory**

```bash
rm -rf tools/
```

- [ ] **Step 4: Remove backend orphaned scripts (19 files)**

```bash
cd gann-visualizer/backend && rm -f \
  compare_csv.py \
  debug_cross.py \
  debug_lines.py \
  debug_sweep.py \
  fix.py \
  fix_indent.py \
  inspect_master.py \
  test_agg.py \
  test_bars.py \
  test_debug.py \
  test_diwali.py \
  test_negative_bars.py \
  test_scenario.py \
  test_script.py \
  test_script2.py \
  test_script3.py \
  test_sm.py \
  test_yf.py
```

- [ ] **Step 5: Remove frontend eslint output files**

```bash
rm -f gann-visualizer/frontend/eslint_err.json \
      gann-visualizer/frontend/eslint_final.json \
      gann-visualizer/frontend/eslint_full.json \
      gann-visualizer/frontend/eslint_others.json \
      gann-visualizer/frontend/eslint_output.json
```

- [ ] **Step 6: Remove `gann-visualizer/debug.txt` and malformed filename**

```bash
rm -f 'gann-visualizer/debug.txt'
rm -f 'gann-visualizer/backend/c:DevGannTestinggann-visualizerbackendstudy_toolunified_state_machine.py'
```

- [ ] **Step 7: Remove stale log files**

```bash
# Backend stale logs
rm -f gann-visualizer/backend/logs/clean.log \
      gann-visualizer/backend/logs/clean2.log \
      gann-visualizer/backend/logs/simulation_run_20260319_122732.log \
      gann-visualizer/backend/logs/simulation_run_20260319_122744.log \
      gann-visualizer/backend/logs/target_progression_validation.log \
      gann-visualizer/backend/logs/target_progression_events.txt \
      gann-visualizer/backend/logs/event_ledger.csv \
      gann-visualizer/backend/logs/state_matrix.csv

# Backend stale log directories
rm -rf gann-visualizer/backend/logs/study_debug/
rm -rf gann-visualizer/backend/logs/analysis/

# Frontend stale logs
rm -f gann-visualizer/logs/localhost-*.log
rm -f gann-visualizer/sim_output.log

# Lock files
find . -name ".~lock.*" -delete
```

- [ ] **Step 8: Remove all `__pycache__/` and `.pytest_cache/` directories**

```bash
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
```

- [ ] **Step 9: Remove aider cache files**

```bash
rm -f .aider.chat.history.md .aider.input.history .aider.tags.cache.v4
```

---

## Phase 3: Move & Reorganize

- [ ] **Step 10: Move active logs to new location**

```bash
mkdir -p logs/backend

# Move active backend logs
mv gann-visualizer/backend/logs/backend_session_*.log logs/backend/
mv gann-visualizer/backend/logs/replay_trace.log logs/backend/
mv gann-visualizer/backend/logs/simulation_trace.log logs/backend/
mv gann-visualizer/backend/logs/simulation_run.log logs/backend/
mv gann-visualizer/backend/logs/simulation_events.csv logs/backend/
mv gann-visualizer/backend/logs/intersections_*.csv logs/backend/
```

- [ ] **Step 11: Move `CommoditiesCourse/` → `docs/research/`**

```bash
mkdir -p docs/research
mv CommoditiesCourse/ docs/research/
```

- [ ] **Step 12: Create docs subdirectories and reorganize docs**

```bash
mkdir -p docs/architecture docs/api docs/strategy

# Move root-level docs
mv GANN_IMPLEMENTATION_SPEC.md docs/architecture/

# Move existing docs/ files
mv docs/ANGULAR_PRICE_COVERAGE_STRATEGY.md docs/strategy/
mv docs/Angular_Price_Coverage_Event_Classification_Implementation.md docs/strategy/
mv docs/Refining\ Breach\ Logic.md docs/strategy/
mv docs/angular_coverage_strategy_v4.md docs/strategy/
mv docs/STRATEGY_QUICK_REFERENCE.md docs/strategy/
mv docs/OPTION_DATA_INTEGRATION.md docs/api/
mv docs/REPLAY_FUNCTIONALITY_ANALYSIS.md docs/architecture/
mv docs/TRADINGVIEW_CODING_STANDARDS.md docs/architecture/
```

Note: `docs/dhan_api/` and `docs/tradingvew_advanced_charting_library/` contain large markdown docs that appear stale. Leave them for now — the user can decide if they want to remove or consolidate them.

- [ ] **Step 13: Move `code_references/` → `gann-visualizer/code_references/`**

```bash
mv code_references/ gann-visualizer/code_references/
```

---

## Phase 4: Update Path References

- [ ] **Step 14: Update `main.py` LOG_DIR path**

Modify `gann-visualizer/backend/main.py` line 21:

Old:
```python
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
```

New:
```python
LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "logs", "backend"
)
```

- [ ] **Step 15: Update `run_simulation.py` log_dir paths**

Modify `gann-visualizer/backend/run_simulation.py` lines 20 and 221:

Old (line 20):
```python
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
```

New (line 20):
```python
log_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "logs", "backend"
)
```

Same change applies at line 221.

- [ ] **Step 16: Update `angular_coverage_study.py` _log_dir path**

Modify `gann-visualizer/backend/study_tool/angular_coverage_study.py` line 31:

Old:
```python
_log_dir = os.path.join(_backend_dir, 'logs', 'study_debug')
```

New:
```python
_log_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "logs", "backend", "study_debug"
)
```

Also update the comment on line 28 that references the old path.

- [ ] **Step 17: Update `unified_state_machine.py` log_dir path**

Modify `gann-visualizer/backend/study_tool/unified_state_machine.py` line 31:

Old:
```python
log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
```

New:
```python
log_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "logs", "backend"
)
```

---

## Phase 5: Update `.gitignore`

- [ ] **Step 18: Update `.gitignore` for new logs location**

The current `.gitignore` has:
```
**/logs/
!gann-visualizer/backend/logs/
!gann-visualizer/backend/logs/*.log
```

Replace those 3 lines with:
```
!logs/
!logs/backend/
!logs/backend/*.log
```

Also ensure these patterns are present (add if missing):
```
__pycache__/
.pytest_cache/
.~lock*
```

The `.aider*` pattern already exists and is fine.

---

## Phase 6: Verify

- [ ] **Step 19: Verify backend starts without errors**

```bash
cd gann-visualizer/backend && python -c "from main import app; print('Backend imports OK')"
```

- [ ] **Step 20: Verify active logs are being written to new location**

```bash
ls logs/backend/
```

Expected: `backend_session_*.log`, `replay_trace.log`, `simulation_trace.log`, `simulation_run.log`, `simulation_events.csv`, `intersections_*.csv`

- [ ] **Step 21: Commit cleanup changes**

```bash
git add -A
git commit -m "chore: complete project cleanup — remove stale files, reorganize tree, update log paths"
```

---

## Spec Self-Review Checklist

- [x] All removals confirmed stale (no active imports)
- [x] Path updates identified: `main.py`, `run_simulation.py`, `angular_coverage_study.py`, `unified_state_machine.py`
- [x] Active logs preserved and will be moved to `logs/backend/`
- [x] `docs/` reorganization into `architecture/`, `api/`, `strategy/`, `research/`
- [x] `.gitignore` update for `logs/backend/` + cache patterns
- [x] `code_references/` moved to `gann-visualizer/code_references/`
