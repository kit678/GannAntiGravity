# Future Enhancements for Angular Price Coverage Strategy

The following features were implemented but reverted to keep the current baseline simple. They can be re-enabled in the future to enhance the visual analysis.

## 1. Confluence Heatmaps
**Goal**: Identify "Hot Zones" where angle lines from different fans intersect, indicating strong support/resistance confluence.

**Implementation Logic**:
- **Backend (`angle_engine.py`)**: Added `find_intersections(fan1, fan2)` method to calculate algebraic intersection ($y = mx + c$) of lines from two different active fans.
- **Study Logic (`angular_coverage_study.py`)**: Iterated through recent active fans (last 5) to find intersections valid in the near future.
- **Frontend**: Rendered intersections as small yellow circles (`marker` type) using `drawGenericMarker`.

## 2. Time-Price Squaring Lines
**Goal**: Project future time cycles based on the duration of the pivot pair formed.

**Implementation Logic**:
- **Backend (`angle_engine.py`)**: Added `generate_time_squaring_lines(fan)` method.
- **Logic**: Calculated cycle duration $T = T_{end} - T_{start}$. Projected vertical lines at $T_{end} + 1.0T, 2.0T, 3.0T$.
- **Frontend**: Rendered as dashed vertical gray lines (`vert_line` type) using `drawVerticalLine`.

## 3. Momentum-Based Opacity
**Goal**: Visually de-emphasize angle fans that are being opposed by strong price momentum (e.g., price crashing below a bullish fan origin).

**Implementation Logic**:
- **Backend (`angle_engine.py`)**: Added `opacity` field to `AngleLine`.
- **Study Logic**: Checked if `Current Close < Fan Origin` (for bullish fans) or `Current Close > Fan Origin` (for bearish fans).
- **Effect**: If momentum opposed the fan, `opacity` was set to `0.4` (40%).
- **Frontend**: Mapped `opacity` to TradingView `transparency` option (0-100).
