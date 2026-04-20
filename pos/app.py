import os
import random
import base64
import io
import paho.mqtt.client as mqtt
from flask import Flask, render_template, request, jsonify
from PIL import Image
import numpy as np
import sys
import time
import threading
import queue
import string

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'core')))
from core.shredder import CipherShredder
from core.orchestrator import CipherOrchestrator

app = Flask(__name__)
app.secret_key = "pos_secret_key_8828"

BROKER = os.environ.get("MQTT_BROKER", "broker.hivemq.com")
PORT = 1883
TOPIC = "phantasm/iot/display"

shredder = CipherShredder(output_dir="pos_outputs")
orch = CipherOrchestrator()

active_txs = {}


def matrix_to_base64(matrix):
    img = Image.fromarray((matrix * 255).astype(np.uint8), mode='L')
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode('utf-8')


def get_local_ip():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except Exception:
        ip = "127.0.0.1"
    return ip


mqtt_queue = queue.Queue()


def mqtt_worker():
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
    except AttributeError:
        client = mqtt.Client()

    while True:
        try:
            item = mqtt_queue.get()
            if item is None:
                break

            payload, qos = item

            # Fresh connection for every single publish — no burst draining
            # This guarantees each message is fully delivered before the next
            client.connect(BROKER, PORT, 60)
            client.loop_start()
            time.sleep(0.3)

            result = client.publish(TOPIC, payload, qos=qos)
            result.wait_for_publish()  # Block until broker ACKs this message

            time.sleep(0.5)
            client.loop_stop()
            client.disconnect()

            print(f"[MQTT] Published payload of length: {len(payload) if isinstance(payload, (bytes, bytearray)) else len(str(payload))}")

        except Exception as e:
            print(f"[MQTT Worker Error] {e}")
            try:
                client.loop_stop()
                client.disconnect()
            except:
                pass
            time.sleep(1)


threading.Thread(target=mqtt_worker, daemon=True).start()


def mqtt_publish(payload, qos=1):
    mqtt_queue.put((payload, qos))


@app.route('/')
def index():
    return "CipherSight POS System. Use /merchant or /customer."


@app.route('/merchant')
def merchant_dashboard():
    return render_template('merchant.html')


@app.route('/customer')
def customer_portal():
    return render_template('customer.html')


@app.route('/api/network-info', methods=['GET'])
def network_info():
    return jsonify({"ip": get_local_ip(), "port": 5000})


@app.route('/api/create-transaction', methods=['POST'])
def create_transaction():
    data = request.json
    amount = data.get("amount")

    tx_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    otp = str(random.randint(1000, 9999))

    secret_data = f"PAY:ID={tx_id};AMT={amount}"
    share_a, share_b = shredder.shred(secret_data)

    active_txs[tx_id] = {
        "amount": amount,
        "otp": otp,
        "share_a": share_a,
        "share_b": share_b,
        "status": "pending"
    }

    base_url = f"http://{get_local_ip()}:5000"
    customer_url = f"{base_url}/customer?tx={tx_id}"

    # Generate QR and publish — OLED displays it immediately
    # PIN is NOT sent here — it only sends when merchant clicks "Send Code to Hardware"
    qr_matrix = shredder.generate_qr(customer_url, border=1)
    qr_payload = orch.prepare_payload(qr_matrix)

    print(f"[POS] QR payload size: {len(qr_payload)} bytes")  # Should always be 1024
    mqtt_publish(qr_payload)

    print(f"[POS] Transaction {tx_id} created - Amount: ${amount} - OTP: {otp}")

    return jsonify({
        "success": True,
        "tx_id": tx_id,
        "amount": amount
    })


@app.route('/api/transaction/<tx_id>', methods=['GET'])
def get_transaction(tx_id):
    if tx_id not in active_txs:
        return jsonify({"success": False, "message": "Transaction not found"}), 404
    tx = active_txs[tx_id]
    return jsonify({
        "success": True,
        "tx_id": tx_id,
        "amount": tx["amount"],
        "status": tx["status"]
    })


@app.route('/api/display-pin/<tx_id>', methods=['POST'])
def display_pin(tx_id):
    """Merchant clicks 'Send Code to Hardware' — sends PIN to OLED."""
    if tx_id not in active_txs:
        return jsonify({"success": False, "message": "Transaction not found"}), 404

    if active_txs[tx_id]["status"] == "completed":
        return jsonify({"success": False, "message": "Transaction already completed"}), 400

    otp = active_txs[tx_id]["otp"]
    mqtt_publish(otp)
    print(f"[POS] PIN sent to OLED for {tx_id}: {otp}")
    return jsonify({"success": True, "message": "PIN sent to hardware"})


@app.route('/api/verify-payment', methods=['POST'])
def verify_payment():
    data = request.json
    tx_id = data.get('tx_id')
    user_otp = data.get('otp')

    if tx_id not in active_txs:
        return jsonify({"success": False, "message": "Transaction not found"}), 404

    if active_txs[tx_id]["status"] == "completed":
        return jsonify({"success": False, "message": "Transaction already completed"}), 400

    if active_txs[tx_id]["otp"] == user_otp:
        active_txs[tx_id]["status"] = "completed"

        share_a = active_txs[tx_id]["share_a"]
        share_b = active_txs[tx_id]["share_b"]
        reconstructed = shredder.reconstruct(share_a, share_b)
        reconstructed_b64 = matrix_to_base64(reconstructed)

        print(f"[POS] Transaction {tx_id} COMPLETED [SUCCESS]")
        mqtt_publish("VERIFIED")

        return jsonify({
            "success": True,
            "message": "Payment Successful!",
            "amount": active_txs[tx_id]["amount"],
            "reconstructed_qr": reconstructed_b64
        })
    else:
        print(f"[POS] Wrong OTP attempt on {tx_id}: {user_otp}")
        return jsonify({"success": False, "message": "Invalid challenge code. Check the OLED screen."}), 401


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)