import MetaTrader5 as mt5
import pandas as pd
import os
from datetime import datetime
import pytz

# ── CONNECT ──────────────────────────────────────────────
def connect():
    if not mt5.initialize():
        print(f"Failed to connect: {mt5.last_error()}")
        quit()
    
    login    = 61558462
    password = "adbcjnM5$q"
    server   = "mt5-demo01.pepperstone.com"
    
    if not mt5.login(login, password=password, server=server):
        print(f"Login failed: {mt5.last_error()}")
        mt5.shutdown()
        quit()
    
    print("Connected to Pepperstone successfully.")

# ── DOWNLOAD CANDLE DATA ─────────────────────────────────
def download_data(symbol, timeframe, timeframe_name, bars=50000):
    print(f"Downloading {symbol} {timeframe_name} data ({bars} candles)...")
    
    # Make sure symbol is available
    mt5.symbol_select(symbol, True)
    
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
    
    if rates is None or len(rates) == 0:
        print(f"No data received for {symbol}")
        return None
    
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df = df[['time', 'open', 'high', 'low', 'close', 'tick_volume']]
    df.columns = ['time', 'open', 'high', 'low', 'close', 'volume']
    df = df.sort_values('time').reset_index(drop=True)
    
    print(f"Downloaded {len(df)} candles.")
    print(f"From: {df['time'].iloc[0]}")
    print(f"To:   {df['time'].iloc[-1]}")
    
    return df

# ── SAVE DATA ────────────────────────────────────────────
def save_data(df, symbol, timeframe_name):
    folder = "data"
    os.makedirs(folder, exist_ok=True)
    
    filename = f"{folder}/{symbol}_{timeframe_name}.csv"
    df.to_csv(filename, index=False)
    print(f"Saved to {filename}")
    return filename

# ── MAIN ─────────────────────────────────────────────────
def main():
    connect()
    
    # Pairs and timeframes to download
    downloads = [
        ("EURUSD", mt5.TIMEFRAME_H4,  "H4"),
        ("EURUSD", mt5.TIMEFRAME_H1,  "H1"),
        ("EURUSD", mt5.TIMEFRAME_M15, "M15"),
        ("GBPUSD", mt5.TIMEFRAME_H4,  "H4"),
        ("GBPUSD", mt5.TIMEFRAME_H1,  "H1"),
        ("GBPUSD", mt5.TIMEFRAME_M15, "M15"),
    ]
    
    results = []
    
    for symbol, timeframe, tf_name in downloads:
        print(f"\n{'='*45}")
        df = download_data(symbol, timeframe, tf_name)
        
        if df is not None:
            filepath = save_data(df, symbol, tf_name)
            results.append({
                'pair'     : symbol,
                'timeframe': tf_name,
                'candles'  : len(df),
                'from'     : df['time'].iloc[0],
                'to'       : df['time'].iloc[-1],
                'file'     : filepath
            })
    
    # ── SUMMARY ──────────────────────────────────────────
    print(f"\n{'='*45}")
    print("DOWNLOAD COMPLETE — SUMMARY")
    print(f"{'='*45}")
    for r in results:
        print(f"{r['pair']} {r['timeframe']}: {r['candles']:,} candles → {r['file']}")
    
    print(f"\nAll data saved to /data folder.")
    print("Ready for backtesting.")
    
    mt5.shutdown()
    print("Disconnected.")

if __name__ == "__main__":
    main()
