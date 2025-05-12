# strategy.py
import numpy as np

def calculate_ema(closes, period):
    alpha = 2 / (period + 1)
    ema = closes[0]
    for price in closes[1:]:
        ema = alpha * price + (1 - alpha) * ema
    return ema

def should_buy(data, params):
    closes = [c[4] for c in data]
    es, el = params['ema_short'], params['ema_long']

    prev_s = calculate_ema(closes[:-1], es)
    prev_l = calculate_ema(closes[:-1], el)
    curr_s = calculate_ema(closes,    es)
    curr_l = calculate_ema(closes,    el)

    return (prev_s < prev_l) and (curr_s > curr_l)

def should_sell(data, params):
    closes = [c[4] for c in data]
    es, el = params['ema_short'], params['ema_long']

    prev_s = calculate_ema(closes[:-1], es)
    prev_l = calculate_ema(closes[:-1], el)
    curr_s = calculate_ema(closes,    es)
    curr_l = calculate_ema(closes,    el)

    return (prev_s > prev_l) and (curr_s < curr_l)
