# bot.py
import ccxt, time, json, logging, requests
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

# --- 설정 로드 ---
with open('config.json') as f:
    cfg = json.load(f)

exchange = ccxt.bithumb({
    'apiKey': cfg['apiKey'],
    'secret': cfg['secret'],
    'enableRateLimit': True
})
symbol        = cfg['symbol']
initial_cap   = cfg['initial_capital']
FEE_RATE      = 0.0004
MIN_PROFIT    = FEE_RATE * 2   # 최소 목표 이익 (예: 0.08%)
MAX_RETRIES   = 3
BACKTEST_LIM  = cfg['backtest_limit']
TIMEFRAME     = cfg['timeframe']
INTERVAL_SEC  = cfg.get('interval_seconds', 600)
SLACK_WEBHOOK = cfg.get('slack_webhook_url')

def notify_slack(msg: str):
    if not SLACK_WEBHOOK: return
    try:
        r = requests.post(SLACK_WEBHOOK, json={"text": msg})
        if r.status_code != 200:
            logger.error(f"Slack notify failed: {r.status_code} {r.text}")
    except Exception as e:
        logger.error(f"Slack error: {e}")

def fetch_ohlcv():
    backoff = 1.0
    for i in range(1, MAX_RETRIES+1):
        try:
            return exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=BACKTEST_LIM)
        except Exception as e:
            logger.warning(f"OHLCV fail {i}/{MAX_RETRIES}: {e}")
            time.sleep(backoff); backoff *= 2
    raise RuntimeError("fetch_ohlcv failed")

def run_bot():
    logger.info("=== Bot Started ===")
    params, entry_price, in_position = None, None, False

    while True:
        try:
            raw = fetch_ohlcv()
            df  = pd.DataFrame(raw, columns=['ts','o','h','l','c','v'])
            # 1) 최적 파라미터
            new_p = optimize_params(df, initial_cap)
            if new_p != params:
                params = new_p
                msg = f":gear: New EMA params: `{params}`"
                logger.info(msg); notify_slack(msg)

            ohlcv = df.values.tolist()
            bal   = exchange.fetch_balance()
            krw   = bal['total']['KRW']
            btc   = bal['total']['BTC']
            price = ohlcv[-1][4]

            # 2) 매수
            if should_buy(ohlcv, params) and not in_position and krw > price:
                amt = (krw / price) * (1 - FEE_RATE)
                order = exchange.create_market_buy_order(symbol, amt)
                entry_price, in_position = price * (1 + FEE_RATE), True
                msg = f":rocket: BUY @ {price:.0f} KRW | amt {order['filled']:.6f}"
                logger.info(msg); notify_slack(msg)

            # 3) 청산: 신호 or profit target
            elif in_position:
                sell_signal = should_sell(ohlcv, params)
                profit = (price - entry_price) / entry_price
                if sell_signal or profit >= MIN_PROFIT:
                    order = exchange.create_market_sell_order(symbol, btc)
                    reason = "SELL signal" if sell_signal else "Profit target"
                    msg = f":white_check_mark: SELL ({reason}) @ {price:.0f} KRW | P/L {profit:.2%}"
                    logger.info(msg); notify_slack(msg)
                    in_position, entry_price = False, None

            # 4) 상태 알림
            if not in_position:
                msg = (f":hourglass: IDLE | "
                       f"KRW={krw:.0f}, Price={price:.0f}, "
                       f"Next buy on EMA_cross")
            else:
                profit = (price - entry_price) / entry_price
                msg = (f":hourglass_flowing_sand: HOLDING | "
                       f"Entry={entry_price:.0f}, Now={price:.0f}, P/L={profit:.2%}")
            logger.info(msg); notify_slack(msg)

        except Exception as e:
            msg = f":x: Bot Error: {e}"
            logger.error(msg); notify_slack(msg)

        time.sleep(INTERVAL_SEC)

if __name__ == "__main__":
    run_bot()
