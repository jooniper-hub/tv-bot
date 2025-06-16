from flask import Flask, request, jsonify
import os
from binance.client import Client

app = Flask(__name__)

API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_SECRET_KEY")
WEBHOOK_KEY = os.getenv("WEBHOOK_KEY")

client = Client(API_KEY, API_SECRET)

positions = {}  # 현재 심볼별 포지션 상태 저장: "LONG", "SHORT", None

SYMBOL = "ETHUSDT"
QTY = 0.01  # 주문 수량, 필요에 따라 수정

def place_order(symbol, side, quantity):
    try:
        order = client.futures_create_order(
            symbol=symbol,
            side=side,
            type="MARKET",
            quantity=quantity
        )
        return order
    except Exception as e:
        return {"error": str(e)}

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    if not data or data.get("key") != WEBHOOK_KEY:
        return jsonify({"error": "Unauthorized"}), 403

    signal = data.get("signal")
    pos = positions.get(SYMBOL, None)

    try:
        if signal == "LONG_ENTRY":
            if pos != "LONG":
                res = place_order(SYMBOL, "BUY", QTY)
                positions[SYMBOL] = "LONG"
                return jsonify({"msg": "Long entry executed", "result": res})

        elif signal == "SHORT_ENTRY":
            if pos != "SHORT":
                res = place_order(SYMBOL, "SELL", QTY)
                positions[SYMBOL] = "SHORT"
                return jsonify({"msg": "Short entry executed", "result": res})

        elif signal == "LONG_EXIT":
            if pos == "LONG":
                res = place_order(SYMBOL, "SELL", QTY)
                positions[SYMBOL] = None
                return jsonify({"msg": "Long exit executed", "result": res})

        elif signal == "SHORT_EXIT":
            if pos == "SHORT":
                res = place_order(SYMBOL, "BUY", QTY)
                positions[SYMBOL] = None
                return jsonify({"msg": "Short exit executed", "result": res})

        else:
            return jsonify({"error": "Unknown signal"}), 400

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
