import ccxt
import pandas as pd
from strategy import should_buy, should_sell
import json

# 파라미터 그리드 (필요시 확장)
grid = {
    'ema_short':   [5, 10, 15],
    'ema_long':    [20, 30, 50],
    'macd_fast':   [12, 15],
    'macd_slow':   [26, 30],
    'rsi_period':  [14],
    'rsi_buy_thresh':  [40, 50, 60],
    'rsi_sell_thresh': [60, 70, 80],
    'bb_period':   [20],
    'adx_period':  [14],
    'adx_thresh':  [20, 25]
}

def optimize_params(df, initial_capital):
    best_val = -float('inf')
    best_params = None

    for es in grid['ema_short']:
        for el in grid['ema_long']:
            if es >= el: continue
            for mf in grid['macd_fast']:
                for ms in grid['macd_slow']:
                    if mf >= ms: continue
                    for rp in grid['rsi_period']:
                        for rb in grid['rsi_buy_thresh']:
                            for rs in grid['rsi_sell_thresh']:
                                if rb >= rs: continue
                                for bb in grid['bb_period']:
                                    for ap in grid['adx_period']:
                                        for ath in grid['adx_thresh']:
                                            params = {
                                                'ema_short': es, 'ema_long': el,
                                                'macd_fast': mf, 'macd_slow': ms,
                                                'rsi_period': rp,
                                                'rsi_buy_thresh': rb, 'rsi_sell_thresh': rs,
                                                'bb_period': bb,
                                                'adx_period': ap, 'adx_thresh': ath
                                            }
                                            cash = initial_capital
                                            btc  = 0
                                            window_size = max(el, ms, rp, bb, ap)
                                            for i in range(window_size, len(df)):
                                                window = df.iloc[i-window_size:i+1].values.tolist()
                                                price = df['close'].iloc[i]
                                                if should_buy(window, params) and cash > price:
                                                    btc += cash / price
                                                    cash = 0
                                                elif should_sell(window, params) and btc > 0:
                                                    cash += btc * price
                                                    btc = 0
                                            final_val = cash + btc * df['close'].iloc[-1]
                                            if final_val > best_val:
                                                best_val = final_val
                                                best_params = params.copy()

    return best_params
