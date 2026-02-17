# Angular Price Coverage Strategy (v4.0)

## Fan Definition
- A Fan is formed by exactly two pivots: one High, one Low.
- The Anchor is always the rightmost pivot (most recent in time).
- One pair = one fan (H4-L1 and L1-H4 are the same fan; anchor determines type).
- High Anchor: Angle formed at the Low pivot (Low, High, horizontal through Low).
- Low Anchor: Angle formed at the High pivot (High, Low, horizontal through High).

## Step 1: Detect All Pivots
Scan the entire historical dataset to detect all pivot Highs and Lows (e.g., 5 left bars, 5 right bars). This produces a complete, time-ordered list of confirmed pivots.

## Step 2: Unified Backward Traversal
Starting from the most recent pivot, iterate backwards through each pivot as a potential Anchor. For each Anchor, scan further back for valid Targets (opposite type).

### Rule 1: Anchor Validity
- High Anchor: Valid unless there exists a Higher High after it in time.
- Low Anchor: Valid only if Price >= Anchor price. If Price < Anchor, the anchor is breached/invalidated.

### Rule 2: Geometric Validity
- Target must be the opposite type to Anchor.
- Target must be below a High Anchor (or above a Low Anchor) for a meaningful angle.

### Rule 3: Clear Path
For a fan pair (Anchor A, Target T):
- High Anchor: No intermediate High between T and A (in time) may be higher than A.
- Low Anchor: No intermediate Low between T and A (in time) may be lower than A.
- If violated, the fan is geometrically blocked. Skip this target.

### Rule 4: Breach Check
After passing Rules 1-3, check if the Target has been breached by price action after the Anchor formed:
- Low Target: Breached if price fell below the Target level after Anchor time.
- High Target: Breached if price rose above the Target level after Anchor time.
- If breached, Invalidated. Continue scanning for next valid target (Waterfall).
- **Configurable `breach_mode`**:
  - `'wick'` (default): Uses candle high/low for breach detection.
  - `'close'`: Uses candle close price for breach detection.

### Rule 5: Successive Geometry
Targets from a single Anchor must be successively more extreme:
- High Anchor: Lows must be successively lower (each deeper than the previous).
- Low Anchor: Highs must be successively higher.
- If a target is not more extreme than the last accepted target, skip it.

### Rule 6: Global Fan Limit
Stop scanning once **3 total active fans** are found across all anchors. Fans can be any mix of High-anchor and Low-anchor types. This limit is configurable (default: 3).

## Step 3: Priority Labeling
Valid fans from each Anchor are labeled in order of discovery:
1. Primary - First valid target (nearest).
2. Secondary - Second valid target.
3. Tertiary - Third valid target (deepest/major).

Multiple Anchors can produce fans simultaneously. All valid fans are active at the same time.

## Dry Run Example
Time order: L1, H1, L2, H2, L3, H3, L4, H4, L5, H5, L6, H6, L7, H7
Price order: L1 < L2 < L4 < L3 < H1 < H3 < H2 < L7 < L5 < H7 < L6 < H5 < H6 < H4
Current Price: H2 < Price < L7

| Anchor | Target | R1 | R2 | R3 | R4 | R5 | Result |
|--------|--------|----|----|----|----|----|----|
| H7 | L7 | Pass | Pass | Pass | Breached | - | Invalid |
| H7 | L5 | Pass | Pass | Blocked H5>H7 | - | - | Blocked |
| L7 | - | Breached | - | - | - | - | Anchor Invalid |
| H6 | L6 | Pass | Pass | Pass | Breached | - | Invalid |
| H6 | L5 | Pass | Pass | Pass | Breached | - | Invalid |
| H6 | L4 | Pass | Pass | Blocked H4>H6 | - | - | Blocked |
| L6 | - | Breached | - | - | - | - | Anchor Invalid |
| H5 | L5 | Pass | Pass | Pass | Breached | - | Invalid |
| H5 | L4 | Pass | Pass | Blocked H4>H5 | - | - | Blocked |
| L5 | - | Breached | - | - | - | - | Anchor Invalid |
| H4 | L4 | Pass | Pass | Pass | Pass | 1st | Primary |
| H4 | L3 | Pass | Pass | Pass | Pass | L3>L4 | Skip |
| H4 | L2 | Pass | Pass | Pass | Pass | L2<L4 | Secondary |
| H4 | L1 | Pass | Pass | Pass | Pass | L1<L2 | Tertiary |
| L4 | H3 | Pass | Pass | Pass | Breached H4>H3 | - | Invalid |
| L4 | H2 | Pass | Pass | Pass | Breached H4>H2 | - | Invalid |

Active Fans: H4-L4 (Primary), H4-L2 (Secondary), H4-L1 (Tertiary)

## Implementation Pseudocode
```
total_fans = 0
for each pivot as Anchor (recent to old):
    if total_fans >= max_fans (Rule 6): STOP
    if Anchor is breached (Rule 1): skip
    for each earlier pivot as Target (recent to old):
        if total_fans >= max_fans (Rule 6): STOP
        if wrong type (Rule 2): skip
        if not geometrically valid (Rule 2): skip
        if path blocked (Rule 3): skip
        if target breached (Rule 4): skip (Waterfall)
        if not successively extreme (Rule 5): skip
        emit Fan(Anchor, Target, priority=total_fans)
        total_fans += 1
```
