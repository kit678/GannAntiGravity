# Video analysis: "Price and Volume: Accumulation vs Distribution" (Dr David Paul)

Source: https://www.youtube.com/watch?v=MIorFQkrHI8 (Guy Levy / Markets Coach, 28 s Short).
Raw files: `raw/` (video, auto captions, info json). Frames: `frames/f_01.png` .. `f_28.png`
(1 per second), `frames/contact.png` (all frames on one sheet).

## Frame by frame

| Sec | What is on screen | What is said |
|---|---|---|
| 1-2 | Speaker. Caption "At the bottom of a market". | Sets the scene: a market bottom. |
| 3-4 | Chart: a downtrend of red candles, then a flat base, then one tall white candle. Volume bars shrink through the base, then one tall bar under the spike. | If price spikes up, volume should rise with it. |
| 5-6 | Same chart, title "Accumulation". | That is accumulation. |
| 7-9 | Speaker. Caption "Distribution". | Moves to the top of a market. |
| 10-12 | Chart "Distribution": an uptrend of white candles, a flat top, then red candles falling. | As price falls... |
| 12-13 | Volume bars under the falling red candles turn red and grow tall. | ...volume should rise. |
| 14-16 | A small white bounce candle after the drop. Its volume bar is short. | As price spikes up, volume should fall. |
| 17-22 | Speaker with a 2x2 grid. "Bullish": rally = price up, volume up. Drop = price down, volume down. | In a bullish market price and volume move together. |
| 23-26 | Grid fills "Bearish": drop = price down, volume up. Rally = price up, volume down. | In a bearish market drops come on heavy volume, rallies on light volume. |
| 27-28 | Outro card, "Follow @marketscoach". | None. |

## What the video actually gives us

One idea: compare the volume on up-moves with the volume on down-moves.

- Bullish (accumulation): up-moves carry more volume than down-moves.
- Bearish (distribution): down-moves carry more volume, and bounces come on light volume.

The video does **not** say: which timeframe, how to define a move, when to enter, where to
put a stop, or when to exit. Those are all our choices, so they need Kit's sign-off.

## Review of the first draft (2026-10-15)

The first draft got the idea only half right. Three mistakes:

1. **It dropped the location.** Both chart examples are about *where* the move happens.
   Accumulation is at a bottom: a downtrend, then a tight sideways base. Distribution is at
   a top: an uptrend, then a flat top. The draft fired signals anywhere.
2. **It turned "volume rising" into "leg average vs leg average".** The video shows volume
   *changing direction*. In the base, volume dries up bar after bar. Then one breakout
   candle comes with one huge volume bar. In the top, volume grows bar after bar as price
   falls. Then the bounce bar has a tiny volume bar.
3. **The 2x2 grid is a trend health check, not an entry.** Bullish needs both halves:
   rallies on rising volume AND drops on falling volume. Bearish is the mirror. The draft
   used only one half.

## Proposed rules v2 (not yet confirmed by Kit)

Setup A, accumulation (long):
1. Prior downtrend: price made lower lows into the base.
2. Base: N bars in a tight range. Volume shrinks through the decline and the base.
3. Trigger: a bar closes above the base high, and its volume is well above the base's
   average volume. Enter long next bar.

Setup B, distribution (short):
1. Prior uptrend, then a flat top (N bars in a tight range).
2. Price breaks below the top range, and volume rises on the falling bars.
3. Trigger: the first bounce after that drop comes on light volume, below the drop's
   volume. Enter short when the bounce ends.

Trend filter (the grid), optional on top of A or B:
- Bullish = up-moves carry more volume AND down-moves carry less. Bearish = the mirror.

Things the video never says, so Kit must choose: timeframe, base length N, how tight the
range is, how big the volume spike must be, stop, and exit.

## Second review (2026-10-15)

Rechecked at 2 frames per second (`frames/dist_seq.png`) and against the video's own
description. v2 still missed the main point and added things the video never shows.

1. **The core idea is one up-bar with two meanings.** The description says it plainly:
   same spike on the chart, opposite meaning. Price can't tell them apart. Volume can.
   v2 used trend shape (bottom vs top) as the decider. In the video, location is only the
   backdrop. The decider is the volume on the up-bar.
2. **The bounce is one small bar, and it is the signal itself.** In the distribution
   chart, the drop is just 3 red bars with volume growing each bar. The bounce is a single
   small white bar with a tiny volume bar. v2 said "first bounce" and "enter when the
   bounce ends". The video shows neither.
3. **v2 invented structure.** "Breaks below the top range", "N-bar base", "prior lower
   lows" are not said. They only appear as background in the drawings. The one visual
   detail worth keeping: in the accumulation chart, volume dries up bar by bar before the
   spike.

## Proposed rules v3 (not yet confirmed by Kit)

One trigger, one decider:

- **Trigger:** an up-bar (close above open, and above the prior bar's close).
- **Decider:** compare its volume to the few bars just before it.
  - Much higher than those bars, and those bars were quiet: **accumulation, go long**.
  - Lower than those bars, and those bars were falling on rising volume:
    **distribution, go short** (the bounce is not real buying).
  - Anything else: no trade.

Optional trend check (the 2x2 grid): bullish = rallies on rising volume AND drops on
falling volume. Bearish = the mirror. It can be used to only take longs in bullish
stretches and shorts in bearish ones.

Still Kit's choices: timeframe, how many bars "just before" means, how much higher is
"much higher", stop, and exit.
