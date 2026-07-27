"""Does the RSI trendline break carry any edge over a time-shifted control?

Holds everything constant -- SMA200 filter, swing stop, R grid, max hold --
and moves ONLY the entry bar. If shifted entries score the same, the break
moment is not doing work and no amount of trendline tuning will change that.

Result on the runs available (2026-07-27): real 0.4517 sits inside the
placebo spread 0.4076-0.4981, and +13 / +23 bar shifts beat it outright.

Gate any future strategy variant on this before trusting its win rate.

Usage:
    python gann-visualizer/backend/scripts/placebo_test_rsi.py
"""

import sys, os, glob
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pandas as pd
from analysis.rsi_pivots import GeometryParams, compute_rsi_series
from analysis.rsi_line_policy import AdjacentAnchorPolicy, WalkBackAnchorPolicy
from analysis.rsi_sweep import run_causal_sweep
from analysis.signal_trade_simulator import CandleSignal, simulate_trade_grid

R_GRID=[1.0,1.5,2.0,2.5,3.0]; HOLD=40; LB=20; BUF=0.0005

def build(c, bars_sides):
    sma=c['close'].rolling(200,min_periods=200).mean(); N=len(c); out=[]
    for bar,side in bars_sides:
        if bar>=N-1 or pd.isna(sma.iloc[bar]): continue
        cl=float(c['close'].iloc[bar])
        if not ((side=='LONG' and cl>sma.iloc[bar]) or (side=='SHORT' and cl<sma.iloc[bar])): continue
        lo=max(0,bar-LB)
        stop=float(c['low'].iloc[lo:bar+1].min())*(1-BUF) if side=='LONG' else float(c['high'].iloc[lo:bar+1].max())*(1+BUF)
        if (side=='LONG' and stop>=cl) or (side=='SHORT' and stop<=cl): continue
        out.append(CandleSignal(bar,side,cl,stop,str(bar)))
    return out

def run(c, sigs):
    if not sigs: return None
    return simulate_trade_grid(candles=c,signals=sigs,r_values=R_GRID,max_hold_bars=HOLD)['best']

agg={}
def add(k,b):
    if not b: return
    d=agg.setdefault(k,{'n':0,'w':0,'net':0.0})
    d['n']+=b['n']; d['w']+=round(b['win_rate']*b['n']); d['net']+=b['net_pnl_total']

for f in sorted(glob.glob('logs/backend/runs/*/*/*/candles.csv')):
    try: c=pd.read_csv(f).reset_index(drop=True)
    except Exception: continue
    if len(c)<300 or not {'open','high','low','close'}<=set(c.columns): continue
    c['bar_index']=c.index
    rsi=compute_rsi_series(c['close'],14)
    res=run_causal_sweep(rsi, AdjacentAnchorPolicy(), GeometryParams(min_swing=8.0,min_length=5))
    real=[(s.bar_index,s.side) for s in res.signals]
    if not real: continue
    add('REAL rsi-break', run(c, build(c, real)))
    for off in (7,13,23,37):
        add('placebo +%d bars'%off, run(c, build(c, [(b+off,s) for b,s in real if b+off < len(c)-1])))
    # every Nth bar, direction chosen purely by the trend filter
    sma=c['close'].rolling(200,min_periods=200).mean()
    every=[]
    for b in range(200,len(c)-1,25):
        if pd.isna(sma.iloc[b]): continue
        every.append((b,'LONG' if c['close'].iloc[b]>sma.iloc[b] else 'SHORT'))
    add('trend-filter only', run(c, build(c, every)))

print('%-22s %6s %6s %9s %12s' % ('entry rule','n','wins','win_rate','net_pnl'))
print('-'*60)
for k in ['REAL rsi-break','placebo +7 bars','placebo +13 bars','placebo +23 bars','placebo +37 bars','trend-filter only']:
    if k in agg:
        d=agg[k]; print('%-22s %6d %6d %9.4f %12.1f' % (k,d['n'],d['w'],d['w']/d['n'],d['net']))
