import numpy as np

def calculate_ema(closes, period):
    alpha = 2/(period+1)
    ema = closes[0]
    for price in closes[1:]:
        ema = alpha * price + (1-alpha) * ema
    return ema

def calculate_rsi(closes, period):
    deltas = np.diff(closes)
    ups = np.where(deltas>0, deltas, 0)
    downs = np.where(deltas<0, -deltas, 0)
    avg_up = np.mean(ups[:period])
    avg_down = np.mean(downs[:period])
    rs = avg_up / (avg_down + 1e-8)
    return 100 - (100/(1+rs))

def calculate_macd(closes, fast, slow):
    ema_fast = calculate_ema(closes[-fast*3:], fast)
    ema_slow = calculate_ema(closes[-slow*3:], slow)
    return ema_fast - ema_slow

def calculate_bollinger(closes, period):
    mid = np.mean(closes[-period:])
    std = np.std(closes[-period:])
    return mid + 2*std, mid, mid - 2*std

def calculate_adx(highs, lows, closes, period):
    tr, plus_dm, minus_dm = [], [], []
    for i in range(1, len(closes)):
        tr.append(max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])))
        up = highs[i]-highs[i-1]; down = lows[i-1]-lows[i]
        plus_dm.append(up if up>down and up>0 else 0)
        minus_dm.append(down if down>up and down>0 else 0)
    atr = np.mean(tr[-period:])
    pdi = 100*(np.mean(plus_dm[-period:])/atr)
    mdi = 100*(np.mean(minus_dm[-period:])/atr)
    dx  = 100*(abs(pdi-mdi)/(pdi+mdi+1e-8))
    return np.mean([dx])

def should_buy(data, params):
    closes = [c[4] for c in data]
    highs  = [c[2] for c in data]
    lows   = [c[3] for c in data]

    # EMA 크로스
    ema_s_prev = calculate_ema(closes[:-1], params['ema_short'])
    ema_l_prev = calculate_ema(closes[:-1], params['ema_long'])
    ema_s_now  = calculate_ema(closes, params['ema_short'])
    ema_l_now  = calculate_ema(closes, params['ema_long'])
    ema_cross  = (ema_s_prev < ema_l_prev) and (ema_s_now > ema_l_now)

    # MACD positive
    macd_pos = calculate_macd(closes, params['macd_fast'], params['macd_slow']) > 0

    # RSI < buy_thresh
    rsi = calculate_rsi(closes, params['rsi_period'])
    rsi_ok = rsi < params['rsi_buy_thresh']

    # Bollinger: 가격 > lower
    _, _, lower = calculate_bollinger(closes, params['bb_period'])
    bb_ok = closes[-1] > lower

    # ADX > thresh
    adx_ok = calculate_adx(highs, lows, closes, params['adx_period']) > params['adx_thresh']

    return ema_cross and macd_pos and rsi_ok and bb_ok and adx_ok

def should_sell(data, params):
    closes = [c[4] for c in data]
    highs  = [c[2] for c in data]
    lows   = [c[3] for c in data]

    ema_s_prev = calculate_ema(closes[:-1], params['ema_short'])
    ema_l_prev = calculate_ema(closes[:-1], params['ema_long'])
    ema_s_now  = calculate_ema(closes, params['ema_short'])
    ema_l_now  = calculate_ema(closes, params['ema_long'])
    ema_cross_down = (ema_s_prev > ema_l_prev) and (ema_s_now < ema_l_now)

    macd_neg = calculate_macd(closes, params['macd_fast'], params['macd_slow']) < 0

    rsi = calculate_rsi(closes, params['rsi_period'])
    rsi_over = rsi > params['rsi_sell_thresh']

    upper, _, _ = calculate_bollinger(closes, params['bb_period'])
    bb_over = closes[-1] >= upper

    adx_ok = calculate_adx(highs, lows, closes, params['adx_period']) > params['adx_thresh']

    return ema_cross_down and macd_neg and rsi_over and bb_over and adx_ok
