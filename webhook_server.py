from flask import Flask, request
import os

app = Flask(__name__)
SECRET_KEY = os.getenv("WEBHOOK_KEY", "default_key")

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    if data.get("key") != SECRET_KEY:
        return 'Unauthorized', 403

    print(f"[SIGNAL] {data}")
    return 'OK', 200

if __name__ == '__main__':
    app.run()