#bot.py
import ccxt, time, json, logging, requests
import pandas as pd
from backtest import optimize_params
from strategy import should_buy, should_sell, is_uptrend

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
    """Slack 알림 전송"""
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
            logger.warning(f"캔들 데이터 로딩 실패 (시도 {attempt}): {e}")
            if attempt == MAX_RETRIES:
                logger.error("최대 재시도 초과. 예외 발생.")
                raise
            time.sleep(backoff)
            backoff *= 2

def run_bot():
    logger.info("=== 봇 시작됨 ===")
    current_params = None
    entry_price = None

    while True:
        try:
            # 데이터 로드 & 최적화
            raw = fetch_ohlcv_with_retry()
            df = pd.DataFrame(raw, columns=['timestamp','open','high','low','close','volume'])
            logger.info("EMA 파라미터 백테스트 중...")
            params = optimize_params(df, initial_capital)
            if params != current_params:
                current_params = params
                logger.info(f"새 EMA 파라미터: {current_params}")
                notify_slack(f"🔧 새 EMA 파라미터 적용됨: `{current_params}`")

            ohlcv = df.values.tolist()
            bal = exchange.fetch_balance()
            krw = bal['total']['KRW']
            btc = bal['total']['BTC']
            price = ohlcv[-1][4]

            # 이 부분 추가
            ema_short = int(params['ema_short'])
            ema_long = int(params['ema_long'])
            short_ma = df['close'].ewm(span=ema_short).mean().iloc[-1]
            long_ma = df['close'].ewm(span=ema_long).mean().iloc[-1]

            # 손절 체크
            if entry_price and btc > 0:
                if (price - entry_price) / entry_price <= -0.03:
                    order = exchange.create_market_sell_order(symbol, btc)
                    msg = f"⚠️ 손절 매도: 진입가 {entry_price:.0f} → 현재가 {price:.0f}원, 손실률 {(price - entry_price) / entry_price:.2%}"
                    logger.info(msg)
                    notify_slack(msg)
                    btc = 0
                    entry_price = None
                    time.sleep(1)
                    continue

            # 매수 조건
            if should_buy(ohlcv, current_params) and krw > price:
                amount = (krw / price) * (1 - FEE_RATE)
                order = exchange.create_market_buy_order(symbol, amount)
                entry_price = price * (1 + FEE_RATE)
                msg = f"🚀 매수 실행됨: 가격 {price:.0f}원, 수량 {order['filled']:.6f} BTC"
                logger.info(msg)
                notify_slack(msg)

            # 매도 조건
            elif should_sell(ohlcv, current_params) and btc > 0:
                profit = (price - entry_price) / entry_price
                if profit >= 0.0008:  # 0.08%
                    if is_uptrend(df):
                        logger.info("📈 상승 추세: 매도 보류")
                        notify_slack("📈 상승 추세로 인해 매도 보류")
                    else:
                        order = exchange.create_market_sell_order(symbol, btc)
                        msg = f"✅ 매도 실행됨: 가격 {price:.0f}원, 수익률 {profit:.2%}, 수량 {order['filled']:.6f} BTC"
                        logger.info(msg)
                        notify_slack(msg)
                        btc = 0
                        entry_price = None
                else:
                    logger.info(f"📉 수익률 {profit:.2%}으로 매도 조건 미충족")

            # 보유 상태(HOLDING)
            elif btc > 0:
                expected_profit = price * btc * (1 - FEE_RATE)
                logger.info(f"🔒 보유 중: 현재가={price:.0f}원, 보유량={btc:.6f}, 예상 매도금액 ≈ {expected_profit:,.0f}원")
                notify_slack(f"🔒 HOLDING: 현재가 {price:,.0f}원 / 보유 {btc:.6f} BTC → 예상 매도금액 ≈ {expected_profit:,.0f}원")

            # 대기 상태(IDLE)
            else:
                desired_entry = long_ma
                diff_ratio = (price - desired_entry) / desired_entry
                possible_amount = (krw / price) * (1 - FEE_RATE)
                msg = f"⏳ 대기 중: 진입 희망가 ≈ EMA_long {desired_entry:,.0f}원, 현재가 {price:,.0f}원 ({diff_ratio:.2%})\n구매 가능 수량 ≈ {possible_amount:.6f} BTC"
                logger.info(msg)
                notify_slack(msg)

        except Exception as e:
            logger.error(f"메인 루프 에러: {e}")
            notify_slack(f"❌ 봇 오류 발생: {e}")

        logger.info(f"{INTERVAL}초 동안 대기...")
        time.sleep(INTERVAL)

if __name__ == "__main__":
    run_bot()
