import numpy as np

def is_uptrend(df):
    """
    최근 5개 종가(close)로 ‘상승 추세’인지 판단하는 함수.

    매개변수
    --------
    df : pandas.DataFrame
        반드시 'close' 컬럼을 포함한 OHLCV 데이터프레임.
    
    반환값
    ------
    bool
        연속된 최근 5개 종가가 모두 이전보다 큰지(True) 여부.
    """
    recent = df['close'].tail(5)  
    # zip(recent, recent[1:])로 pairwise 비교 → 모두 상승이면 추세 상승
    return all(x < y for x, y in zip(recent, recent[1:]))

def calculate_ema(closes, period):
    """
    지수이동평균(EMA) 계산 함수.

    EMA 원리
    --------
    EMA_t = α * Price_t + (1 − α) * EMA_{t−1}
    여기서 α = 2 / (period + 1)
    과거 가격보다 최근 가격에 더 높은 가중치를 부여.

    매개변수
    --------
    closes : list of float
        계산 대상 종가 리스트(시간순 정렬).
    period : int
        EMA 기간(예: 3, 7, 20 등).

    반환값
    ------
    float
        리스트 전체에 대해 계산된 최신 EMA 값.
    """
    alpha = 2 / (period + 1)
    ema = closes[0]  # 첫 EMA 초기값은 첫 종가로 설정
    for price in closes[1:]:
        ema = alpha * price + (1 - alpha) * ema
    return ema

def should_buy(data, params):
    """
    매수(골든 크로스) 시그널 판단.

    골든 크로스 원리
    -------------
    - 단기 EMA(prev_s → curr_s)가 장기 EMA(prev_l → curr_l)를 아래에서 위로
      교차할 때(True → False → True), 즉 ‘prev_s < prev_l and curr_s > curr_l’.

    매개변수
    --------
    data : list of lists
        OHLCV 데이터. 각 원소 [ts, open, high, low, close, vol].
    params : dict
        {'ema_short': 단기 EMA 기간, 'ema_long': 장기 EMA 기간}.

    반환값
    ------
    bool
        골든 크로스 발생 시 True.
    """
    closes = [c[4] for c in data]
    es, el = params['ema_short'], params['ema_long']

    # 이전 시점 EMA
    prev_s = calculate_ema(closes[:-1], es)
    prev_l = calculate_ema(closes[:-1], el)
    # 현재 시점 EMA
    curr_s = calculate_ema(closes,    es)
    curr_l = calculate_ema(closes,    el)

    # 골든 크로스: 단기EMA가 장기EMA를 하회하다가 상회
    return (prev_s < prev_l) and (curr_s > curr_l)

def should_sell(data, params):
    """
    매도(데드 크로스) 시그널 판단.

    데드 크로스 원리
    -------------
    - 단기 EMA(prev_s → curr_s)가 장기 EMA(prev_l → curr_l)를 위에서 아래로
      교차할 때(True → False → True), 즉 ‘prev_s > prev_l and curr_s < curr_l’.

    매개변수
    --------
    data : list of lists
        OHLCV 데이터. 각 원소 [ts, open, high, low, close, vol].
    params : dict
        {'ema_short': 단기 EMA 기간, 'ema_long': 장기 EMA 기간}.

    반환값
    ------
    bool
        데드 크로스 발생 시 True.
    """
    closes = [c[4] for c in data]
    es, el = params['ema_short'], params['ema_long']

    prev_s = calculate_ema(closes[:-1], es)
    prev_l = calculate_ema(closes[:-1], el)
    curr_s = calculate_ema(closes,    es)
    curr_l = calculate_ema(closes,    el)

    # 데드 크로스: 단기EMA가 장기EMA를 상회하다가 하회
    return (prev_s > prev_l) and (curr_s < curr_l)

def calculate_rsi(closes, period):
    # RSI 계산: 평균 상승/하락 비율 기반
    deltas = np.diff(closes)
    seed = deltas[:period]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    rs = up / down if down != 0 else np.inf
    rsi = 100 - (100 / (1 + rs))
    for delta in deltas[period:]:
        upval = max(delta, 0)
        downval = abs(min(delta, 0))
        up = (up * (period - 1) + upval) / period
        down = (down * (period - 1) + downval) / period
        rs = up / down if down != 0 else np.inf
        rsi = 100 - (100 / (1 + rs))
    return rsi