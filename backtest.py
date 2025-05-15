import pandas as pd
from strategy import should_buy, should_sell, calculate_rsi

# EMA, RSI 파라미터 그리드
grid = {
    'ema_short':      [3, 5, 7],
    'ema_long':       [10, 20, 30],
    'rsi_period':     [7, 14, 21],
    'rsi_threshold':  [30, 50, 70],
}

def optimize_params(df, initial_capital):
    best_val = -float('inf')
    best_params = None

    closes = df['close'].tolist()
    n = len(df)

    # 가능한 모든 파라미터 조합 탐색
    for es in grid['ema_short']:
        for el in grid['ema_long']:
            if es >= el: continue
            for rp in grid['rsi_period']:
                for rt in grid['rsi_threshold']:
                    params = {
                        'ema_short':     es,
                        'ema_long':      el,
                        'rsi_period':    rp,
                        'rsi_threshold': rt,
                    }
                    cash, btc = initial_capital, 0
                    window = max(es, el, rp)

                    # 시뮬레이션 루프
                    for i in range(window, n):
                        window_data = df.iloc[i-window:i+1].values.tolist()
                        price = closes[i]

                        # RSI 계산
                        rsi = calculate_rsi(closes[:i+1], rp)

                        # 매수: EMA 골든 크로스 & RSI < threshold
                        if should_buy(window_data, params) and rsi < rt and cash > price:
                            btc = cash / price
                            cash = 0

                        # 매도: EMA 데드 크로스
                        elif should_sell(window_data, params) and btc > 0:
                            cash = btc * price
                            btc = 0

                    # 최종 가치
                    final_val = cash + btc * closes[-1]
                    if final_val > best_val:
                        best_val, best_params = final_val, params.copy()

    return best_params