# Gann & Geometry Standards
Since this project focuses on Gann-inspired geometric analysis, follow these mathematical and structural standards.

## 1. Coordinate Systems
- **Price/Time**: The backend operates on price and Unix seconds.
- **Ratios**: The frontend uses a fixed Price-to-Bar ratio (currently 5.5) for geometric rendering sanity.
- **Pivots**: Use the `PivotDetector` logic (left/right bar scanning) for all anchor identification.

## 2. Angular Price Coverage Strategy (v4.0)
When working on the `AngularPriceCoverageStudy`:
- **Rules 1-6**: Follow the "Unified Backward Traversal" exactly as documented in `docs/angular_coverage_strategy_v4.md`.
- **Anchor-Type Breathing**: Breach direction is fixed by anchor type (Low anchor = Upward breach tracking; High anchor = Downward).
- **Terminology**: Use **"Division Line Reversal"** instead of "Breach Failure".

## 3. Verification
- All new logic or modules MUST have corresponding unit tests in `study_tool/tests/` or `backend/tests/`.
- Run tests using `python -m pytest` before claiming a task is complete.
