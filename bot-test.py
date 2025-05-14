import json
import time
import logging
import ccxt
from decimal import Decimal, getcontext, ROUND_DOWN

# Configure logging to stdout for Docker logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# Load configuration
with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

api_key = config.get('apiKey')
secret = config.get('secret')
symbol_base = config.get('symbol')  # e.g. "ETH"
interval_seconds = config.get('interval_seconds', 60)

# Initialize Bithumb exchange
exchange = ccxt.bithumb({
    'apiKey': api_key,
    'secret': secret,
    'enableRateLimit': True,
})

# Prepare market symbol
market_symbol = f"{symbol_base}/KRW"
exchange.load_markets()
market = exchange.markets.get(market_symbol)
if not market:
    logger.error(f"Market symbol {market_symbol} not found on Bithumb.")
    raise SystemExit(1)
# Get amount precision for rounding
amount_precision = market['precision']['amount']
logger.info(f"Amount precision: {amount_precision}")

# Set Decimal context precision
getcontext().prec = amount_precision + 10

# Define minimum and quantization units
quant = Decimal('1e-{0}'.format(amount_precision))
min_amount = 0.0014

try:
    # Fetch KRW balance and calculate 95%
    balance = exchange.fetch_balance()
    krw_balance = Decimal(str(balance.get('KRW', {}).get('free', 0)))
    krw_to_use = krw_balance * Decimal('0.95')
    logger.info(f"KRW balance: {krw_balance}, using 95%: {krw_to_use}")

    # Fetch current ask price
    ticker = exchange.fetch_ticker(market_symbol)
    ask_price = Decimal(str(ticker.get('ask') or ticker.get('last')))
    logger.info(f"Current ask price for {market_symbol}: {ask_price}")

    # Calculate base amount and floor to precision
    raw_amount = krw_to_use / ask_price
    amount_to_buy = raw_amount.quantize(quant, rounding=ROUND_DOWN)

    # Adjust down if cost exceeds available KRW (accounting for fees/slippage)
    estimated_cost = amount_to_buy * ask_price
    while estimated_cost > krw_to_use:
        amount_to_buy -= quant
        estimated_cost = amount_to_buy * ask_price

    # Ensure amount is above minimum
    if amount_to_buy < min_amount:
        logger.error(f"Calculated amount {amount_to_buy} is below minimum trade amount {min_amount}.")
        raise SystemExit(1)
    logger.info(f"Adjusted amount to buy: {amount_to_buy} {symbol_base} (cost ~{estimated_cost})")

    # Place market buy order
    logger.info(f"Placing market buy order for {amount_to_buy} {symbol_base}... (cost {estimated_cost})")
    buy_order = exchange.create_order(
        symbol=market_symbol,
        type='market',
        side='buy',
        amount=0.014,
    )
    logger.info(f"Buy order executed: {buy_order}")

    # Wait before selling
    logger.info(f"Waiting for {interval_seconds} seconds before selling...")
    time.sleep(interval_seconds)

    # Refresh balance
    balance = exchange.fetch_balance()
    free_amount = Decimal(str(balance.get(symbol_base, {}).get('free', 0)))
    logger.info(f"Available balance for {symbol_base}: {free_amount}")

    if free_amount >= min_amount:
        # Adjust sell amount down
        amount_to_sell = free_amount.quantize(quant, rounding=ROUND_DOWN)
        logger.info(f"Placing market sell order for {amount_to_sell} {symbol_base}...")
        sell_order = exchange.create_order(
            symbol=market_symbol,
            type='market',
            side='sell',
            amount=float(amount_to_sell),
        )
        logger.info(f"Sell order executed: {sell_order}")
    else:
        logger.warning("No sufficient balance to sell.")

    logger.info("Trade cycle completed.")

except Exception as e:
    logger.exception(f"An error occurred during trading: {e}")
    raise
