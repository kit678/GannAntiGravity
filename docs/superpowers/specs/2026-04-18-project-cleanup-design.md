# Project Cleanup & Reorganization Design

**Date:** 2026-04-18
**Status:** Draft

## Goal

Identify and remove stale files, dead code, one-off scripts, and inactive log files. Reorganize the project tree for clarity. Update any path references affected by the reorganization.

---

## 1. Tree Reorganization

### 1.1 Docs Consolidation

Move all documentation to `docs/` at root with subfolders:

```
docs/
├── architecture/      # System design docs
├── api/              # API-related docs
├── strategy/         # Trading strategy docs
└── research/          # CommoditiesCourse moved here
```

**Files to move into `docs/`:**
- `GANN_IMPLEMENTATION_SPEC.md` → `docs/architecture/`
- `README.md` (root) → `docs/` (or keep at root)
- `docs/ANGULAR_PRICE_COVERAGE_STRATEGY.md` → `docs/strategy/`
- `docs/Angular_Price_Coverage_Event_Classification_Implementation.md` → `docs/strategy/`
- `docs/Refining Breach Logic.md` → `docs/strategy/`
- `docs/angular_coverage_strategy_v4.md` → `docs/strategy/`
- `docs/STRATEGY_QUICK_REFERENCE.md` → `docs/strategy/`
- `docs/OPTION_DATA_INTEGRATION.md` → `docs/api/`
- `docs/REPLAY_FUNCTIONALITY_ANALYSIS.md` → `docs/architecture/`
- `docs/TRADINGVIEW_CODING_STANDARDS.md` → `docs/architecture/`
- `CommoditiesCourse/` → `docs/research/`

### 1.2 Logs Consolidation

Move all logs to `logs/` at root:

```
logs/
├── backend/           # All backend logs (see section 3)
└── frontend/          # Frontend server logs (localhost-*.log)
```

**Path updates required:**
| File | Old Path | New Path |
|------|----------|----------|
| `main.py` | `backend/logs/` | `logs/backend/` |
| `run_simulation.py` | `backend/logs/` | `logs/backend/` |
| `angular_coverage_study.py` | `backend/logs/study_debug/` | `logs/backend/study_debug/` |
| `unified_state_machine.py` | `backend/logs/` | `logs/backend/` |

### 1.3 Code References

Move `code_references/` from root to `gann-visualizer/code_references/`. Keep it empty.

---

## 2. Files to Remove

### 2.1 Root-level stale scripts
- `gemini_test.py` — One-off Gemini API test with hardcoded credentials
- `repro_main.py` — Throwaway yfinance date logic reproduction
- `test_doc_example.mjs` — One-off Dhan API test with credentials
- `test_v2_fetch.mjs` — One-off Dhan API v2 test with credentials
- `angular_coverage_study_remote.py` — Duplicate of `gann-visualizer/backend/study_tool/angular_coverage_study.py`
- `intersection_detector_remote.py` — Duplicate of `gann-visualizer/backend/study_tool/intersection_detector.py`
- `pivot_detector_remote.py` — Duplicate of `gann-visualizer/backend/study_tool/pivot_detector.py`
- `backend_scale_check.py` — Throwaway debug script
- `extract_log.py` — Throwaway log extraction with hardcoded old paths
- `setup_env.ps1` — One-liner pip install
- `angle_diff.txt` — Stale git diff artifact
- `c:DevGannTestingangle_diff2.txt` — Malformed filename from path error
- `package.json` (root) — Root-level npm config, unused
- `package-lock.json` (root) — Lockfile for root package.json

### 2.2 `tools/` directory
All 3 files — Dhan API one-off scripts with embedded credentials, not used by backend:
- `dhan-test-script.py`
- `dhan_auth.py`
- `update_token.py`

### 2.3 Debug/stale files
- `gann-visualizer/debug.txt` — Stale debug output from extract_log.py
- `gann-visualizer/backend/c:DevGannTestinggann-visualizerbackendstudy_toolunified_state_machine.py` — Malformed filename

### 2.4 Backend orphaned scripts (18 files)
None are imported or referenced by any active module:
- `debug_cross.py`
- `debug_lines.py`
- `debug_sweep.py`
- `fix.py`
- `fix_indent.py`
- `test_agg.py`
- `test_bars.py`
- `test_debug.py`
- `test_diwali.py`
- `test_negative_bars.py`
- `test_scenario.py`
- `test_script.py`
- `test_script2.py`
- `test_script3.py`
- `test_sm.py`
- `test_yf.py`
- `compare_csv.py`
- `inspect_master.py`

### 2.5 Frontend eslint output files
- `eslint_err.json`
- `eslint_final.json`
- `eslint_full.json`
- `eslint_others.json`
- `eslint_output.json`

### 2.6 Log files to remove
- `gann-visualizer/backend/logs/clean.log`
- `gann-visualizer/backend/logs/clean2.log`
- `gann-visualizer/backend/logs/simulation_run_20260319_122732.log`
- `gann-visualizer/backend/logs/simulation_run_20260319_122744.log`
- `gann-visualizer/backend/logs/target_progression_validation.log`
- `gann-visualizer/backend/logs/target_progression_events.txt`
- `gann-visualizer/backend/logs/event_ledger.csv` (unreferenced)
- `gann-visualizer/backend/logs/state_matrix.csv` (unreferenced)
- `gann-visualizer/backend/logs/study_debug/` (all contents — unreferenced debug)
- `gann-visualizer/backend/logs/analysis/` (all contents — orphaned hypothesis outputs)
- `gann-visualizer/logs/localhost-*.log` (11 files)
- `gann-visualizer/sim_output.log`
- All `.~lock.*` files

### 2.7 Cache directories to remove
All `__pycache__/` and `.pytest_cache/` directories recursively.

### 2.8 Aider cache files
- `.aider.chat.history.md`
- `.aider.input.history`
- `.aider.tags.cache.v4`

---

## 3. Files to Keep

| File/Dir | Reason |
|----------|--------|
| `restart_servers.ps1`, `restart_servers.sh` | Dev utilities |
| `strategy_params.json` | Used by backend `main.py` |
| `gann-visualizer/frontend/dist/` | Build artifact (regenerated on build) |
| `gann-visualizer/frontend/public/` | Actively served static assets |
| `gann-visualizer/frontend/src/` | Active frontend source |
| Active backend logs (after move to `logs/backend/`): | |
| — `backend_session_*.log` | Actively generated |
| — `replay_trace.log` | Actively generated |
| — `simulation_trace.log` | Actively generated |
| — `simulation_run.log` | Actively generated |
| — `simulation_events.csv` | Actively generated |
| — `intersections_*.csv` | Actively generated |

---

## 4. Implementation Steps

### Phase 1: Pre-cleanup commit
1. Commit current state so cleanup is reversible

### Phase 2: Remove stale files
2. Remove root-level stale scripts (13 files)
3. Remove `tools/` directory (3 files)
4. Remove backend orphaned scripts (18 files)
5. Remove frontend eslint output files (5 files)
6. Remove malformed files (`debug.txt`, malformed backend filename)
7. Remove all stale log files
8. Remove all `__pycache__/` and `.pytest_cache/` directories
9. Remove aider cache files

### Phase 3: Move & reorganize
10. Move `CommoditiesCourse/` → `docs/research/`
11. Move scattered docs into `docs/` subfolders (architecture/, api/, strategy/)
12. Move `code_references/` → `gann-visualizer/code_references/`

### Phase 4: Update path references
13. Update `main.py`: `backend/logs/` → `logs/backend/`
14. Update `run_simulation.py`: `backend/logs/` → `logs/backend/`
15. Update `angular_coverage_study.py`: `backend/logs/study_debug/` → `logs/backend/study_debug/`
16. Update `unified_state_machine.py`: `backend/logs/` → `logs/backend/`

### Phase 5: Update `.gitignore`
17. Ensure `logs/`, `__pycache__/`, `.pytest_cache/`, `*.pyc`, `.~lock*`, `.aider*` are all ignored

### Phase 6: Verify
18. Verify backend starts without errors
19. Verify active logs are being written to new location

---

## 5. Port Discrepancy Note

`restart_servers.ps1` uses port 8001 for backend; `restart_servers.sh` uses port 8005. This discrepancy should be investigated separately — not in this cleanup pass.

---

## 6. Spec Self-Review

- [ ] All removals are confirmed stale (no active imports)
- [ ] Path updates are complete and correct
- [ ] Active logs are preserved and will be moved to new location
- [ ] `docs/` reorganization is clear and logical
- [ ] `.gitignore` covers all removed artifacts
