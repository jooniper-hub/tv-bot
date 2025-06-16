from flask import Flask, request, jsonify
import os
import threading
import time
from binance.client import Client
import numpy as np
import logging

app = Flask(__name__)

API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_SECRET_KEY")
WEBHOOK_KEY = os.getenv("WEBHOOK_KEY")

client = Client(API_KEY, API_SECRET)

SYMBOL = "ETHUSDT"
QTY = 0.01  # 주문 수량 필요에 맞게 수정

SL_ATR_FACTOR = 0.7
TP_ATR_TRAIL = 1.5
TRAILING_OFFSET = 0.3  # 필요시 활용 가능

API_CALL_INTERVAL = 2  # 바이낸스 API 제한 고려, 호출 간격(초)

positions = {}

logging.basicConfig(level=logging.INFO, filename='trade_bot.log', format='%(asctime)s %(levelname)s: %(message)s')

def calculate_atr(highs, lows, closes, period=14):
    tr = []
    for i in range(1, len(highs)):
        high_low = highs[i] - lows[i]
        high_close_prev = abs(highs[i] - closes[i - 1])
        low_close_prev = abs(lows[i] - closes[i - 1])
        tr.append(max(high_low, high_close_prev, low_close_prev))
    tr = np.array(tr)
    atr = np.zeros_like(tr)
    atr[0] = np.mean(tr[:period])  # 첫 ATR은 첫 period 동안 TR 평균
    for i in range(1, len(tr)):
        atr[i] = (atr[i-1] * (period - 1) + tr[i]) / period
    return atr[-1]

def get_atr(client, symbol, interval="1m", length=14):
    try:
        klines = client.futures_klines(symbol=symbol, interval=interval, limit=length+1)
        if len(klines) < length + 1:
            logging.warning(f"ATR 계산 오류: 충분한 캔들 데이터 없음 (현재 {len(klines)})")
            return None
        highs = np.array([float(k[2]) for k in klines])
        lows = np.array([float(k[3]) for k in klines])
        closes = np.array([float(k[4]) for k in klines])
        return calculate_atr(highs, lows, closes, period=length)
    except Exception as e:
        logging.error(f"ATR 계산 예외 발생: {e}")
        return None

def place_order(symbol, side, quantity, retry=3):
    for attempt in range(retry):
        try:
            order = client.futures_create_order(
                symbol=symbol,
                side=side,
                type="MARKET",
                quantity=quantity
            )
            logging.info(f"주문 실행: {side} {quantity} {symbol}")
            return order
        except Exception as e:
            logging.error(f"주문 실패 {attempt + 1}회차: {e}")
            time.sleep(1)
    return {"error": "주문 실패 최대 재시도 횟수 초과"}

def get_current_price(symbol):
    try:
        ticker = client.futures_symbol_ticker(symbol=symbol)
        return float(ticker['price'])
    except Exception as e:
        logging.error(f"현재가 조회 오류: {e}")
        return None

def update_trailing_stop(pos):
    atr = get_atr(client, SYMBOL)
    if atr is None:
        logging.warning("ATR 값이 없어 트레일링 업데이트 무시")
        return

    side = pos["side"]
    entry_price = pos["entry_price"]
    trail_price = pos.get("trail_price", entry_price)
    stop_loss_price = pos.get("stop_loss_price", None)
    current_price = get_current_price(SYMBOL)

    if current_price is None:
        logging.warning("현재가 조회 실패로 트레일링 업데이트 무시")
        return

    if side == "LONG":
        stop_loss = entry_price - atr * SL_ATR_FACTOR
        if stop_loss_price is None or stop_loss > stop_loss_price:
            pos["stop_loss_price"] = stop_loss
        new_trail_price = max(trail_price, current_price - atr * TP_ATR_TRAIL)
        pos["trail_price"] = new_trail_price

    elif side == "SHORT":
        stop_loss = entry_price + atr * SL_ATR_FACTOR
        if stop_loss_price is None or stop_loss < stop_loss_price:
            pos["stop_loss_price"] = stop_loss
        new_trail_price = min(trail_price, current_price + atr * TP_ATR_TRAIL)
        pos["trail_price"] = new_trail_price

def trailing_monitor():
    while True:
        for symbol, pos in list(positions.items()):
            if not pos.get("active", False):
                continue

            current_price = get_current_price(symbol)
            if current_price is None:
                continue

            side = pos["side"]
            trail_price = pos.get("trail_price")
            stop_loss_price = pos.get("stop_loss_price")

            update_trailing_stop(pos)

            if side == "LONG":
                if current_price <= stop_loss_price or current_price <= trail_price:
                    logging.info(f"LONG 청산 주문 실행. 현재가: {current_price}, 손절가: {stop_loss_price}, 트레일 가격: {trail_price}")
                    place_order(symbol, "SELL", QTY)
                    positions[symbol]["active"] = False
                    positions[symbol]["side"] = None

            elif side == "SHORT":
                if current_price >= stop_loss_price or current_price >= trail_price:
                    logging.info(f"SHORT 청산 주문 실행. 현재가: {current_price}, 손절가: {stop_loss_price}, 트레일 가격: {trail_price}")
                    place_order(symbol, "BUY", QTY)
                    positions[symbol]["active"] = False
                    positions[symbol]["side"] = None

        time.sleep(API_CALL_INTERVAL)

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if not data or data.get("key") != WEBHOOK_KEY:
        return jsonify({"error": "Unauthorized"}), 403

    signal = data.get("signal")
    pos = positions.get(SYMBOL, {"side": None, "active": False})

    try:
        if signal == "LONG_ENTRY":
            if pos["side"] != "LONG" or not pos["active"]:
                res = place_order(SYMBOL, "BUY", QTY)
                price = get_current_price(SYMBOL)
                atr_val = get_atr(client, SYMBOL)
                positions[SYMBOL] = {
                    "side": "LONG",
                    "entry_price": price,
                    "stop_loss_price": price - atr_val * SL_ATR_FACTOR if atr_val else None,
                    "trail_price": price - atr_val * TP_ATR_TRAIL if atr_val else None,
                    "active": True
                }
                return jsonify({"msg": "Long entry executed", "result": res})

        elif signal == "SHORT_ENTRY":
            if pos["side"] != "SHORT" or not pos["active"]:
                res = place_order(SYMBOL, "SELL", QTY)
                price = get_current_price(SYMBOL)
                atr_val = get_atr(client, SYMBOL)
                positions[SYMBOL] = {
                    "side": "SHORT",
                    "entry_price": price,
                    "stop_loss_price": price + atr_val * SL_ATR_FACTOR if atr_val else None,
                    "trail_price": price + atr_val * TP_ATR_TRAIL if atr_val else None,
                    "active": True
                }
                return jsonify({"msg": "Short entry executed", "result": res})

        elif signal == "LONG_EXIT":
            if pos["side"] == "LONG" and pos["active"]:
                res = place_order(SYMBOL, "SELL", QTY)
                positions[SYMBOL]["active"] = False
                positions[SYMBOL]["side"] = None
                return jsonify({"msg": "Long exit executed", "result": res})

        elif signal == "SHORT_EXIT":
            if pos["side"] == "SHORT" and pos["active"]:
                res = place_order(SYMBOL, "BUY", QTY)
                positions[SYMBOL]["active"] = False
                positions[SYMBOL]["side"] = None
                return jsonify({"msg": "Short exit executed", "result": res})

        else:
            return jsonify({"error": "Unknown signal"}), 400

    except Exception as e:
        logging.error(f"웹훅 처리 에러: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    monitor_thread = threading.Thread(target=trailing_monitor, daemon=True)
    monitor_thread.start()

    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
