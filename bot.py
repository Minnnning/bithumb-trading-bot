import ccxt, time, json, logging
import pandas as pd
from backtest import optimize_params
from strategy import should_buy, should_sell

# --- 로깅 설정 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger()

# 설정 로드
with open('config.json') as f:
    cfg = json.load(f)

exchange = ccxt.bithumb({
    'apiKey': cfg['apiKey'],
    'secret': cfg['secret'],
    'enableRateLimit': True
})
symbol = cfg['symbol']
initial_capital = cfg['initial_capital']

def fetch_ohlcv(limit):
    data = exchange.fetch_ohlcv(symbol, timeframe=cfg['timeframe'], limit=limit)
    df = pd.DataFrame(data, columns=['ts','open','high','low','close','vol'])
    return df

def run_bot():
    logger.info("=== Trading Bot Started ===")

    current_params = None
    while True:
        try:
            df = fetch_ohlcv(cfg['backtest_limit'])
            # 1) 매 루프마다 최적 파라미터 재계산
            logger.info("Running backtest to optimize parameters...")
            params = optimize_params(df, initial_capital)
            if params != current_params:
                current_params = params
                logger.info(f"New optimal params: {current_params}")

            ohlcv_list = df.values.tolist()
            balance = exchange.fetch_balance()
            krw = balance['total']['KRW']
            btc = balance['total']['BTC']
            price = ohlcv_list[-1][4]

            # 2) 자동 매수/매도
            if should_buy(ohlcv_list, current_params) and krw > price:
                order = exchange.create_market_buy_order(symbol, krw / price)
                logger.info(f"BUY executed: price={price}, amount={order['filled']}")
            elif should_sell(ohlcv_list, current_params) and btc > 0:
                order = exchange.create_market_sell_order(symbol, btc)
                logger.info(f"SELL executed: price={price}, amount={order['filled']}")
            else:
                # 포지션 상태 로깅
                if btc > 0:
                    logger.info("HOLDING position.")
                else:
                    logger.info("IDLE (no position).")

        except Exception as e:
            logger.error(f"Error in main loop: {e}")

        # timeframe에 맞춰 대기 (예: '1h' → 3600초)
        unit = cfg['timeframe'][-1]
        amount = int(cfg['timeframe'][:-1])
        sleep_secs = amount * (3600 if unit == 'h' else 60)
        logger.info(f"Waiting for next cycle ({sleep_secs} seconds)...")
        time.sleep(sleep_secs)

if __name__ == "__main__":
    run_bot()
