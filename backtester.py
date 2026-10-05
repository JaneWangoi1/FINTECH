import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

# ── LOAD DATA ────────────────────────────────────────────
def load_signals():
    signals = pd.read_csv(
        "data/signals_EURUSD_H1.csv",
        parse_dates=['time']
    )
    full = pd.read_csv(
        "data/EURUSD_H1_analysed.csv",
        parse_dates=['time']
    )
    print(f"Loaded {len(signals):,} signals")
    print(f"Loaded {len(full):,} candles for price lookup")
    return signals, full

# ── SIMULATE TRADE WITH SPREAD COST ──────────────────────
def simulate_trade(signal_row, full_df,
                   risk_percent=1.0, rr_ratio=2.0,
                   sl_pips=15, account_balance=10000,
                   spread_pips=0.5):

    pip        = 0.0001
    pip_value  = 10.0
    risk_amt   = account_balance * (risk_percent / 100)
    lot_size   = risk_amt / (sl_pips * pip_value)
    lot_size   = round(max(0.01, min(100, lot_size)), 2)

    entry_time = signal_row['time']
    signal     = signal_row['signal']

    future = full_df[full_df['time'] > entry_time].head(100)
    if len(future) < 2:
        return None

    # Add spread cost to entry
    entry = signal_row['close']
    spread_cost = spread_pips * pip * lot_size * 100000 / 100000
    spread_dollar_cost = spread_pips * pip_value * lot_size

    if signal == 'LONG':
        entry_with_spread = entry + (spread_pips * pip)
        sl = entry_with_spread - (sl_pips * pip)
        tp = entry_with_spread + (sl_pips * pip * rr_ratio)
    else:
        entry_with_spread = entry - (spread_pips * pip)
        sl = entry_with_spread + (sl_pips * pip)
        tp = entry_with_spread - (sl_pips * pip * rr_ratio)

    for _, candle in future.iterrows():
        if signal == 'LONG':
            if candle['low'] <= sl:
                pnl = -(risk_amt + spread_dollar_cost)
                return {'time': entry_time, 'signal': signal,
                        'entry': entry, 'exit': sl,
                        'sl_pips': sl_pips,
                        'tp_pips': sl_pips * rr_ratio,
                        'lot_size': lot_size,
                        'pnl': round(pnl, 2),
                        'result': 'LOSS',
                        'exit_time': candle['time']}
            if candle['high'] >= tp:
                pnl = (risk_amt * rr_ratio) - spread_dollar_cost
                return {'time': entry_time, 'signal': signal,
                        'entry': entry, 'exit': tp,
                        'sl_pips': sl_pips,
                        'tp_pips': sl_pips * rr_ratio,
                        'lot_size': lot_size,
                        'pnl': round(pnl, 2),
                        'result': 'WIN',
                        'exit_time': candle['time']}
        else:
            if candle['high'] >= sl:
                pnl = -(risk_amt + spread_dollar_cost)
                return {'time': entry_time, 'signal': signal,
                        'entry': entry, 'exit': sl,
                        'sl_pips': sl_pips,
                        'tp_pips': sl_pips * rr_ratio,
                        'lot_size': lot_size,
                        'pnl': round(pnl, 2),
                        'result': 'LOSS',
                        'exit_time': candle['time']}
            if candle['low'] <= tp:
                pnl = (risk_amt * rr_ratio) - spread_dollar_cost
                return {'time': entry_time, 'signal': signal,
                        'entry': entry, 'exit': tp,
                        'sl_pips': sl_pips,
                        'tp_pips': sl_pips * rr_ratio,
                        'lot_size': lot_size,
                        'pnl': round(pnl, 2),
                        'result': 'WIN',
                        'exit_time': candle['time']}
    return None

# ── RUN BACKTEST WITH WALK-FORWARD SPLIT ─────────────────
def run_backtest(signals, full_df,
                 initial_balance = 10000,
                 risk_percent    = 1.0,
                 rr_ratio        = 2.0,
                 sl_pips         = 15,
                 max_trades_day  = 2,
                 spread_pips     = 0.5,
                 cooldown_hours  = 4):

    print(f"\nRunning backtest on {len(signals):,} signals...")
    print(f"Risk={risk_percent}% | RR=1:{rr_ratio} | "
          f"SL={sl_pips}pips | Spread={spread_pips}pips | "
          f"Cooldown={cooldown_hours}hrs")

    # Walk-forward split
    split_date = pd.Timestamp('2022-01-01')
    train = signals[signals['time'] < split_date]
    test  = signals[signals['time'] >= split_date]

    print(f"\nTraining set : {len(train):,} signals (2018-2021)")
    print(f"Testing set  : {len(test):,} signals  (2022-2026)")

    results = {}

    for label, subset in [("TRAINING", train), ("TESTING", test)]:
        trades       = []
        balance      = initial_balance
        last_date    = None
        trades_today = 0
        last_trade_time = None

        for _, signal_row in subset.iterrows():
            trade_date = signal_row['time'].date()

            # Reset daily counter
            if trade_date != last_date:
                last_date    = trade_date
                trades_today = 0

            # Daily trade limit
            if trades_today >= max_trades_day:
                continue

            # Cooldown filter — skip if last trade too recent
            if last_trade_time is not None:
                hours_since = (signal_row['time'] -
                               last_trade_time).total_seconds() / 3600
                if hours_since < cooldown_hours:
                    continue

            trade = simulate_trade(
                signal_row, full_df,
                risk_percent    = risk_percent,
                rr_ratio        = rr_ratio,
                sl_pips         = sl_pips,
                account_balance = balance,
                spread_pips     = spread_pips
            )

            if trade is None:
                continue

            balance             += trade['pnl']
            trade['balance']     = round(balance, 2)
            trades_today        += 1
            last_trade_time      = signal_row['time']
            trades.append(trade)

            if balance <= initial_balance * 0.5:
                print(f"ACCOUNT BLOWN in {label}")
                break

        results[label] = pd.DataFrame(trades)

    return results

# ── ANALYSE RESULTS ───────────────────────────────────────
def analyse_results(trades_df, initial_balance=10000):
    if len(trades_df) == 0:
        print("No trades to analyse")
        return

    wins    = trades_df[trades_df['result'] == 'WIN']
    losses  = trades_df[trades_df['result'] == 'LOSS']

    total_trades  = len(trades_df)
    win_rate      = len(wins) / total_trades * 100
    total_pnl     = trades_df['pnl'].sum()
    final_balance = initial_balance + total_pnl
    total_return  = (total_pnl / initial_balance) * 100

    # Sharpe Ratio
    returns       = trades_df['pnl'] / initial_balance
    sharpe        = (returns.mean() / returns.std()) * np.sqrt(252) if returns.std() > 0 else 0

    # Max Drawdown
    trades_df     = trades_df.copy()
    trades_df['cumulative'] = initial_balance + trades_df['pnl'].cumsum()
    trades_df['peak']       = trades_df['cumulative'].cummax()
    trades_df['drawdown']   = (trades_df['cumulative'] - trades_df['peak']) / trades_df['peak'] * 100
    max_drawdown            = trades_df['drawdown'].min()

    # Profit Factor
    gross_profit  = wins['pnl'].sum()   if len(wins)   > 0 else 0
    gross_loss    = abs(losses['pnl'].sum()) if len(losses) > 0 else 1
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

    print(f"\n{'='*50}")
    print("BACKTEST RESULTS")
    print(f"{'='*50}")
    print(f"Total trades     : {total_trades:,}")
    print(f"Wins             : {len(wins):,}")
    print(f"Losses           : {len(losses):,}")
    print(f"Win rate         : {win_rate:.1f}%")
    print(f"{'─'*50}")
    print(f"Initial balance  : ${initial_balance:,.2f}")
    print(f"Final balance    : ${final_balance:,.2f}")
    print(f"Total P&L        : ${total_pnl:,.2f}")
    print(f"Total return     : {total_return:.1f}%")
    print(f"{'─'*50}")
    print(f"Sharpe ratio     : {sharpe:.2f}")
    print(f"Max drawdown     : {max_drawdown:.1f}%")
    print(f"Profit factor    : {profit_factor:.2f}")
    print(f"{'─'*50}")

    # Verdict
    print(f"\nVERDICT:")
    if sharpe > 1.5 and max_drawdown > -15 and win_rate > 45:
        print("EXCELLENT — System ready for paper trading")
    elif sharpe > 1.0 and max_drawdown > -20 and win_rate > 40:
        print("GOOD — System needs minor refinement")
    elif sharpe > 0.5:
        print("MARGINAL — System needs significant refinement")
    else:
        print("POOR — Strategy needs rework before going live")

    return trades_df

# ── PLOT EQUITY CURVE ─────────────────────────────────────
def plot_equity_curve(trades_df, initial_balance=10000, title='BILLION DOLLARS — Backtest Results'):
    trades_df = trades_df.copy()
    trades_df['cumulative'] = initial_balance + trades_df['pnl'].cumsum()

    fig, axes = plt.subplots(2, 1, figsize=(14, 8))
    fig.suptitle(title, 
                 fontsize=14, fontweight='bold')

    # Equity curve
    axes[0].plot(trades_df['time'], trades_df['cumulative'],
                 color='#00AA00', linewidth=1.5, label='Equity')
    axes[0].axhline(y=initial_balance, color='gray',
                    linestyle='--', alpha=0.5, label='Starting balance')
    axes[0].set_title('Equity Curve')
    axes[0].set_ylabel('Account Balance ($)')
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)

    # Win/Loss bars
    colors = ['#00AA00' if r == 'WIN' else '#CC0000' 
              for r in trades_df['result']]
    axes[1].bar(range(len(trades_df)), trades_df['pnl'],
                color=colors, alpha=0.7, width=0.8)
    axes[1].axhline(y=0, color='gray', linestyle='-', alpha=0.5)
    axes[1].set_title('Trade P&L')
    axes[1].set_ylabel('Profit / Loss ($)')
    axes[1].set_xlabel('Trade Number')
    axes[1].grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig('data/backtest_results.png', dpi=150, bbox_inches='tight')
    print("Chart saved → data/backtest_results.png")
    plt.show()

# ── MAIN ─────────────────────────────────────────────────
def main():
    print("="*50)
    print("BACKTESTER v2 — WALK-FORWARD VALIDATION")
    print("="*50)

    signals, full_df = load_signals()

    results = run_backtest(
        signals, full_df,
        initial_balance = 10000,
        risk_percent    = 1.0,
        rr_ratio        = 2.0,
        sl_pips         = 15,
        max_trades_day  = 2,
        spread_pips     = 0.5,
        cooldown_hours  = 4
    )

    for label, trades_df in results.items():
        print(f"\n{'='*50}")
        print(f"{label} RESULTS")
        print(f"{'='*50}")
        if len(trades_df) > 0:
            trades_df = analyse_results(trades_df)
            trades_df.to_csv(
                f"data/backtest_{label.lower()}.csv",
                index=False
            )
            plot_equity_curve(trades_df,
                              title=f"BILLION DOLLARS — {label}")

    print("\nSession 5 complete.")

if __name__ == "__main__":
    main()
