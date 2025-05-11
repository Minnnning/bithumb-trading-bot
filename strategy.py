# strategy.py
import numpy as np

def calculate_ema(closes, period):
    alpha = 2 / (period + 1)
    ema = closes[0]
    for price in closes[1:]:
        ema = alpha * price + (1 - alpha) * ema
    return ema

def should_buy(data, params):
    """
    EMA 단기(period=ema_short)가 EMA 장기(period=ema_long)를 상향 돌파할 때 매수
    """
    closes = [c[4] for c in data]
    es = params['ema_short']
    el = params['ema_long']

    prev_short = calculate_ema(closes[:-1], es)
    prev_long  = calculate_ema(closes[:-1], el)
    curr_short = calculate_ema(closes, es)
    curr_long  = calculate_ema(closes, el)

    return (prev_short < prev_long) and (curr_short > curr_long)

def should_sell(data, params):
    """
    EMA 단기(period=ema_short)가 EMA 장기(period=ema_long)를 하향 돌파할 때 매도
    """
    closes = [c[4] for c in data]
    es = params['ema_short']
    el = params['ema_long']

    prev_short = calculate_ema(closes[:-1], es)
    prev_long  = calculate_ema(closes[:-1], el)
    curr_short = calculate_ema(closes, es)
    curr_long  = calculate_ema(closes, el)

    return (prev_short > prev_long) and (curr_short < curr_long)
