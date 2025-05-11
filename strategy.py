import numpy as np

def calculate_ema(closes, period):
    alpha = 2 / (period + 1)
    ema = closes[0]
    for price in closes[1:]:
        ema = alpha * price + (1 - alpha) * ema
    return ema

def calculate_rsi(closes, period):
    deltas = np.diff(closes)
    ups = np.where(deltas > 0, deltas, 0)
    downs = np.where(deltas < 0, -deltas, 0)
    avg_up = np.mean(ups[:period])
    avg_down = np.mean(downs[:period])
    rs = avg_up / (avg_down + 1e-8)
    return 100 - (100 / (1 + rs))

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
        tr.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        ))
        up = highs[i] - highs[i-1]
        down = lows[i-1] - lows[i]
        plus_dm.append(up if up > down and up > 0 else 0)
        minus_dm.append(down if down > up and down > 0 else 0)
    atr = np.mean(tr[-period:])
    pdi = 100 * (np.mean(plus_dm[-period:]) / atr)
    mdi = 100 * (np.mean(minus_dm[-period:]) / atr)
    dx  = 100 * (abs(pdi - mdi) / (pdi + mdi + 1e-8))
    return np.mean([dx])

def detect_three_down_rebound(closes):
    """
    마지막 4봉 중에
    - 3봉 연속 하락 (c3 < c2 < c1 < c0)
    - 그 다음 봉이 반등 (c0 < c_next)
    """
    if len(closes) < 4:
        return False
    return (closes[-4] > closes[-3] > closes[-2] > closes[-1] and
            closes[-1] < closes[-0] and
            closes[-0] > closes[-1])

def detect_three_up_drop(closes):
    """
    마지막 4봉 중에
    - 3봉 연속 상승
    - 그 다음 봉이 하락
    """
    if len(closes) < 4:
        return False
    return (closes[-4] < closes[-3] < closes[-2] < closes[-1] and
            closes[-1] > closes[-0] and
            closes[-0] < closes[-1])

def should_buy(data, params):
    closes = [c[4] for c in data]
    highs  = [c[2] for c in data]
    lows   = [c[3] for c in data]

    # 1) EMA 크로스
    ema_s_prev = calculate_ema(closes[:-1], params['ema_short'])
    ema_l_prev = calculate_ema(closes[:-1], params['ema_long'])
    ema_s_now  = calculate_ema(closes,     params['ema_short'])
    ema_l_now  = calculate_ema(closes,     params['ema_long'])
    ema_cross  = (ema_s_prev < ema_l_prev) and (ema_s_now > ema_l_now)

    # 2) MACD > 0
    macd_pos = calculate_macd(closes, params['macd_fast'], params['macd_slow']) > 0

    # 3) RSI 과매도 해제
    rsi = calculate_rsi(closes, params['rsi_period'])
    rsi_ok = rsi < params['rsi_buy_thresh']

    # 4) Bollinger Bands 하단 위
    _, _, lower = calculate_bollinger(closes, params['bb_period'])
    bb_ok = closes[-1] > lower

    # 5) ADX > threshold
    adx_ok = calculate_adx(highs, lows, closes, params['adx_period']) > params['adx_thresh']

    # 6) 추가 필터: 3번 연속 하락 후 반등 패턴
    pattern_ok = detect_three_down_rebound(closes)

    return all([ema_cross, macd_pos, rsi_ok, bb_ok, adx_ok, pattern_ok])

def should_sell(data, params):
    closes = [c[4] for c in data]
    highs  = [c[2] for c in data]
    lows   = [c[3] for c in data]

    # 1) EMA 크로스 다운
    ema_s_prev = calculate_ema(closes[:-1], params['ema_short'])
    ema_l_prev = calculate_ema(closes[:-1], params['ema_long'])
    ema_s_now  = calculate_ema(closes,     params['ema_short'])
    ema_l_now  = calculate_ema(closes,     params['ema_long'])
    ema_cross_down = (ema_s_prev > ema_l_prev) and (ema_s_now < ema_l_now)

    # 2) MACD < 0
    macd_neg = calculate_macd(closes, params['macd_fast'], params['macd_slow']) < 0

    # 3) RSI 과매수
    rsi = calculate_rsi(closes, params['rsi_period'])
    rsi_over = rsi > params['rsi_sell_thresh']

    # 4) Bollinger Bands 상단 근처
    upper, _, _ = calculate_bollinger(closes, params['bb_period'])
    bb_over = closes[-1] >= upper

    # 5) ADX > threshold
    adx_ok = calculate_adx(highs, lows, closes, params['adx_period']) > params['adx_thresh']

    # 6) 추가 필터: 3번 연속 상승 후 하락 패턴
    pattern_ok = detect_three_up_drop(closes)

    return all([ema_cross_down, macd_neg, rsi_over, bb_over, adx_ok, pattern_ok])
