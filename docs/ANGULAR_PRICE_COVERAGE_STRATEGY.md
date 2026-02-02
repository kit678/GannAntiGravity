# Angular Price Coverage Strategy

> **A Gann-Inspired Geometric Trading System**
> 
> Document Version: 1.0  
> Last Updated: 2026-01-04  
> Status: Initial Documentation - Pending Backtesting

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Core Philosophy](#core-philosophy)
3. [Prerequisites & Tools](#prerequisites--tools)
4. [Setup Phase](#setup-phase)
5. [Angle Calculation](#angle-calculation)
6. [Trading Rules](#trading-rules)
7. [Entry Rules](#entry-rules)
8. [Exit Rules](#exit-rules)
9. [Pivot Management](#pivot-management)
10. [Multi-Timeframe Analysis](#multi-timeframe-analysis)
11. [Confluence Factors](#confluence-factors)
12. [Known Challenges](#known-challenges)
13. [Backtesting Priorities](#backtesting-priorities)
14. [Appendix: Quick Reference](#appendix-quick-reference)

---

## Executive Summary

The **Angular Price Coverage Strategy** is a geometric trading approach that measures price movements in terms of **angular distance** rather than just vertical price distance. 

### Key Insight
When price moves from a low pivot to a high pivot (or vice versa), it creates an angular relationship with the time axis. When price reverses, it tends to "retrace" this angular distance, pausing at predictable fractional levels (1/8th divisions).

### Trading Edge
These fractional angle levels act as **dynamic support and resistance** that move with time, offering high-probability reaction zones for entries and exits.

---

## Core Philosophy

### Traditional View vs Angular View

| Traditional | Angular (This Strategy) |
|-------------|------------------------|
| "Price moved 100 points down" | "Price covered 84.79° of angular distance" |
| Static horizontal S/R levels | Dynamic diagonal S/R levels |
| Price targets are fixed | Targets evolve with time |

### The Angular Coverage Concept

```
                    HIGH ●
                        ╱│
                       ╱ │
                      ╱  │  ← When price falls, it "covers"
                     ╱   │     this angular distance
          Angle A   ╱    │
                   ╱     │
  ────────────────●──────────────── Time Axis (Horizontal)
                 LOW
                 
When price returns to LOW's price level (at any future time):
→ It has "covered" the entire Angle A
```

### Why 1/8th Divisions?

The strategy divides the reference angle into **8 equal parts** (based on Gann's octave theory). Price tends to respect these fractional levels:

- **7/8** (87.5%) - First resistance/support
- **3/4** (75%) - Secondary level
- **1/2** (50%) - Major midpoint
- **1/4** (25%) - Extended level

---

## Prerequisites & Tools

### Required Indicator
- **Swing High-Low Indicator**
  - Parameter: X bars on each side (recommended: X = 10)
  - Marks pivot highs (🔻) and pivot lows (🔺)
  - Pivot is confirmed only when X bars have passed on both sides

### Chart Requirements
- Ability to draw angle lines from specific points
- Ability to measure angle with horizontal
- Ability to draw horizontal lines at specific price levels

### Recommended Additions (for confluence)
- Volume indicator
- RSI or momentum oscillator
- Multiple timeframe charts

---

## Setup Phase

### Step 1: Identify Pivots

Using the Swing High-Low Indicator, identify:
- All confirmed pivot highs (price peaks)
- All confirmed pivot lows (price troughs)

### Step 2: Assess Market Direction

Look at the **last 3-4 candles** from the most recent pivot:

| Observation | Assessment |
|-------------|------------|
| Candles rising from a pivot low | **BULLISH** - market trending up |
| Candles falling from a pivot high | **BEARISH** - market trending down |

### Step 3: Select Pivot Pair

#### For BULLISH Setup (Rising from Low)

1. **Reference Low Pivot**: The swing low where the current upward move started
2. **Reference High Pivot**: The **next HIGHEST pivot** that is ABOVE the current price
3. **Ignore**: Any pivot highs between them that are BELOW current price

```
Example:
                    A ● ← This is our HIGH (above current price)
                   ╱
                  ╱    ○ ← Ignore this (below current price)
                 ╱
    Current →   ╱
    Price      ╱
              ╱
             ● B ← This is our LOW (where uptrend started)
```

#### For BEARISH Setup (Falling from High)

1. **Reference High Pivot**: The swing high where the current downward move started
2. **Reference Low Pivot**: The **next LOWEST pivot** that is BELOW the current price
3. **Ignore**: Any pivot lows between them that are ABOVE current price

---

## Angle Calculation

### Critical: Which Pivot Formed First?

The geometric setup depends on the **temporal order** of pivots:

| Scenario | First Pivot | Second Pivot | H Placement | Angles Radiate |
|----------|-------------|--------------|-------------|----------------|
| **Rising from Low** | HIGH (A) | LOW (B) | Through A | DOWN from A |
| **Falling from High** | LOW (B) | HIGH (A) | Through B | UP from B |

### Step 1: Draw Reference Horizontal (H)

**H is ALWAYS drawn through the FIRST pivot** (the one that formed earlier in time):

- **Scenario 1 (Rising)**: A formed first → H through A
- **Scenario 2 (Falling)**: B formed first → H through B

### Step 2: Calculate Primary Angle (θ)

The full angle θ is measured at the **vertex of the first pivot**:

- **Scenario 1**: θ = angle at A, between H and line AB
- **Scenario 2**: θ = angle at B, between H and line BA

**All angle divisions (7/8θ, 3/4θ, 1/2θ, 1/4θ) must be WITHIN the full angle θ.**

### Step 3: Calculate Fractional Angles

Using the reduction sequence (doubling the reduction each time):

| Level | Calculation | Example (θ = 84.79°) |
|-------|-------------|------------------------|
| **7/8** | θ - (1/8 × θ) | 84.79 - 10.60 = **74.19°** |
| **3/4** | θ - (2/8 × θ) | 84.79 - 21.20 = **63.59°** |
| **1/2** | θ - (4/8 × θ) | 84.79 - 42.40 = **42.40°** |
| **1/4** | θ - (6/8 × θ) | 84.79 - 63.59 = **21.20°** |

### Step 4: Plot Angle Lines

From the **FIRST pivot**, draw lines radiating toward the **SECOND pivot's direction**:

- **Scenario 1**: From A, lines radiate DOWNWARD
- **Scenario 2**: From B, lines radiate UPWARD

| Angle | Suggested Color | Line Style |
|-------|-----------------|------------|
| 7/8 (closest to full θ) | Blue | Dashed |
| 3/4 | Green | Solid |
| 1/2 | Orange | Solid |
| 1/4 (closest to H) | Red/Pink | Solid |

### Step 5: Plot Horizontal Target

The horizontal target is derived as follows:

1. Draw a **vertical line** at the time (x-position) of the **SECOND pivot**
2. Find point **Y** where this vertical intersects the **1/2 angle line**
3. Draw a **horizontal line** through Y → this is the **HORIZONTAL TARGET**

**This horizontal becomes the target AFTER the 1/2 angle is breached.**

### Step 6: The 1/4 Angle Exception

> **UNLESS** the price reacts from the 1/4 angle BEFORE reaching the horizontal target line, in which case the horizontal target is **INVALIDATED**.

**Note**: When the full angle θ is small, the 1/4 angle line is often BELOW the horizontal target line, making it less likely to invalidate the target.

### Step 7: Full Angle Coverage (Michael Jenkins Secret Angle Method)

After the horizontal target is breached:
- **Final target** = the price level of the **FIRST pivot** (full θ coverage)
- This is the pivot where angles radiate FROM
- **Scenario 1 (Rising)**: Target = A's price (the high where angles radiate down from)
- **Scenario 2 (Falling)**: Target = B's price (the low where angles radiate up from)
- This completes the full angular cycle



---

## Trading Rules

### Rule 1: First Target After Reversal

When price starts moving from a pivot:
- **First target** = 7/8 angle (1/8 reduction line)
- Watch for **reaction** at this level

### Rule 2: Early Weakness Signal

If price reacts at **1/16th angle** (half of 1/8):
- Implies **strong counter-momentum**
- Consider the reversal may fail

### Rule 3: Breach Confirmation

A single candle closing beyond an angle is **NOT** sufficient confirmation.

**Required for confirmation**:
- Minimum **2 successive closes** in the direction of the breach
- Higher closes = bullish confirmation
- Lower closes = bearish confirmation

### Rule 4: Angle Role Reversal

Once an angle is breached and confirmed:
- **Resistance becomes Support** (in uptrend)
- **Support becomes Resistance** (in downtrend)

Price often returns to test the breached angle before continuing.

### Rule 5: Target After 1/2 Angle

After breaching the 1/2 angle:
- **Primary Target**: Horizontal line (at 1/2 angle ∩ vertical at pivot time)
- **Exception**: If 1/4 angle reacts FIRST → horizontal target is **invalidated**

### Rule 6: Angle Reactions

Price reactions are visible as:
- Long upper/lower wicks
- Doji candles
- Spinning tops
- Reversal patterns

---

## Entry Rules

### Bullish Entry

```
TRIGGER:
1. Price approaching angle line from BELOW
2. First candle touches or breaches the angle
3. Wait for CONFIRMATION: 2+ successive higher closes

ENTRY POINT:
→ On the CLOSE of the 2nd confirmation candle
→ OR: Drop to lower timeframe for earlier entry

TARGET:
→ Next angle level above
→ OR: Horizontal target (if applicable after 1/2)

STOP LOSS:
→ Below the low of the confirmation candles
→ OR: Below the angle line that was just breached
```

### Bearish Entry

```
TRIGGER:
1. Price approaching angle line from ABOVE
2. First candle touches or breaches the angle
3. Wait for CONFIRMATION: 2+ successive lower closes

ENTRY POINT:
→ On the CLOSE of the 2nd confirmation candle
→ OR: Drop to lower timeframe for earlier entry

TARGET:
→ Next angle level below

STOP LOSS:
→ Above the high of the confirmation candles
→ OR: Above the angle line that was just breached
```

---

## Exit Rules

### Option 1: Fixed Target Exit

- Exit 100% when price reaches next angle level
- **Pros**: Simple, mechanical
- **Cons**: May miss larger moves

### Option 2: Trailing Stop Exit

- Move stop to previous angle after each confirmed breach
- **Pros**: Captures extended moves
- **Cons**: May give back profits on reversals

### Option 3: Partial Exit (Recommended)

1. Exit **50%** at first target angle
2. Move stop to **breakeven**
3. Trail remaining **50%** using angle levels as stops

### Reaction-Based Exit

If you observe strong reaction at target (doji, long wick, reversal pattern):
→ Consider full exit regardless of which option you're using

---

## Pivot Management

### Terminology: Outer Container vs Inner Sequence

Understanding the distinction between **Outer** and **Inner** pivots is critical:

| Term | Definition |
|------|------------|
| **Outer Container** | The pair of pivots representing the **largest relevant swing** that bounds the current price action. This defines the "full theta" (θ) against which all angular coverage is measured. |
| **Inner Sequence** | A series of intermediate pivot pairs formed **within** the Outer Container's range. These create smaller nested fans that track the progression of price toward the Outer boundary. |

**Key Insight:** The Outer Container is **persistent** — it remains the reference frame until its boundary is breached. Inner pivots are **dynamic** — they evolve as price progresses and new pivots form.

---

### Bearish Retracement Scenario (Price Falling After a Major High)

This scenario applies when price has made a significant **High** and is now retracing downward.

#### Step 1: Identify the Outer Container

```
                    B ● ← OUTER HIGH: Highest High since A
                   /|
                  / |
                 /  |
                /   |     Price is falling from B toward A
               /    |
              /     |
             /      |
            /       |
   ────────●────────┴─────────────────── Horizontal (H) through A
          A
    OUTER LOW: Nearest historical Low BELOW current price
```

1. **Outer Low (A):** Find the nearest historical **Low** that is **below** the current price.
2. **Outer High (B):** Find the **Highest High** that occurred **between A and Now** (NOT the nearest high — the HIGHEST).
3. **Outer Angle (θ):** The angle formed by pivot B, pivot A, and the horizontal through A (denoted as ∠BAH).

**This Outer Container remains the constant reference frame** as long as price stays above A.

#### Step 2: Track the Inner Sequence

As price falls from B, **new pivot Lows** form (E, F, G, etc.). Each new Low creates an **Inner Fan** with the most recent relevant High:

```
        B ●
         /|\
        / | \
       /  |  \     C ●  ← Inner High (lower than B)
      /   |   \    /|
     /    |    \  / |
    /     |     \/  |    D ● ← Another Inner High
   /      |     /\  |    /|
  /       |    /  \ |   / |
 /        |   /    \|  /  |
●─────────┼──●──────●─●───●─── Time
A         E         F   (Current Low)

Inner Fans (nested within Outer):
  - Fan 1: D → F (most recent)
  - Fan 2: C → F (next level up)
  - Fan 3: B → F (connects to Outer High)
```

#### Step 3: Sequential Promotion of Inner Pivots

As price continues falling and breaches horizontal levels:

| Event | Action |
|-------|--------|
| Price breaches horizontal through D | Look retrospectively for the next Inner High **above D** (which is C). Draw fan from C → current Low. |
| Price breaches horizontal through C | Look retrospectively for the next Inner High **above C** (which is B). Draw fan from B → current Low. |
| Price breaches horizontal through A (Outer Low) | **Recursive Extension:** Search for a new Outer Low below A. B remains the Outer High until a higher High forms. |

##### ⚠️ Ascending Staircase Requirement (CRITICAL)

**Inner Highs must form an ASCENDING sequence toward the Outer High.** This means:

1. **Only consider Highs that are HIGHER than previously identified Inner Highs**
2. **Ignore any intermediate High that is LOWER than a previously identified High in the sequence**
3. **The sequence must "climb" from the Inner Anchor (recent Low) UP to the Outer High**

**Example - Correct Selection:**
```
Price Levels:
  B (Outer High) = 24600  ← HIGHEST
  X (Intermediate) = 24400  ← SKIPPED (lower than C)
  C (Next High) = 24500  ← INCLUDED (ascending from D)
  D (First High) = 24200  ← INCLUDED (first above current price)
  Current Price = 24100
  
Valid Inner Sequence: D → C → B (ascending)
Invalid: D → X → C (X is lower than C, breaks ascending order)
```

**Rationale:** When price rises from a Low and reaches the horizontal at D, it means D's "angular coverage" is complete. The next relevant resistance is the NEXT HIGHER High (C), not a lower intermediate High (X). Since X is lower than C, it was already "covered" when price passed through it to reach C's level.

#### Step 4: Recursive Extension of Outer Container

When the **Outer Low (A) is breached**:

1. The system searches retrospectively for the **next historical Low below A** — call it A'.
2. A' becomes the new Outer Low.
3. B remains the Outer High (unless price has since made a higher high).
4. The new Outer Angle is ∠BA'H (horizontal through A').
5. The Inner Sequence continues to be tracked within this extended container.

---

### Bullish Retracement Scenario (Price Rising After a Major Low)

This is the **mirror image** of the bearish scenario, applying when price has made a significant **Low** and is now retracing upward.

#### Step 1: Identify the Outer Container

```
    OUTER HIGH: Nearest historical High ABOVE current price
   ────────●────────┬─────────────────── Horizontal (H) through A
          A         |
            \       |
             \      |
              \     |     Price is rising from B toward A
               \    |
                \   |
                 \  |
                  \ |
                   \|
                    ● B ← OUTER LOW: Lowest Low since A
```

1. **Outer High (A):** Find the nearest historical **High** that is **above** the current price.
2. **Outer Low (B):** Find the **Lowest Low** that occurred **between A and Now** (NOT the nearest low — the LOWEST).
3. **Outer Angle (θ):** The angle formed by pivot B, pivot A, and the horizontal through A (denoted as ∠BAH).

**This Outer Container remains the constant reference frame** as long as price stays below A.

#### Step 2: Track the Inner Sequence

As price rises from B, **new pivot Highs** form (E, F, G, etc.). Each new High creates an **Inner Fan** with the most recent relevant Low:

```
●─────────┼──●──────●─●───●─── Time
B         E         F   (Current High)
 \        |   \    /|  \  |
  \       |    \  / |   \ |
   \      |     \/  |    \|
    \     |     /\  |    D ● ← Inner Low (higher than B)
     \    |    /  \ |    \|
      \   |   /    \|     |
       \  |  /     C ●  ← Another Inner Low
        \ | /       |
         \|/        |
          ●         |
          B ← OUTER LOW
```

Inner Fans (nested within Outer):
  - Fan 1: D → F (most recent)
  - Fan 2: C → F (next level down)
  - Fan 3: B → F (connects to Outer Low)

#### Step 3: Sequential Promotion of Inner Pivots

As price continues rising and breaches horizontal levels:

| Event | Action |
|-------|--------|
| Price breaches horizontal through D | Look retrospectively for the next Inner Low **below D** (which is C). Draw fan from C → current High. |
| Price breaches horizontal through C | Look retrospectively for the next Inner Low **below C** (which is B). Draw fan from B → current High. |
| Price breaches horizontal through A (Outer High) | **Recursive Extension:** Search for a new Outer High above A. B remains the Outer Low until a lower Low forms. |

##### ⚠️ Descending Staircase Requirement (CRITICAL)

**Inner Lows must form a DESCENDING sequence toward the Outer Low.** This means:

1. **Only consider Lows that are LOWER than previously identified Inner Lows**
2. **Ignore any intermediate Low that is HIGHER than a previously identified Low in the sequence**
3. **The sequence must "descend" from the Inner Anchor (recent High) DOWN to the Outer Low**

**Example - Correct Selection:**
```
Price Levels:
  Current Price = 24100
  D (First Low) = 24000  ← INCLUDED (first below current price)
  X (Intermediate) = 23800  ← SKIPPED (higher than C)
  C (Next Low) = 23700  ← INCLUDED (descending from D)
  B (Outer Low) = 23500  ← LOWEST
  
Valid Inner Sequence: D → C → B (descending)
Invalid: D → X → C (X is higher than C, breaks descending order)
```

**Rationale:** When price falls from a High and reaches the horizontal at D, it means D's "angular support" is being tested. The next relevant support is the NEXT LOWER Low (C), not a higher intermediate Low (X). Since X is higher than C, it was already "tested" when price passed through it to reach C's level.

#### Step 4: Recursive Extension of Outer Container

When the **Outer High (A) is breached**:

1. The system searches retrospectively for the **next historical High above A** — call it A'.
2. A' becomes the new Outer High.
3. B remains the Outer Low (unless price has since made a lower low).
4. The new Outer Angle is ∠BA'H (horizontal through A').
5. The Inner Sequence continues to be tracked within this extended container.

---

### Summary: The Hierarchical Pivot Framework

| Concept | Bearish Scenario | Bullish Scenario |
|---------|------------------|------------------|
| **Outer Low** | Nearest Low BELOW current price | Lowest Low since Outer High |
| **Outer High** | Highest High since Outer Low | Nearest High ABOVE current price |
| **Inner Pivots** | Intermediate Highs (D, C) forming fans with new Lows | Intermediate Lows (D, C) forming fans with new Highs |
| **Promotion Trigger** | Breach of Inner High's horizontal | Breach of Inner Low's horizontal |
| **Extension Trigger** | Breach of Outer Low (A) | Breach of Outer High (A) |
| **Angle Direction** | Fans radiate DOWN from Highs | Fans radiate UP from Lows |

### Key Principles

1. **Outer Container is Persistent:** It remains the reference frame until its boundary is breached.
2. **Inner Sequence is Dynamic:** It evolves as price progresses and new pivots form.
3. **Retrospective Identification:** When a horizontal is breached, look backwards to find the next relevant pivot.
4. **Multiple Fans Coexist:** At any point, there may be an Outer fan and one or more Inner fans — all remain relevant.
5. **Recursive Extension:** When an Outer boundary is breached, the container expands to the next historical extreme.

### Confluence Zones

When angle lines from **different pairs overlap**:
- Creates **stronger S/R zone**
- Higher probability of price reaction
- More confidence in entry decisions

Example: Inner 1/2θ aligns with Outer horizontal target → Strong level

### Using Outer Pairs for Context

| Outer Pair State | Implication |
|------------------|-------------|
| Price above outer horizontal target | Larger trend bias intact |
| Price rejected at outer angle | Larger trend may be exhausted |
| Inner + outer angles converge | High probability trade zone |
| Inner signals long but outer suggests resistance | Caution / reduced size |



---

## Multi-Timeframe Analysis

### Suggested Framework

| Timeframe | Purpose |
|-----------|---------|
| **Higher TF** (1H, 4H, Daily) | Identify major pivots, primary trend, major targets |
| **Current TF** (15min, 1H) | Monitor angle interactions, confirmation patterns |

### 6. Fan Invalidation Rules
**Concept:** Fans represent active market geometry. They become invalid when either their endpoint OR start point is breached.

**Rule 1 - Endpoint Breach (Anchor Invalidation):**
- **Bearish (High → Low):** If price drops **below** the Low (Anchor), the fan is invalidated.
- **Bullish (Low → High):** If price rises **above** the High (Anchor), the fan is invalidated.

**Rule 2 - Start Point Breach (Angle Traversal Complete):**
- **Bearish (High → Low):** If price rises **above** the High (Start), the angle has been completely traversed and the fan is obsolete.
- **Bullish (Low → High):** If price drops **below** the Low (Start), the angle has been completely traversed and the fan is obsolete.

**Implication:**
- No fan should be displayed if either its start or end pivot has been breached.
- A new fan will only be drawn when a *new* valid pivot structure forms.

## 7. Configuration Parameters
| **Lower TF** (1min, 5min) | Fine-tune entry, tighter stops |

### Entry Protocol

1. **Higher TF**: Confirms price approaching significant angle
2. **Current TF**: Shows first breach attempt
3. **Lower TF**: Provides precise entry point
4. **Trade Management**: Use Current TF

### Why Lower Timeframe Helps

**Problem**: On higher TF, the confirmation candle often closes near or beyond the next target, leaving no room for entry.

**Solution**: Lower TF has more candles between angle levels, allowing earlier entry after confirmation forms on the micro level.

---

## Confluence Factors

### Source 1: Multiple Pivot Pairs

When angle lines from different pivot pairs **converge**:
- Creates stronger S/R zone
- Higher probability of reaction
- More confidence in entry

### Source 2: Multiple Timeframes

When angle levels align across timeframes:
- Higher TF angle + Current TF angle at same price = Strong level

### Source 3: Additional Indicators (Suggested)

| Indicator | Usage |
|-----------|-------|
| **Volume** | Higher volume on breach = stronger signal |
| **RSI** | Divergence at angle = reversal confirmation |
| **VWAP** | Alignment with angles = added confluence |

---

## Momentum Determination

### Why Momentum Matters

**Key Rule**: Trade WITH momentum, not against it.
- Outer target gives the ULTIMATE destination
- Inner angles give the IMMEDIATE trading levels
- Momentum determines WHICH DIRECTION to trade NOW

### Momentum Indicators (Configurable)

| Indicator | Bullish Signal | Bearish Signal |
|-----------|----------------|----------------|
| **EMA 9/21** | EMA 9 > EMA 21 | EMA 9 < EMA 21 |
| **Price vs VWAP** | Price above VWAP | Price below VWAP |
| **RSI Direction** | RSI > 50 and rising | RSI < 50 and falling |
| **Last N Candles** | N higher closes | N lower closes |

### Momentum Confirmation Rule

Momentum is confirmed when **2 or more indicators agree** on direction.

| Agreement | Action |
|-----------|--------|
| 3-4 indicators agree | Strong momentum, trade with it |
| 2 indicators agree | Moderate, proceed with caution |
| Mixed signals | Wait for clarity |

---

## Reversal Confirmation

### Reversal Signals at Angle Levels

| Signal Type | Description |
|-------------|-------------|
| **Doji** | Small body, indecision |
| **Hammer/Inverted Hammer** | Long wick rejection |
| **Engulfing** | Current candle engulfs previous |
| **Long Wick** | Price rejected from level |
| **2+ Counter Closes** | 2+ closes against previous direction |

### Additional Reversal Confluence

| Indicator | Reversal Signal |
|-----------|-----------------|
| **RSI Divergence** | Price makes new extreme, RSI doesn't |
| **Volume Spike** | Higher than average volume on reversal candle |
| **VWAP Rejection** | Price rejects from VWAP area |

### Reversal Confirmation Rule

Reversal is confirmed when:
1. Price is AT an angle level (inner)
2. **AND** candle pattern detected (doji, hammer, engulfing, long wick)
3. **AND** 2+ closes in new direction
4. **OPTIONAL**: RSI divergence or volume spike for extra confidence

---

## Trading Direction Logic

### Priority Order

1. **Assess current momentum** (using indicators above)
2. **Trade inner angles** in the direction of momentum
3. **Watch for reversal** at inner support/resistance
4. **Only reverse direction** when reversal confirmation is met
5. **Outer target** is the ultimate destination, not immediate signal

### Example Scenario

| Factor | State |
|--------|-------|
| Inner pair | B-A (Scenario 2, falling) |
| Outer pair | I-E (Scenario 1, target = I's price) |
| Current momentum | BEARISH (EMA 9 < 21, below VWAP) |

**Action**: 
- Trade SHORT at inner resistance angles
- Target inner support levels
- When inner support holds + reversal confirmed → switch to LONG
- Ultimate target = I's price (outer)



## Known Challenges

### Challenge 1: Entry Timing

**Problem**: Waiting for 2 candle confirmation often means price is already at or past the next target.

**Workaround**: Use lower timeframe for entry after higher TF shows initial breach.

### Challenge 2: Defining "Breach"

**Problem**: What exactly constitutes a breach? Close above? Wick above?

**Current Rule**: Use **close-based** breach (candle body closes beyond angle).

**To Test**: Wick-based breach vs close-based breach.

### Challenge 3: Timeframe Precedence

**Problem**: Which timeframe should take priority when they conflict?

**Status**: Needs backtesting and observation.

### Challenge 4: Pivot Confirmation Lag

**Problem**: Swing indicator needs X bars on each side, causing lag in pivot identification.

**Workaround**: Use "potential" pivots before full confirmation, but with caution.

---

## Backtesting Priorities

### Priority 1: Confirmation Rules
- Test: 1 vs 2 vs 3 candle confirmations
- Test: Close-based vs wick-based breach
- Measure: Win rate and average profit per variant

### Priority 2: Timeframe Optimization
- Test: Which TF works best as primary
- Test: MTF combinations (e.g., 1H + 5min)
- Measure: Entry timing improvement

### Priority 3: Additional Filters
- Test: Volume spike on breach
- Test: RSI/momentum confirmation
- Measure: Signal quality improvement

### Priority 4: Exit Optimization
- Test: Fixed target vs trailing vs hybrid
- Test: Partial exit percentages
- Measure: Profit factor and max drawdown

### Priority 5: Confluence Analysis
- Test: Inner angle only vs inner + outer
- Test: Angle convergence zones
- Measure: Win rate at confluence vs single angle

---

## Appendix: Quick Reference

### Angle Reduction Formula

```
For any reference angle θ:

7/8 angle = θ × (7/8) = θ - (θ/8)
3/4 angle = θ × (3/4) = θ - (θ/4)
1/2 angle = θ × (1/2) = θ - (θ/2)
1/4 angle = θ × (1/4) = θ - (3θ/4)
```

### Entry Checklist

- [ ] Pivot pair identified
- [ ] Angle lines plotted
- [ ] Price at angle level
- [ ] Reaction observed (wick/doji/reversal)
- [ ] 2+ confirmation closes
- [ ] Stop loss defined
- [ ] Target defined
- [ ] Position size calculated

### Color Coding Standard

| Angle | Color | Line Style |
|-------|-------|------------|
| Full angle (reference) | Gray | Dotted |
| 7/8 (87.5%) | Blue | Dashed |
| 3/4 (75%) | Green | Solid |
| 1/2 (50%) | Orange | Solid |
| 1/4 (25%) | Red | Solid |
| Horizontal target | Yellow | Dashed |

### Pivot Selection Summary

**For Upward Move (from Low):**
```
LOW pivot → where uptrend started (BELOW current price)
HIGH pivot → next HIGHEST pivot (ABOVE current price)
```

**For Downward Move (from High):**
```
HIGH pivot → where downtrend started (ABOVE current price)
LOW pivot → next LOWEST pivot (BELOW current price)
```

---

## Document History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-01-04 | Initial documentation based on strategy walkthrough |

---

> **Next Steps**: 
> 1. Implement backtesting framework
> 2. Test confirmation rules
> 3. Validate on multiple instruments and timeframes
> 4. Refine entry/exit rules based on backtest results
