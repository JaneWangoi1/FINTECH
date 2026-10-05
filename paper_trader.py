import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time
import os
from datetime import datetime
import pytz

# ── SETTINGS ─────────────────────────────────────────────
SETTINGS = {
    'login'          : 	61558462,
    'password'       : 'adbcjnM5$q',
    'server'         : 'mt5-demo01.pepperstone.com',
    'symbol'         : 'EURUSD',
    'risk_percent'   : 1.0,
    'rr_ratio'       : 2.0,
    'sl_pips'        : 15,
    'cooldown_hours' : 4,
    'max_trades_day' : 2,
    'log_file'       : 'data/paper_trades.csv',
    'check_interval' : 60   # seconds between checks
}

# ── CONNECT ──────────────────────────────────────────────
def connect():
    # Try to initialize without login first
    # Python connects through the already-open MT5 terminal
    if not mt5.initialize():
        print(f"MT5 initialize failed: {mt5.last_error()}")
        return False
    
    print(f"MT5 initialized successfully")
    
    # Check if already logged in through the terminal
    account = mt5.account_info()
    
    if account is not None:
        print(f"Already connected via terminal!")
        print(f"Account: {account.login}")
        print(f"Broker:  {account.company}")
        print(f"Balance: ${account.balance:,.2f}")
        return True
    
    # If not connected, try explicit login
    print("Terminal not logged in, attempting explicit login...")
    
    authorized = mt5.login(
        SETTINGS['login'],
        password = SETTINGS['password'],
        server   = SETTINGS['server']
    )
    
    if not authorized:
        print(f"Login failed: {mt5.last_error()}")
        print("\nTroubleshooting:")
        print("1. Make sure Pepperstone MT5 is open")
        print("2. Make sure you are logged in inside MT5")
        print("3. Make sure Algo Trading is enabled (green button)")
        mt5.shutdown()
        return False
    
    return True

# ── SESSION FILTER ────────────────────────────────────────
def is_valid_session():
    utc_now = datetime.utcnow()
    hour    = utc_now.hour
    london   = 7  <= hour <= 16
    new_york = 13 <= hour <= 21
    return london or new_york

# ── GET LATEST CANDLES ────────────────────────────────────
def get_candles(symbol, timeframe, count=100):
    mt5.symbol_select(symbol, True)
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None:
        return None
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.columns = ['time','open','high','low','close',
                  'volume','spread','real_volume']
    return df[['time','open','high','low','close','volume']]

# ── SMC DETECTION ────────────────────────────────────────
def detect_structure(df, swing_length=3):
    df = df.copy()
    df['swing_high'] = False
    df['swing_low']  = False
    df['trend']      = 'neutral'

    for i in range(swing_length, len(df) - swing_length):
        window = df['high'].iloc[i-swing_length:i+swing_length+1]
        if df['high'].iloc[i] == window.max():
            df.loc[i, 'swing_high'] = True
        window = df['low'].iloc[i-swing_length:i+swing_length+1]
        if df['low'].iloc[i] == window.min():
            df.loc[i, 'swing_low'] = True

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
                trend = 'bullish' if df['low'].iloc[i] > last_low else 'bearish'
            last_low = df['low'].iloc[i]
        df.loc[i, 'trend'] = trend

    return df

def detect_ob(df):
    df = df.copy()
    df['ob_bullish'] = False
    df['ob_bearish'] = False
    df['ob_high']    = np.nan
    df['ob_low']     = np.nan

    for i in range(1, len(df) - 1):
        if (df['close'].iloc[i]   < df['open'].iloc[i] and
            df['close'].iloc[i+1] > df['open'].iloc[i+1] and
            df['close'].iloc[i+1] > df['open'].iloc[i]):
            df.loc[i, 'ob_bullish'] = True
            df.loc[i, 'ob_high']    = df['high'].iloc[i]
            df.loc[i, 'ob_low']     = df['low'].iloc[i]

        if (df['close'].iloc[i]   > df['open'].iloc[i] and
            df['close'].iloc[i+1] < df['open'].iloc[i+1] and
            df['close'].iloc[i+1] < df['open'].iloc[i]):
            df.loc[i, 'ob_bearish'] = True
            df.loc[i, 'ob_high']    = df['high'].iloc[i]
            df.loc[i, 'ob_low']     = df['low'].iloc[i]

    return df

def detect_fvg(df):
    df = df.copy()
    df['fvg_bullish'] = False
    df['fvg_bearish'] = False

    for i in range(1, len(df) - 1):
        if df['low'].iloc[i+1] > df['high'].iloc[i-1]:
            df.loc[i, 'fvg_bullish'] = True
        if df['high'].iloc[i+1] < df['low'].iloc[i-1]:
            df.loc[i, 'fvg_bearish'] = True

    return df

def candle_body_ratio(candle):
    body  = abs(candle['close'] - candle['open'])
    total = candle['high'] - candle['low']
    return body / total if total > 0 else 0

def check_signal(df):
    df = detect_structure(df, swing_length=3)
    df = detect_ob(df)
    df = detect_fvg(df)

    last  = df.iloc[-1]
    trend = last['trend']

    # Session filter
    if not is_valid_session():
        return None, None, df

    # Lookback window
    lookback = 5
    window   = df.iloc[-lookback-1:-1]

    bull_ob  = window['ob_bullish'].any()
    bear_ob  = window['ob_bearish'].any()
    bull_fvg = window['fvg_bullish'].any()
    bear_fvg = window['fvg_bearish'].any()

    # Always print what we see
    print(f"  → Trend:{trend} | "
          f"BOB:{bull_ob} BOB:{bear_ob} | "
          f"BFVG:{bull_fvg} BeFVG:{bear_fvg}")

    ob_row = None
    if bull_ob:
        ob_candidates = window[window['ob_bullish']]
        if len(ob_candidates) > 0:
            ob_row = ob_candidates.iloc[-1]
    elif bear_ob:
        ob_candidates = window[window['ob_bearish']]
        if len(ob_candidates) > 0:
            ob_row = ob_candidates.iloc[-1]

    if trend == 'bullish' and bull_ob and bull_fvg:
        return 'LONG', ob_row, df
    elif trend == 'bearish' and bear_ob and bear_fvg:
        return 'SHORT', ob_row, df

    return None, None, df

# ── CALCULATE TRADE LEVELS ────────────────────────────────
def calculate_levels(signal, entry, ob_row, balance):
    pip      = 0.0001
    pip_val  = 10.0
    sl_pips  = SETTINGS['sl_pips']
    rr       = SETTINGS['rr_ratio']
    risk_amt = balance * (SETTINGS['risk_percent'] / 100)
    lot_size = round(max(0.01, risk_amt / (sl_pips * pip_val)), 2)

    if ob_row is not None:
        if signal == 'LONG':
            sl = ob_row['ob_low'] - (2 * pip)
            tp = entry + ((entry - sl) * rr)
        else:
            sl = ob_row['ob_high'] + (2 * pip)
            tp = entry - ((sl - entry) * rr)
    else:
        if signal == 'LONG':
            sl = entry - (sl_pips * pip)
            tp = entry + (sl_pips * pip * rr)
        else:
            sl = entry + (sl_pips * pip)
            tp = entry - (sl_pips * pip * rr)

    actual_sl_pips = round(abs(entry - sl) / pip, 1)

    return {
        'entry'    : round(entry, 5),
        'sl'       : round(sl, 5),
        'tp'       : round(tp, 5),
        'sl_pips'  : actual_sl_pips,
        'tp_pips'  : round(actual_sl_pips * rr, 1),
        'lot_size' : lot_size,
        'risk_amt' : round(risk_amt, 2),
        'max_profit': round(risk_amt * rr, 2)
    }

# ── LOG TRADE ─────────────────────────────────────────────
def log_trade(signal, levels, balance):
    os.makedirs('data', exist_ok=True)
    log_file = SETTINGS['log_file']

    trade = {
        'timestamp'  : datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
        'symbol'     : SETTINGS['symbol'],
        'signal'     : signal,
        'entry'      : levels['entry'],
        'stop_loss'  : levels['sl'],
        'take_profit': levels['tp'],
        'sl_pips'    : levels['sl_pips'],
        'tp_pips'    : levels['tp_pips'],
        'lot_size'   : levels['lot_size'],
        'risk_amount': levels['risk_amt'],
        'max_profit' : levels['max_profit'],
        'balance'    : balance,
        'status'     : 'OPEN'
    }

    df_log = pd.DataFrame([trade])

    if os.path.exists(log_file):
        df_log.to_csv(log_file, mode='a', header=False, index=False)
    else:
        df_log.to_csv(log_file, index=False)

    return trade

# ── PRINT SIGNAL ALERT ────────────────────────────────────
def print_alert(signal, levels, balance):
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n{'='*50}")
    print(f"  SIGNAL DETECTED — {now} UTC")
    print(f"{'='*50}")
    print(f"  Symbol     : {SETTINGS['symbol']}")
    print(f"  Direction  : {signal}")
    print(f"  Entry      : {levels['entry']}")
    print(f"  Stop Loss  : {levels['sl']} ({levels['sl_pips']} pips)")
    print(f"  Take Profit: {levels['tp']} ({levels['tp_pips']} pips)")
    print(f"  Lot Size   : {levels['lot_size']}")
    print(f"  Risk       : ${levels['risk_amt']}")
    print(f"  Max Profit : ${levels['max_profit']}")
    print(f"  Balance    : ${balance:,.2f}")
    print(f"{'='*50}")
    print(f"  Logged to: {SETTINGS['log_file']}")
    print(f"{'='*50}\n")

# ── MAIN LOOP ─────────────────────────────────────────────
def main():
    print("="*50)
    print("  BILLION DOLLARS — PAPER TRADER")
    print("  Session 6 — Live Signal Detection")
    print("="*50)
    print(f"  Symbol   : {SETTINGS['symbol']}")
    print(f"  Risk     : {SETTINGS['risk_percent']}% per trade")
    print(f"  RR Ratio : 1:{SETTINGS['rr_ratio']}")
    print(f"  SL Pips  : {SETTINGS['sl_pips']}")
    print(f"  Cooldown : {SETTINGS['cooldown_hours']} hours")
    print(f"  Max/Day  : {SETTINGS['max_trades_day']} trades")
    print("="*50)
    print("\nConnecting to Pepperstone...")

    if not connect():
        print("Connection failed. Check MT5 is open.")
        return

    print("Connected. Bot is running.")
    print("Press Ctrl+C to stop.\n")

    last_signal_time = None
    trades_today     = 0
    last_date        = None
    scan_count       = 0

    try:
        while True:
            scan_count += 1
            now         = datetime.utcnow()
            now_str     = now.strftime('%H:%M:%S')

            # Reset daily counter
            today = now.date()
            if today != last_date:
                last_date    = today
                trades_today = 0
                print(f"\n--- New trading day: {today} ---")

            # Status update every 10 scans
            
            if scan_count % 1 == 0:
                account = mt5.account_info()
                if account is None:
                    print(f"[{now_str}] MT5 disconnected — reconnecting...")
                    mt5.shutdown()
                    time.sleep(5)
                    connect()
                    continue
            session = "ACTIVE" if is_valid_session() else "CLOSED"
            print(f"[{now_str}] Scan #{scan_count} | "
                f"Balance: ${account.balance:,.2f} | "
                f"Session: {session} | "
                f"Trades today: {trades_today}/{SETTINGS['max_trades_day']}")
            # Skip if daily limit reached
            if trades_today >= SETTINGS['max_trades_day']:
                time.sleep(SETTINGS['check_interval'])
                continue

            # Skip if market session closed
            if not is_valid_session():
                time.sleep(SETTINGS['check_interval'])
                continue

            # Cooldown check
            if last_signal_time is not None:
                hours_since = (now - last_signal_time).total_seconds() / 3600
                if hours_since < SETTINGS['cooldown_hours']:
                    remaining = SETTINGS['cooldown_hours'] - hours_since
                    if scan_count % 10 == 0:
                        print(f"  Cooldown: {remaining:.1f}hrs remaining")
                    time.sleep(SETTINGS['check_interval'])
                    continue

            # Get latest candles and check for signal
            df = get_candles(SETTINGS['symbol'], mt5.TIMEFRAME_H1, 100)
            if df is None:
                time.sleep(SETTINGS['check_interval'])
                continue

            signal, ob_row, df = check_signal(df)

            if signal:
                account = mt5.account_info()
                balance = account.balance
                tick    = mt5.symbol_info_tick(SETTINGS['symbol'])
                entry   = tick.ask if signal == 'LONG' else tick.bid

                levels  = calculate_levels(signal, entry, ob_row, balance)

                # Validate stop loss distance
                if 5 <= levels['sl_pips'] <= 50:
                    print_alert(signal, levels, balance)
                    log_trade(signal, levels, balance)
                    last_signal_time = now
                    trades_today    += 1
                else:
                    print(f"[{now_str}] Signal found but SL invalid "
                          f"({levels['sl_pips']} pips) — skipped")

            time.sleep(SETTINGS['check_interval'])

    except KeyboardInterrupt:
        print("\n\nBot stopped by user.")
        print(f"Total scans completed: {scan_count}")

        if os.path.exists(SETTINGS['log_file']):
            log_df = pd.read_csv(SETTINGS['log_file'])
            print(f"Total signals logged : {len(log_df)}")
            print(f"Log saved at         : {SETTINGS['log_file']}")

        mt5.shutdown()
        print("Disconnected. Session 6 running.")

if __name__ == "__main__":
    main()
