import ccxt
import pandas as pd
from strategy import should_buy, should_sell
import json

def optimize_params(df, grid):
    results = []
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
                                            params = dict(
                                                ema_short=es, ema_long=el,
                                                macd_fast=mf, macd_slow=ms,
                                                rsi_period=rp,
                                                rsi_buy_thresh=rb, rsi_sell_thresh=rs,
                                                bb_period=bb,
                                                adx_period=ap, adx_thresh=ath
                                            )
                                            cash = 1000000; btc = 0
                                            # 시뮬레이션
                                            for i in range(max(el, ms, rp, bb, ap), len(df)):
                                                window = df.iloc[i-max(el, ms, rp, bb, ap):i+1].values.tolist()
                                                price = df['close'].iloc[i]
                                                if should_buy(window, params) and cash > price:
                                                    btc += cash/price; cash = 0
                                                if should_sell(window, params) and btc > 0:
                                                    cash += btc*price; btc = 0
                                            final_val = cash + btc*df['close'].iloc[-1]
                                            results.append((final_val, params))
    # 최대 자산 조합 반환
    return max(results, key=lambda x: x[0])[1]

if __name__ == "__main__":
    # 데이터 로드
    with open('config.json') as f: cfg = json.load(f)
    ex = ccxt.bithumb()
    ohlcv = ex.fetch_ohlcv(cfg['symbol'], timeframe=cfg['timeframe'], limit=cfg['backtest_limit'])
    df = pd.DataFrame(ohlcv, columns=['ts','open','high','low','close','vol'])

    # 그리드 정의 (필요시 config.json으로 분리 가능)
    grid = {
      'ema_short':   [5,10,15],
      'ema_long':    [20,30,50],
      'macd_fast':   [12,15],
      'macd_slow':   [26,30],
      'rsi_period':  [14],
      'rsi_buy_thresh':  [40,50,60],
      'rsi_sell_thresh': [60,70,80],
      'bb_period':   [20],
      'adx_period':  [14],
      'adx_thresh':  [20,25]
    }

    best = optimize_params(df, grid)
    print("BEST PARAMS:", best)
