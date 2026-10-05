import MetaTrader5 as mt5
import pandas as pd

# ── CONNECT TO MT5 ──────────────────────────────────────
print("Connecting to MetaTrader 5...")

if not mt5.initialize():
    print(f"Failed to connect. Error: {mt5.last_error()}")
    quit()

# ── LOGIN TO YOUR DEMO ACCOUNT ──────────────────────────
login    = 61558462
password = "adbcjnM5$q"
server   = "mt5-demo01.pepperstone.com"

authorized = mt5.login(login, password=password, server=server)

if not authorized:
    print(f"Login failed. Error: {mt5.last_error()}")
    mt5.shutdown()
    quit()

print("Connected successfully!")

# ── ACCOUNT INFO ─────────────────────────────────────────
info = mt5.account_info()
print(f"\nAccount:  {info.login}")
print(f"Broker:   {info.company}")
print(f"Balance:  ${info.balance:,.2f}")
print(f"Currency: {info.currency}")
print(f"Leverage: 1:{info.leverage}")

# ── LIVE EURUSD PRICE ────────────────────────────────────
tick = mt5.symbol_info_tick("EURUSD")
print(f"\nEURUSD Live Price:")
print(f"  Bid: {tick.bid}")
print(f"  Ask: {tick.ask}")
print(f"  Spread: {round((tick.ask - tick.bid) * 10000, 1)} pips")

# ── LAST 10 CANDLES ──────────────────────────────────────
rates = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_H1, 0, 10)
df = pd.DataFrame(rates)
df['time'] = pd.to_datetime(df['time'], unit='s')
print(f"\nLast 10 EURUSD H1 Candles:")
print(df[['time','open','high','low','close','tick_volume']].to_string(index=False))

# ── DISCONNECT ───────────────────────────────────────────
mt5.shutdown()
print("\nDisconnected. Session 1 complete.")
