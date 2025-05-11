import ccxt, time, json
import pandas as pd
from backtest import optimize_params
from strategy import should_buy, should_sell

# 설정 로드
with open('config.json') as f:
    cfg = json.load(f)

exchange = ccxt.bithumb({
    'apiKey': cfg['apiKey'],
    'secret': cfg['secret'],
    'enableRateLimit': True
})
symbol = cfg['symbol']

def fetch_ohlcv(limit):
    data = exchange.fetch_ohlcv(symbol, timeframe=cfg['timeframe'], limit=limit)
    return pd.DataFrame(data, columns=['ts','open','high','low','close','vol'])

def run_bot():
    params = None
    while True:
        try:
            df = fetch_ohlcv(cfg['backtest_limit'])
            # 1) 매 루프마다 최적 파라미터 재계산
            params = optimize_params(df, grid=None)  # grid는 backtest.py 내부 정의 사용
            ohlcv_list = df.values.tolist()
            bal = exchange.fetch_balance()
            krw, btc = bal['total']['KRW'], bal['total']['BTC']

            # 2) 자동 매수/매도
            price = ohlcv_list[-1][4]
            if should_buy(ohlcv_list, params) and krw > price:
                order = exchange.create_market_buy_order(symbol, krw/price)
                print(time.ctime(), "BUY:", order)
            elif should_sell(ohlcv_list, params) and btc > 0:
                order = exchange.create_market_sell_order(symbol, btc)
                print(time.ctime(), "SELL:", order)

        except Exception as e:
            print("Error:", e)

        time.sleep(60*int(cfg['timeframe'][:-1]))  # 예: '1h' → 3600초

if __name__ == "__main__":
    run_bot()
