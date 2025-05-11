# backtest.py
import pandas as pd
from strategy import should_buy, should_sell

# EMA 단기/장기 그리드
grid = {
    'ema_short': [5, 10, 15],
    'ema_long':  [20, 30, 50],
}

FEE_RATE = 0.0004  # 거래 수수료 0.04%

def optimize_params(df, initial_capital):
    best_val = -float('inf')
    best_params = None

    for es in grid['ema_short']:
        for el in grid['ema_long']:
            if es >= el:
                continue
            params = {'ema_short': es, 'ema_long': el}
            cash = initial_capital
            btc  = 0
            window = max(es, el)

            for i in range(window, len(df)):
                window_data = df.iloc[i-window:i+1].values.tolist()
                price = df['close'].iloc[i]

                # 매수
                if should_buy(window_data, params) and cash > price:
                    # 투자 금액 전부 매수, 수수료 제외
                    btc = (cash / price) * (1 - FEE_RATE)
                    cash = 0

                # 매도
                elif should_sell(window_data, params) and btc > 0:
                    cash = btc * price * (1 - FEE_RATE)
                    btc = 0

            final_val = cash + btc * df['close'].iloc[-1]
            if final_val > best_val:
                best_val = final_val
                best_params = params.copy()

    return best_params
