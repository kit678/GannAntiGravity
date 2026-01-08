# Angular Price Coverage Strategy - Quick Reference Card

> Print this for quick reference during trading sessions

---

## 🎯 SETUP CHECKLIST

```
□ 1. Identify pivots (Swing High-Low, X=10 bars)
□ 2. Assess trend (last 3-4 candles from pivot)
□ 3. Determine which pivot formed FIRST:
      RISING: High A first, Low B second → H through A, angles DOWN from A
      FALLING: Low B first, High A second → H through B, angles UP from B
□ 4. Calculate angle θ at FIRST pivot vertex
□ 5. Plot angle lines: 7/8θ, 3/4θ, 1/2θ, 1/4θ (ALL within θ)
□ 6. Plot horizontal target: vertical at SECOND pivot × 1/2θ line = Point Y
```

---

## 📐 ANGLE CALCULATION

| Level | Formula | Color |
|-------|---------|-------|
| **7/8** | θ - (θ/8) | 🔵 Blue Dashed |
| **3/4** | θ - (θ/4) | 🟢 Green |
| **1/2** | θ - (θ/2) | 🟠 Orange |
| **1/4** | θ - (3θ/4) | 🔴 Red |

---

## ✅ ENTRY RULES

### BULLISH ENTRY
```
1. Price at angle from BELOW
2. First candle touches/breaches
3. Wait: 2+ HIGHER CLOSES
4. Enter on 2nd confirmation close
5. Stop: Below breached angle
6. Target: Next angle above
```

### BEARISH ENTRY
```
1. Price at angle from ABOVE
2. First candle touches/breaches
3. Wait: 2+ LOWER CLOSES
4. Enter on 2nd confirmation close
5. Stop: Above breached angle
6. Target: Next angle below
```

---

## 🚪 EXIT OPTIONS

| Option | Rules |
|--------|-------|
| **Fixed** | 100% exit at next angle |
| **Trailing** | Move stop to previous angle |
| **Hybrid** | 50% at target, trail rest |

**Always exit on strong reaction** (doji, long wick)

---

## ⚠️ SPECIAL RULES

| Situation | Rule |
|-----------|------|
| After 1/2 breach | Target = Horizontal line at Point Y |
| 1/4 reacts first | Horizontal target INVALID |
| After Horizontal breach | Target = FIRST pivot's price (Full θ coverage) |
| 1/16 reaction | Strong counter-momentum |
| Multiple pairs | INNERMOST takes precedence |
| Pivot breached | Recalculate with new pivot |

**HORIZONTAL TARGET DERIVATION:**
```
1. Draw vertical line at SECOND pivot's time
2. Find intersection with 1/2θ line = Point Y
3. Horizontal through Y = TARGET
```

---

## 📊 MULTI-TIMEFRAME

| TF | Purpose |
|----|---------|
| Higher (1H/4H/D) | Direction, major pivots |
| Current (15m/1H) | Angle monitoring, confirmation |
| Lower (1m/5m) | Entry timing |

**Entry Protocol**: Higher shows approach → Current shows breach → Lower for entry

---

## 🔴 COMMON MISTAKES TO AVOID

- ❌ Entering on first candle breach (wait for 2+ confirms)
- ❌ Ignoring lower timeframe for entry precision
- ❌ Using outer angle as primary (always use innermost)
- ❌ Forgetting horizontal target after 1/2 breach
- ❌ Not placing stop loss

---

## 💡 CONFLUENCE = HIGHER PROBABILITY

When these align = STRONG level:
- Multiple angle lines converge
- Higher TF + Current TF angles align
- Volume spike on breach
- RSI divergence at angle

---

*Document: ANGULAR_PRICE_COVERAGE_STRATEGY.md | v1.0 | 2026-01-04*
