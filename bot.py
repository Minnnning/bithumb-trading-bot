import ccxt, time, json, logging, requests, math
import pandas as pd
from backtest import optimize_params
from strategy import should_buy, should_sell, is_uptrend, calculate_ema

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
    'apiKey':         cfg['apiKey'],
    'secret':         cfg['secret'],
    'enableRateLimit': True,
})
exchange.load_markets()

symbol           = cfg['symbol']             # ex. "ETH/KRW"
base_curr, quote_curr = symbol.split('/')    # 코인/KRW
INITIAL_CAP      = cfg['initial_capital']
FEE_RATE         = 0.0004                    # 0.04%
MIN_PROFIT       = FEE_RATE * 2              # 0.08%
STOP_LOSS        = -0.03                     # -3%
BACKTEST_LIM     = cfg['backtest_limit']
TIMEFRAME        = cfg['timeframe']
INTERVAL_SEC     = cfg['interval_seconds']
SLACK_WEBHOOK    = cfg.get('slack_webhook_url')
amount_decimals = 8                            # 소수점 8자리 고정
prec_factor     = 10 ** amount_decimals
MIN_PURCHASE_KRW = cfg.get('min_purchase_krw', 10000)  # 최소 구매 KRW 기준


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
            time.sleep(backoff); backoff *= 2
    raise RuntimeError("fetch_ohlcv 실패")


def run_bot():
    logger.info("=== 트레이딩 봇 시작 ===")
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
                notify_slack(f"🔧 EMA 파라미터 업데이트: `{params}`")

            price       = df['close'].iat[-1]
            min_units   = MIN_PURCHASE_KRW / price

            bal         = exchange.fetch_balance()
            quote_bal   = float(bal['free'].get(quote_curr, 0))
            base_bal    = float(bal['free'].get(base_curr,  0))

            closes      = [c[4] for c in ohlcv]
            es, el      = int(params['ema_short']), int(params['ema_long'])
            ema_s       = calculate_ema(closes, es)
            ema_l       = calculate_ema(closes, el)
            diff_pct    = (ema_s - ema_l) / ema_l

            # 1) 포지션 중이면 매도/손절 분기
            if in_position:
                base_bal = float(exchange.fetch_balance()['free'].get(base_curr, 0))
                profit   = (price - entry_price) / entry_price

                logger.info(
                    f"[HOLDING] EMA_s={ema_s:.0f}, EMA_l={ema_l:.0f}, 차이={diff_pct:.2%}, P/L={profit:.2%}"
                )

                do_sell = False
                sell_reason = ''
                if base_bal > 0 and profit <= STOP_LOSS:
                    do_sell = True; sell_reason = '손절'
                elif base_bal > 0 and should_sell(ohlcv, params):
                    do_sell = True; sell_reason = '알고리즘 시그널'
                elif base_bal > 0 and profit >= MIN_PROFIT and not is_uptrend(df):
                    do_sell = True; sell_reason = '수익목표'
                elif base_bal > 0 and profit >= MIN_PROFIT and is_uptrend(df):
                    logger.info("📈 상승추세 감지: 매도 보류")

                if do_sell:
                    sell_amount = round(base_bal, amount_decimals)
                    try:
                        order = exchange.create_order(
                            symbol=symbol,
                            type='market',
                            side='sell',
                            amount=float(sell_amount),
                        )
                        notify_slack(
                            f"✅ 매도({sell_reason}): {order['filled']:.8f}{base_curr} @ {order['average']:.0f}KRW (P/L {profit:.2%})"
                        )
                        in_position = False
                    except Exception as e:
                        logger.error(f"매도 주문 에러: {e}")
                        notify_slack(f"❌ 매도 실패: {e}")
                time.sleep(INTERVAL_SEC)
                continue

            # 2) 포지션 없으면 매수 분기
            if should_buy(ohlcv, params) or ema_s > ema_l:
                usable_krw = quote_bal * 0.7
                raw_units  = usable_krw / price
                steps      = math.floor(raw_units * prec_factor)
                units      = round(steps / prec_factor, amount_decimals)

                logger.info(
                    f"[매수 시도] 잔고={quote_bal:.0f}KRW, 예상수량={units:.8f}{base_curr}, EMA_s={ema_s:.0f}, EMA_l={ema_l:.0f}, 차이= {diff_pct:.2%}"
                )

                if units >= min_units:
                    try:
                        order = exchange.create_order(
                            symbol=symbol,
                            type='market',
                            side='buy',
                            amount=float(units),
                        )
                        new_base = exchange.fetch_balance()[base_curr]['free']
                        filled   = new_base - quote_bal 
                        # 2) cost는 price * filled
                        spent_krw = filled * price
                        entry_price = price
                        
                        in_position = True
                        logger.info(
                            f"🚀 매수 체결: {filled:.8f}{base_curr} @ {entry_price:.0f}KRW (지출 {spent_krw:.0f}KRW)"
                        )
                        notify_slack(
                            f"🚀 매수 체결: {filled:.8f}{base_curr} @ {entry_price:.0f}KRW (지출 {spent_krw:.0f}KRW)"
                        )
                    except Exception as e:
                        logger.error(f"매수 주문 에러: {e}")
                        notify_slack(f"❌ 매수 실패: {e}")
                else:
                    logger.info(f"⚠️ 매수 스킵: 최소 구매 단위 미달 ({units:.8f} < {min_units:.8f})")
                time.sleep(INTERVAL_SEC)
                continue

            # 3) IDLE 상태
            logger.info(f"[IDLE] EMA_s={ema_s:.0f}, EMA_l={ema_l:.0f}, 차이={diff_pct:.2%}")
            time.sleep(INTERVAL_SEC)

        except Exception as e:
            logger.error(f"봇 루프 에러: {e}")
            notify_slack(f"❌ 봇 오류: {e}")
            time.sleep(INTERVAL_SEC)

if __name__ == "__main__":
    run_bot()
