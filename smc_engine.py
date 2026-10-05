import pandas as pd
import numpy as np

# ── LOAD DATA ────────────────────────────────────────────
def load_data(symbol, timeframe):
    filepath = f"data/{symbol}_{timeframe}.csv"
    df = pd.read_csv(filepath, parse_dates=['time'])
    df = df.sort_values('time').reset_index(drop=True)
    print(f"Loaded {len(df):,} candles — {symbol} {timeframe}")
    return df

# ── MARKET STRUCTURE ─────────────────────────────────────
def detect_structure(df, swing_length=10):
    df = df.copy()
    df['swing_high'] = False
    df['swing_low']  = False
    df['trend']      = 'neutral'

    for i in range(swing_length, len(df) - swing_length):
        if df['high'].iloc[i] == df['high'].iloc[i-swing_length:i+swing_length+1].max():
            df.loc[i, 'swing_high'] = True
        if df['low'].iloc[i] == df['low'].iloc[i-swing_length:i+swing_length+1].min():
            df.loc[i, 'swing_low'] = True

    # Trend via swing structure
    last_high = None
    last_low  = None
    trend     = 'neutral'

    for i in range(len(df)):
        if df['swing_high'].iloc[i]:
            if last_high is not None:
                trend = 'bullish' if df['high'].iloc[i] > last_high else 'bearish'
            last_high = df['high'].iloc[i]

        if df['swing_low'].iloc[i]:
            if last_low is not None:
                if df['low'].iloc[i] > last_low:
                    trend = 'bullish'
                elif df['low'].iloc[i] < last_low:
                    trend = 'bearish'
            last_low = df['low'].iloc[i]

        df.loc[i, 'trend'] = trend

    return df

# ── ORDER BLOCKS ─────────────────────────────────────────
def detect_order_blocks(df):
    df = df.copy()
    df['ob_bullish'] = False
    df['ob_bearish'] = False

    for i in range(1, len(df) - 1):
        # Bullish OB — bearish candle followed by bullish engulfing
        if (df['close'].iloc[i]   < df['open'].iloc[i] and
            df['close'].iloc[i+1] > df['open'].iloc[i+1] and
            df['close'].iloc[i+1] > df['open'].iloc[i]):
            df.loc[i, 'ob_bullish'] = True

        # Bearish OB — bullish candle followed by bearish engulfing
        if (df['close'].iloc[i]   > df['open'].iloc[i] and
            df['close'].iloc[i+1] < df['open'].iloc[i+1] and
            df['close'].iloc[i+1] < df['open'].iloc[i]):
            df.loc[i, 'ob_bearish'] = True

    return df

# ── FAIR VALUE GAPS ───────────────────────────────────────
def detect_fvg(df):
    df = df.copy()
    df['fvg_bullish'] = False
    df['fvg_bearish'] = False

    for i in range(1, len(df) - 1):
        prev_high = df['high'].iloc[i-1]
        prev_low  = df['low'].iloc[i-1]
        next_high = df['high'].iloc[i+1]
        next_low  = df['low'].iloc[i+1]

        # Bullish FVG — gap up: previous high below next low
        if next_low > prev_high:
            df.loc[i, 'fvg_bullish'] = True

        # Bearish FVG — gap down: previous low above next high
        if next_high < prev_low:
            df.loc[i, 'fvg_bearish'] = True

    return df
    

# ── GENERATE SIGNALS ─────────────────────────────────────
# ── SESSION FILTER ────────────────────────────────────────
def is_valid_session(timestamp):
    hour = timestamp.hour
    # London session: 07:00 - 16:00 UTC
    # New York session: 13:00 - 21:00 UTC
    # Overlap is the most powerful: 13:00 - 16:00 UTC
    london   = 7 <= hour <= 16
    new_york = 13 <= hour <= 21
    return london or new_york

# ── CANDLE STRENGTH ───────────────────────────────────────
def candle_body_ratio(candle):
    body  = abs(candle['close'] - candle['open'])
    total = candle['high'] - candle['low']
    if total == 0:
        return 0
    return body / total

# ── GENERATE SIGNALS v3 ───────────────────────────────────
def generate_signals(df, lookback=2):
    df = df.copy()
    df['signal'] = 'none'

    for i in range(lookback, len(df)):
        candle = df.iloc[i]
        trend  = candle['trend']

        # Filter 1 — only trade valid sessions
        if not is_valid_session(candle['time']):
            continue

        # Filter 2 — candle must have strong body (>50% of range)
        if candle_body_ratio(candle) < 0.5:
            continue

        # Filter 3 — tight lookback (only 2 candles)
        window = df.iloc[i-lookback:i+1]

        recent_bull_ob  = window['ob_bullish'].any()
        recent_bear_ob  = window['ob_bearish'].any()
        recent_bull_fvg = window['fvg_bullish'].any()
        recent_bear_fvg = window['fvg_bearish'].any()

        # LONG signal
        if (trend == 'bullish' and
                recent_bull_ob and
                recent_bull_fvg):
            df.loc[i, 'signal'] = 'LONG'

        # SHORT signal
        elif (trend == 'bearish' and
                recent_bear_ob and
                recent_bear_fvg):
            df.loc[i, 'signal'] = 'SHORT'

    return df
# ── MAIN ─────────────────────────────────────────────────
def main():
    print("="*50)
    print("SMC SIGNAL ENGINE v2 — SESSION 3 FIX")
    print("="*50)

    df = load_data("EURUSD", "H1")

    print("\nDetecting market structure...")
    df = detect_structure(df)

    print("Detecting order blocks...")
    df = detect_order_blocks(df)

    print("Detecting fair value gaps...")
    df = detect_fvg(df)

    print("Generating signals...")
    df = generate_signals(df)

    # ── RESULTS ──────────────────────────────────────────
    signals   = df[df['signal'] != 'none']
    long_sig  = df[df['signal'] == 'LONG']
    short_sig = df[df['signal'] == 'SHORT']
    bull_fvgs = df[df['fvg_bullish'] == True]
    bear_fvgs = df[df['fvg_bearish'] == True]
    bull_obs  = df[df['ob_bullish']  == True]
    bear_obs  = df[df['ob_bearish']  == True]

    print(f"\n{'='*50}")
    print("RESULTS")
    print(f"{'='*50}")
    print(f"Total candles analysed : {len(df):,}")
    print(f"Swing highs detected   : {df['swing_high'].sum():,}")
    print(f"Swing lows detected    : {df['swing_low'].sum():,}")
    print(f"Bullish order blocks   : {len(bull_obs):,}")
    print(f"Bearish order blocks   : {len(bear_obs):,}")
    print(f"Bullish FVGs           : {len(bull_fvgs):,}")
    print(f"Bearish FVGs           : {len(bear_fvgs):,}")
    print(f"{'─'*50}")
    print(f"LONG signals           : {len(long_sig):,}")
    print(f"SHORT signals          : {len(short_sig):,}")
    print(f"TOTAL signals          : {len(signals):,}")
    print(f"Signal frequency       : {len(signals)/8:.0f} signals/year")

    print(f"\nLast 10 signals:")
    print(signals[['time','close','trend',
                   'signal']].tail(10).to_string(index=False))

    # Save full dataframe and signals
    df.to_csv("data/EURUSD_H1_analysed.csv", index=False)
    signals.to_csv("data/signals_EURUSD_H1.csv", index=False)
    print(f"\nFull analysis saved → data/EURUSD_H1_analysed.csv")
    print(f"Signals saved       → data/signals_EURUSD_H1.csv")
    print("\nSession 3 complete.")

if __name__ == "__main__":
    main()
