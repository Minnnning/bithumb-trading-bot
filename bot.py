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
symbol = cfg['symbol']
initial_capital = cfg['initial_capital']
FEE_RATE = 0.0004
MAX_RETRIES = 3
INITIAL_BACKOFF = 1.0
INTERVAL = cfg.get('interval_seconds', 600)
SLACK_WEBHOOK = cfg.get('slack_webhook_url')

def notify_slack(message: str):
    """Slack Incoming Webhook 으로 알림 전송"""
    if not SLACK_WEBHOOK:
        return
    try:
        resp = requests.post(SLACK_WEBHOOK, json={"text": message})
        if resp.status_code != 200:
            logger.error(f"Slack 알림 실패: {resp.status_code} {resp.text}")
    except Exception as e:
        logger.error(f"Slack 전송 에러: {e}")

def fetch_ohlcv_with_retry():
    backoff = INITIAL_BACKOFF
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return exchange.fetch_ohlcv(symbol,
                                        timeframe=cfg['timeframe'],
                                        limit=cfg['backtest_limit'])
        except Exception as e:
            logger.warning(f"fetch_ohlcv failed (attempt {attempt}): {e}")
            if attempt == MAX_RETRIES:
                logger.error("최대 재시도 초과, 예외 발생")
                raise
            time.sleep(backoff)
            backoff *= 2

def run_bot():
    logger.info("=== Trading Bot Started ===")
    current_params = None
    entry_price = None

    while True:
        try:
            # 1) 데이터 로드 & 최적 파라미터
            raw = fetch_ohlcv_with_retry()
            df = pd.DataFrame(raw, columns=['ts','open','high','low','close','vol'])
            logger.info("Optimizing EMA params by backtest...")
            params = optimize_params(df, initial_capital)
            if params != current_params:
                current_params = params
                logger.info(f"New EMA params: {current_params}")
                notify_slack(f":gear: New EMA params: `{current_params}`")

            # 2) 현재 상태
            ohlcv = df.values.tolist()
            bal = exchange.fetch_balance()
            krw = bal['total']['KRW']
            btc = bal['total']['BTC']
            price = ohlcv[-1][4]

            # 3) 손절 체크 (진입가 대비 -3%)
            if entry_price and btc > 0:
                if (price - entry_price) / entry_price <= -0.03:
                    order = exchange.create_market_sell_order(symbol, btc)
                    msg = f":warning: STOP-LOSS SELL executed at {price:.0f} KRW (loss {(price-entry_price)/entry_price:.2%})"
                    logger.info(msg)
                    notify_slack(msg)
                    btc = 0
                    entry_price = None
                    time.sleep(1)
                    continue

            # 4) 매수/매도
            if should_buy(ohlcv, current_params) and krw > price:
                amount = (krw / price) * (1 - FEE_RATE)
                order = exchange.create_market_buy_order(symbol, amount)
                entry_price = price * (1 + FEE_RATE)
                msg = f":rocket: BUY executed at {price:.0f} KRW, amount {order['filled']:.6f} BTC"
                logger.info(msg)
                notify_slack(msg)

            elif should_sell(ohlcv, current_params) and btc > 0:
                order = exchange.create_market_sell_order(symbol, btc)
                msg = f":white_check_mark: SELL executed at {price:.0f} KRW, amount {order['filled']:.6f} BTC"
                logger.info(msg)
                notify_slack(msg)
                btc = 0
                entry_price = None

            else:
                state = "HOLDING" if btc > 0 else "IDLE"
                logger.info(f"{state}: price={price:.0f}, KRW={krw:.0f}, BTC={btc:.6f}")

        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            notify_slack(f":x: Bot Error: {e}")

        logger.info(f"Sleeping for {INTERVAL} seconds...")
        time.sleep(INTERVAL)

if __name__ == "__main__":
    run_bot()
