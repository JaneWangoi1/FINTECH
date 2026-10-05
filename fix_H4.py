import MetaTrader5 as mt5
import pandas as pd
import os

def connect():
    if not mt5.initialize():
        print(f"Failed: {mt5.last_error()}")
        quit()
    if not mt5.login(61558462, password="adbcjnM5$q", server="mt5-demo01.pepperstone.com"):
        print(f"Login failed: {mt5.last_error()}")
        mt5.shutdown()
        quit()
    print("Connected.")

def main():
    connect()
    
    pairs = ["EURUSD", "GBPUSD"]
    
    for symbol in pairs:
        # Force add symbol to market watch
        selected = mt5.symbol_select(symbol, True)
        print(f"{symbol} selected: {selected}")
        
        # Check symbol info
        info = mt5.symbol_info(symbol)
        if info is None:
            print(f"{symbol} not found")
            continue
            
        print(f"{symbol} visible: {info.visible}")
        
        # Download H4
        print(f"Downloading {symbol} H4...")
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H4, 0, 50000)
        
        if rates is None or len(rates) == 0:
            print(f"Still no data for {symbol} H4. Error: {mt5.last_error()}")
            continue
            
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df = df[['time','open','high','low','close','tick_volume']]
        df.columns = ['time','open','high','low','close','volume']
        df = df.sort_values('time').reset_index(drop=True)
        
        os.makedirs("data", exist_ok=True)
        filename = f"data/{symbol}_H4.csv"
        df.to_csv(filename, index=False)
        
        print(f"Saved {len(df):,} candles → {filename}")
        print(f"From: {df['time'].iloc[0]}")
        print(f"To:   {df['time'].iloc[-1]}")
        print()
    
    mt5.shutdown()
    print("Done.")

if __name__ == "__main__":
    main()
