from flask import Flask, request, jsonify
import os
import time
import hmac
import hashlib
import requests

API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_SECRET_KEY")
WEBHOOK_KEY = os.getenv("WEBHOOK_KEY").strip()

app = Flask(__name__)
BASE_URL = "https://fapi.binance.com"

def send_order(symbol: str, side: str, quantity: float = 0.01):
    url = f"{BASE_URL}/fapi/v1/order"
    params = {
        "symbol": symbol,
        "side": side,
        "type": "MARKET",
        "quantity": quantity,
        "timestamp": int(time.time() * 1000)
    }
    query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
    signature = hmac.new(API_SECRET.encode(), query_string.encode(), hashlib.sha256).hexdigest()
    params["signature"] = signature
    headers = {
        "X-MBX-APIKEY": API_KEY
    }
    response = requests.post(url, params=params, headers=headers)
    print(f"📤 주문 전송 결과: {response.status_code} - {response.text}")
    return response.json()

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    print("📥 웹훅 수신:", data)

    if not data or data.get("key") != WEBHOOK_KEY:
        print("❌ 인증 실패 또는 빈 데이터")
        return jsonify({"error": "Unauthorized"}), 403

    signal = data.get("message", "").strip().upper()

    if signal == "LONG":
        return jsonify(send_order("ETHUSDT", "BUY"))
    elif signal == "SHORT":
        return jsonify(send_order("ETHUSDT", "SELL"))
    elif signal == "PING":
        print("✅ 서버 연결 확인용 ping 수신됨")
        return jsonify({"status": "pong"}), 200
    else:
        print("❗ 잘못된 신호:", signal)
        return jsonify({"error": "잘못된 메시지 형식"}), 400

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
