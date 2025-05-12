#boy.py
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

exchange      = ccxt.bithumb({
    'apiKey': cfg['apiKey'],
    'secret': cfg['secret'],
    'enableRateLimit': True
})
symbol        = cfg['symbol']              # e.g. "BTC/KRW", "ETH/KRW", "XRP/KRW" 등
quote_curr, base_curr = symbol.split('/')  # quote="BTC", base="KRW" 순서 주의!
# Bithumb CCXT symbol is "BTC/KRW", so left가 base(코인), right가 quote(법정화폐)
base_currency, quote_currency = symbol.split('/')  
# 예: base_currency="BTC", quote_currency="KRW"

initial_cap   = cfg['initial_capital']
FEE_RATE      = 0.0004
MAX_RETRIES   = 3
BACKTEST_LIM  = cfg['backtest_limit']
TIMEFRAME     = cfg['timeframe']
INTERVAL_SEC  = cfg['interval_seconds']
SLACK_WEBHOOK = cfg.get('slack_webhook_url')
BUY_TOL       = cfg.get('buy_tolerance', 0.001)
SELL_TOL      = cfg.get('sell_tolerance', 0.001)

def notify_slack(msg: str):
    if not SLACK_WEBHOOK:
        return
    try:
        r = requests.post(SLACK_WEBHOOK, json={"text": msg})
        if r.status_code != 200:
            logger.error(f"Slack 알림 실패: {r.status_code} {r.text}")
    except Exception as e:
        logger.error(f"Slack 전송 에러: {e}")

def fetch_ohlcv():
    backoff = 1.0
    for attempt in range(1, MAX_RETRIES+1):
        try:
            data = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=BACKTEST_LIM)
            return pd.DataFrame(data, columns=['ts','open','high','low','close','vol'])
        except Exception as e:
            logger.warning(f"OHLCV 로드 실패 ({attempt}/{MAX_RETRIES}): {e}")
            time.sleep(backoff)
            backoff *= 2
    raise RuntimeError("fetch_ohlcv 실패")

def run_bot():
    logger.info("=== 트레이딩 봇 시작 ===")
    params = None
    entry_price = None
    in_position = False

    while True:
        try:
            # 1) 데이터 & 파라미터 최적화
            df = fetch_ohlcv()
            new_p = optimize_params(df, initial_cap)
            if new_p != params:
                params = new_p
                notify_slack(f"🔧 새 EMA 파라미터: `{params}`")

            # 2) 잔고 조회
            bal = exchange.fetch_balance()
            quote_bal = bal['total'].get(quote_currency, 0)  # ex: KRW
            base_bal  = bal['total'].get(base_currency,  0)  # ex: BTC

            price = df['close'].iloc[-1]
            es = int(params['ema_short'])
            el = int(params['ema_long'])
            short_ma = df['close'].ewm(span=es).mean().iloc[-1]
            long_ma  = df['close'].ewm(span=el).mean().iloc[-1]

            # 3) 매수: EMA 크로스 OR 가격이 EMA_long ± tol 범위 진입
            buy_signal   = should_buy(df.values.tolist(), params)
            in_buy_range = abs(price - long_ma) / long_ma <= BUY_TOL

            if not in_position and quote_bal > price and (buy_signal or in_buy_range):
                amount = (quote_bal / price) * (1 - FEE_RATE)
                order = exchange.create_market_buy_order(symbol, amount)
                entry_price = price * (1 + FEE_RATE)
                in_position = True
                msg = (f"🚀 매수: {symbol} {price:.0f} {quote_currency} | "
                       f"{order['filled']:.6f} {base_currency}")
                notify_slack(msg)

            # 4) 매도: EMA 크로스 OR 가격이 EMA_long ± tol 범위 진입 또는 손절/수익
            elif in_position:
                sell_signal   = should_sell(df.values.tolist(), params)
                in_sell_range = abs(price - long_ma) / long_ma <= SELL_TOL
                profit = (price - entry_price) / entry_price

                # 손절(-3%)
                if profit <= -0.03:
                    order = exchange.create_market_sell_order(symbol, base_bal)
                    msg = (f"⚠️ 손절매도: {symbol} {price:.0f} {quote_currency} | "
                           f"{base_bal:.6f} {base_currency}, 손실 {profit:.2%}")
                    notify_slack(msg)
                    in_position = False

                # 매도 신호 or 가격 범위 진입
                elif sell_signal or in_sell_range:
                    # 수익률 ≥ 0.08%이면서 상승 추세면 보류
                    if profit >= FEE_RATE*2 and is_uptrend(df):
                        notify_slack("📈 상승 추세로 매도 보류")
                    else:
                        order = exchange.create_market_sell_order(symbol, base_bal)
                        msg = (f"✅ 매도: {symbol} {price:.0f} {quote_currency} | "
                               f"{base_bal:.6f} {base_currency}, 수익률 {profit:.2%}")
                        notify_slack(msg)
                        in_position = False

            # 5) 상태 알림
            if not in_position:
                possible_amt = (quote_bal / price) * (1 - FEE_RATE)
                msg = (f"⏳ IDLE | {symbol} 현재가 {price:.0f} {quote_currency}, "
                       f"EMA_long {long_ma:.0f} {quote_currency} ±{BUY_TOL*100:.1f}% "
                       f"시장가 매수 가능 {possible_amt:.6f} {base_currency}")
            else:
                expect_sell = price * base_bal * (1 - FEE_RATE)
                msg = (f"🔒 HOLDING | {symbol} 진입가 {entry_price:.0f} {quote_currency}, "
                       f"현재 {price:.0f} {quote_currency}, 예상 매도금 ≈ {expect_sell:,.0f} {quote_currency}")
            notify_slack(msg)

        except Exception as e:
            notify_slack(f"❌ 봇 오류: {e}")
            logger.error(f"봇 루프 에러: {e}")

        time.sleep(INTERVAL_SEC)

if __name__ == "__main__":
    run_bot()
