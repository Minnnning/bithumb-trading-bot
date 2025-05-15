import ccxt, time, json, logging, requests, math
import pandas as pd
import numpy as np
from backtest import optimize_params
from strategy import should_buy, should_sell, is_uptrend, calculate_ema, calculate_rsi

# ─── 로깅 설정 ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger()

# ─── 설정 로드 ─────────────────────────────────────────────
with open('config.json') as f:
    cfg = json.load(f)

exchange = ccxt.bithumb({
    'apiKey': cfg['apiKey'],
    'secret': cfg['secret'],
    'enableRateLimit': True,
})
exchange.load_markets()

symbol             = cfg['symbol']
base_curr, quote_curr = symbol.split('/')
INITIAL_CAP        = cfg['initial_capital']
FEE_RATE           = 0.0004
MIN_PROFIT         = FEE_RATE * 10
STOP_LOSS          = -0.03
BACKTEST_LIM       = cfg['backtest_limit']
TIMEFRAME          = cfg['timeframe']
INTERVAL_SEC       = cfg['interval_seconds']
SLACK_WEBHOOK      = cfg.get('slack_webhook_url')
amount_decimals    = 8
prec_factor        = 10 ** amount_decimals
MIN_PURCHASE_KRW   = cfg.get('min_purchase_krw', 10000)


def notify_slack(msg: str):
    if not SLACK_WEBHOOK:
        return
    try:
        resp = requests.post(SLACK_WEBHOOK, json={"text": msg})
        if resp.status_code != 200:
            logger.error(f"Slack 알림 실패: {resp.status_code} {resp.text}")
    except Exception as e:
        logger.error(f"Slack 전송 에러: {e}")


def fetch_ohlcv():
    backoff = 1.0
    for i in range(1, 4):
        try:
            data = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=BACKTEST_LIM)
            return pd.DataFrame(data, columns=['ts','open','high','low','close','vol'])
        except Exception as e:
            logger.warning(f"OHLCV 로드 실패 ({i}/3): {e}")
            time.sleep(backoff)
            backoff *= 2
    raise RuntimeError("fetch_ohlcv 실패")

def run_bot():
    notify_slack("=== 트레이딩 봇 시작 ===")
    params      = None
    entry_price = None
    in_position = False

    while True:
        try:
            df      = fetch_ohlcv()
            ohlcv   = df.values.tolist()
            new_p   = optimize_params(df, INITIAL_CAP)
            if new_p != params:
                params = new_p
                logger.info(f"🔧 EMA 파라미터 업데이트: `{params}`")

            closes   = df['close'].tolist()
            price    = closes[-1]
            rsi      = calculate_rsi(closes, int(params['rsi_period']))
            min_units = MIN_PURCHASE_KRW / price

            bal       = exchange.fetch_balance()
            quote_bal = float(bal['free'].get(quote_curr, 0))
            base_bal  = float(bal['free'].get(base_curr,  0))

            es, el    = int(params['ema_short']), int(params['ema_long'])
            ema_s     = calculate_ema(closes, es)
            ema_l     = calculate_ema(closes, el)
            diff_pct  = (ema_s - ema_l) / ema_l

            # 1) 포지션 중이면 매도/손절 분기
            if in_position:
                prev_quote = quote_bal
                prev_base  = base_bal
                profit     = (price - entry_price) / entry_price

                logger.info(
                    f"[HOLDING] EMA_s={ema_s:.0f}, EMA_l={ema_l:.0f}, RSI={rsi:.1f}, P/L={profit:.2%}"
                )

                do_sell = False
                sell_reason = ''
                if prev_base > 0 and profit <= STOP_LOSS:
                    do_sell, sell_reason = True, '손절'
                elif prev_base > 0 and should_sell(ohlcv, params):
                    do_sell, sell_reason = True, '알고리즘 시그널'
                elif prev_base > 0 and profit >= MIN_PROFIT and not is_uptrend(df):
                    do_sell, sell_reason = True, '수익목표'
                elif prev_base > 0 and profit >= MIN_PROFIT and is_uptrend(df):
                    logger.info("📈 상승추세 감지: 매도 보류")

                if do_sell:
                    sell_amount = round(prev_base, amount_decimals)
                    order = exchange.create_market_sell_order(symbol, sell_amount)
                    post = exchange.fetch_balance()
                    filled     = prev_base - float(post['free'].get(base_curr, 0))
                    sold_krw   = float(post['free'].get(quote_curr, 0)) - prev_quote
                    profit_amt = sold_krw - (entry_price * filled)

                    logger.info(
                        f"✅ 매도({sell_reason}): {filled:.8f}{base_curr} @ {price:.0f}KRW | P/L={profit:.2%}, 이익={profit_amt:.0f}KRW"
                    )
                    notify_slack(
                        f"✅ 매도({sell_reason}): {filled:.8f}{base_curr} @ {price:.0f}KRW | P/L={profit:.2%}, 이익={profit_amt:.0f}KRW"
                    )
                    in_position = False
                time.sleep(INTERVAL_SEC)
                continue

            # 2) 포지션 없으면 매수 분기 (EMA 골든 크로스 + RSI 필터)
            if (should_buy(ohlcv, params) or ema_s > ema_l) and rsi < int(params['rsi_threshold']):
                usable_krw = quote_bal * 0.7
                raw_units  = usable_krw / price
                steps      = math.floor(raw_units * prec_factor)
                units      = round(steps / prec_factor, amount_decimals)

                logger.info(
                    f"[매수 시도] 잔고={quote_bal:.0f}KRW, 예상수량={units:.8f}{base_curr}, RSI={rsi:.1f}, EMA_cross_diff={diff_pct:.2%}"
                )

                if units >= min_units:
                    prev = exchange.fetch_balance()
                    order = exchange.create_market_buy_order(symbol, units)
                    post = exchange.fetch_balance()
                    filled     = float(post['free'].get(base_curr, 0)) - prev['free'].get(base_curr, 0)
                    spent_krw  = prev['free'].get(quote_curr, 0) - float(post['free'].get(quote_curr, 0))
                    entry_price = price

                    logger.info(
                        f"🚀 매수 체결: {filled:.8f}{base_curr} @ {price:.0f}KRW | 지출={spent_krw:.0f}KRW"
                    )
                    notify_slack(
                        f"🚀 매수 체결: {filled:.8f}{base_curr} @ {price:.0f}KRW | 지출={spent_krw:.0f}KRW"
                    )
                    in_position = True
                else:
                    logger.info(f"⚠️ 매수 스킵: 최소 구매 단위 미달 ({units:.8f} < {min_units:.8f})")
                time.sleep(INTERVAL_SEC)
                continue

            # 3) IDLE 상태
            logger.info(
                f"[IDLE] EMA_s={ema_s:.0f}, EMA_l={ema_l:.0f}, RSI={rsi:.1f}, EMA_diff={diff_pct:.2%}"
            )
            time.sleep(INTERVAL_SEC)

        except Exception as e:
            logger.error(f"봇 루프 에러: {e}")
            notify_slack(f"❌ 봇 오류: {e}")
            time.sleep(INTERVAL_SEC)

if __name__ == "__main__":
    run_bot()
