import MetaTrader5 as mt5
import pandas as pd
import numpy as np

# ── CONNECT ──────────────────────────────────────────────
def connect():
    if not mt5.initialize():
        print(f"Failed: {mt5.last_error()}")
        quit()
    if not mt5.login(61558462, 
                     password="adbcjnM5$q",
                     server="mt5-demo01.pepperstone.com"):
        print(f"Login failed: {mt5.last_error()}")
        mt5.shutdown()
        quit()

# ── ACCOUNT INFO ─────────────────────────────────────────
def get_account_info():
    info = mt5.account_info()
    return {
        'balance'   : info.balance,
        'equity'    : info.equity,
        'currency'  : info.currency,
        'leverage'  : info.leverage
    }

# ── LOT SIZE CALCULATOR ───────────────────────────────────
def calculate_lot_size(account_balance, risk_percent, 
                        stop_loss_pips, symbol="EURUSD"):
    
    # Step 1 — How much money are we risking?
    risk_amount = account_balance * (risk_percent / 100)
    
    # Step 2 — Get symbol info from MT5
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        print(f"Symbol {symbol} not found")
        return None
    
    # Step 3 — Pip value calculation
    # For EURUSD: 1 pip = 0.0001, 1 standard lot = 100,000 units
    point          = symbol_info.point
    pip_size       = point * 10  # 1 pip = 10 points for 5-decimal brokers
    contract_size  = symbol_info.trade_contract_size  # usually 100,000
    
    # Pip value in account currency (USD) per lot
    pip_value_per_lot = pip_size * contract_size
    
    # Step 4 — Calculate lot size
    lot_size = risk_amount / (stop_loss_pips * pip_value_per_lot)
    
    # Step 5 — Round to broker minimum (0.01 lots)
    min_lot  = symbol_info.volume_min
    max_lot  = symbol_info.volume_max
    lot_step = symbol_info.volume_step
    
    lot_size = round(lot_size / lot_step) * lot_step
    lot_size = max(min_lot, min(max_lot, lot_size))
    
    return {
        'risk_amount'      : round(risk_amount, 2),
        'stop_loss_pips'   : stop_loss_pips,
        'pip_value_per_lot': round(pip_value_per_lot, 4),
        'lot_size'         : round(lot_size, 2),
        'min_lot'          : min_lot,
        'max_lot'          : max_lot
    }

# ── STOP LOSS & TAKE PROFIT ───────────────────────────────
def calculate_sl_tp(signal, entry_price, ob_high, ob_low, 
                    rr_ratio=2.0, symbol="EURUSD"):
    
    symbol_info = mt5.symbol_info(symbol)
    point       = symbol_info.point
    pip_size    = point * 10
    
    if signal == 'LONG':
        # Stop loss below the order block with 2 pip buffer
        stop_loss   = ob_low - (2 * pip_size)
        sl_distance = entry_price - stop_loss
        take_profit = entry_price + (sl_distance * rr_ratio)
        sl_pips     = round(sl_distance / pip_size, 1)
        tp_pips     = round((take_profit - entry_price) / pip_size, 1)

    elif signal == 'SHORT':
        # Stop loss above the order block with 2 pip buffer
        stop_loss   = ob_high + (2 * pip_size)
        sl_distance = stop_loss - entry_price
        take_profit = entry_price - (sl_distance * rr_ratio)
        sl_pips     = round(sl_distance / pip_size, 1)
        tp_pips     = round((entry_price - take_profit) / pip_size, 1)

    return {
        'entry'      : round(entry_price, 5),
        'stop_loss'  : round(stop_loss, 5),
        'take_profit': round(take_profit, 5),
        'sl_pips'    : sl_pips,
        'tp_pips'    : tp_pips,
        'rr_ratio'   : rr_ratio
    }

# ── DAILY LOSS LIMIT CHECK ────────────────────────────────
def check_daily_limit(account_info, max_daily_loss_percent=3.0):
    balance = account_info['balance']
    equity  = account_info['equity']
    
    daily_loss         = balance - equity
    daily_loss_percent = (daily_loss / balance) * 100
    
    if daily_loss_percent >= max_daily_loss_percent:
        return False, daily_loss_percent
    return True, daily_loss_percent

# ── TRADE VALIDATOR ───────────────────────────────────────
def validate_trade(signal, entry, ob_high, ob_low, 
                   symbol="EURUSD", risk_percent=1.0, rr_ratio=2.0):
    
    account   = get_account_info()
    
    # Check daily loss limit
    can_trade, loss_pct = check_daily_limit(account)
    if not can_trade:
        return None, f"BLOCKED — Daily loss limit reached ({loss_pct:.1f}%)"
    
    # Calculate SL/TP
    levels = calculate_sl_tp(signal, entry, ob_high, ob_low, rr_ratio, symbol)
    
    # Validate stop loss distance (minimum 5 pips, maximum 50 pips)
    if levels['sl_pips'] < 5:
        return None, f"BLOCKED — Stop loss too tight ({levels['sl_pips']} pips)"
    if levels['sl_pips'] > 50:
        return None, f"BLOCKED — Stop loss too wide ({levels['sl_pips']} pips)"
    
    # Calculate position size
    sizing = calculate_lot_size(account['balance'], risk_percent, 
                                 levels['sl_pips'], symbol)
    
    trade = {
        'signal'      : signal,
        'symbol'      : symbol,
        'entry'       : levels['entry'],
        'stop_loss'   : levels['stop_loss'],
        'take_profit' : levels['take_profit'],
        'sl_pips'     : levels['sl_pips'],
        'tp_pips'     : levels['tp_pips'],
        'rr_ratio'    : levels['rr_ratio'],
        'lot_size'    : sizing['lot_size'],
        'risk_amount' : sizing['risk_amount'],
        'risk_percent': risk_percent,
        'balance'     : account['balance'],
        'equity'      : account['equity'],
        'daily_loss'  : round(loss_pct, 2)
    }
    
    return trade, "APPROVED"

# ── MAIN ─────────────────────────────────────────────────
def main():
    print("="*50)
    print("RISK CALCULATOR — SESSION 4")
    print("="*50)
    
    connect()
    account = get_account_info()
    
    print(f"\nAccount Balance : ${account['balance']:,.2f}")
    print(f"Account Equity  : ${account['equity']:,.2f}")
    print(f"Leverage        : 1:{account['leverage']}")
    
    # ── TEST WITH REAL SIGNAL FROM SESSION 3 ─────────────
    # Using last LONG signal from our signal engine
    # EURUSD bullish, entry at current price
    
    tick   = mt5.symbol_info_tick("EURUSD")
    entry  = tick.ask  # buy at ask price
    
    # Simulate order block levels (10 pip range below entry)
    pip    = 0.0001
    ob_low  = entry - (10 * pip)
    ob_high = entry - (5  * pip)
    
    print(f"\nTest Trade — LONG EURUSD")
    print(f"Entry price : {entry}")
    print(f"OB High     : {round(ob_high, 5)}")
    print(f"OB Low      : {round(ob_low, 5)}")
    
    trade, status = validate_trade(
        signal     = 'LONG',
        entry      = entry,
        ob_high    = ob_high,
        ob_low     = ob_low,
        symbol     = 'EURUSD',
        risk_percent = 1.0,
        rr_ratio   = 2.0
    )
    
    print(f"\nTrade Status: {status}")
    
    if trade:
        print(f"\n{'='*50}")
        print("TRADE PARAMETERS")
        print(f"{'='*50}")
        print(f"Signal       : {trade['signal']}")
        print(f"Entry        : {trade['entry']}")
        print(f"Stop Loss    : {trade['stop_loss']} ({trade['sl_pips']} pips)")
        print(f"Take Profit  : {trade['take_profit']} ({trade['tp_pips']} pips)")
        print(f"Risk/Reward  : 1:{trade['rr_ratio']}")
        print(f"Lot Size     : {trade['lot_size']}")
        print(f"Risk Amount  : ${trade['risk_amount']}")
        print(f"Risk Percent : {trade['risk_percent']}%")
        print(f"Daily Loss   : {trade['daily_loss']}%")
        print(f"{'─'*50}")
        
        potential_profit = trade['risk_amount'] * trade['rr_ratio']
        print(f"Max Loss     : -${trade['risk_amount']}")
        print(f"Max Profit   : +${round(potential_profit, 2)}")
    
    mt5.shutdown()
    print("\nSession 4 complete.")

if __name__ == "__main__":
    main()
