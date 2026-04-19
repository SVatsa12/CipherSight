import os
import random
import base64
import io
import paho.mqtt.client as mqtt
from flask import Flask, render_template, request, jsonify
from PIL import Image
import numpy as np
import sys

# Ensure core modules can be imported
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

# Store active transactions: {tx_id: {amount, otp, share_b_base64, status}}
active_txs = {}


def matrix_to_base64(matrix):
    img = Image.fromarray((matrix * 255).astype(np.uint8), mode='L')
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode('utf-8')


import queue
import threading

mqtt_queue = queue.Queue()

def mqtt_worker():
    import time, queue
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
    except AttributeError:
        client = mqtt.Client()
    
    while True:
        try:
            item = mqtt_queue.get()
            if item is None: break
            
            # Boot a fresh connection guaranteed to be alive for this burst
            client.connect(BROKER, PORT, 60)
            client.loop_start()
            time.sleep(0.2)
            
            payload, qos = item
            client.publish(TOPIC, payload, qos=qos)
            
            # Drain any immediate follow-up payloads (burst mode)
            while True:
                try:
                    next_item = mqtt_queue.get_nowait()
                    if next_item is None: break
                    client.publish(TOPIC, next_item[0], qos=next_item[1])
                except queue.Empty:
                    break
                    
            # Allow the network buffer to flush everything
            time.sleep(0.5)
            client.loop_stop()
            client.disconnect()
            
        except Exception as e:
            print(f"[MQTT Worker Error] {e}")
            try:
                client.loop_stop()
                client.disconnect()
            except:
                pass
            time.sleep(0.5)

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

@app.route('/api/create-transaction', methods=['POST'])
def create_transaction():
    import string
    import random
    data = request.json
    amount = data.get("amount")
    
    # Use shorter TX ID to guarantee the URL string fits in a Version 3 QR Code (29x29)
    tx_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    otp = f"{random.randint(1000, 9999)}"

    # 1. Generate Transaction Secret (encode payment details into a QR)
    secret_data = f"PAY:ID={tx_id};AMT={amount}"
    share_a, share_b = shredder.shred(secret_data)

    otp = str(random.randint(1000, 9999))

    # 3. Store Transaction State server-side (shares live here securely)
    active_txs[tx_id] = {
        "amount": amount,
        "otp": otp,
        "share_a": share_a,
        "share_b": share_b,
        "status": "pending"
    }

    # 5. Generate the standard QR Code for the ESP32 to cache securely
    base_url = f"http://{get_local_ip()}:5000"
    customer_url = f"{base_url}/customer?tx={tx_id}"
    
    qr_matrix = shredder.generate_qr(customer_url, border=1)
    qr_payload = orch.prepare_payload(qr_matrix)
    mqtt_publish(qr_payload) # Cache natively on hardware buffer FIRST

    import time
    time.sleep(0.1)

    # 6. Broadcast Proximity Protocol commands
    mqtt_publish("PREPARE") # Tells ESP32 to show proximity prompt and enable BLE

    print(f"[POS] Transaction {tx_id} created - Amount: ${amount} - OTP: {otp}")

    # Return only tx_id (not the share_b — customer fetches it separately)
    return jsonify({
        "success": True,
        "tx_id": tx_id,
        "amount": amount
    })


@app.route('/api/transaction/<tx_id>', methods=['GET'])
def get_transaction(tx_id):
    """Customer fetches tx details using only the tx_id."""
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
    """Merchant triggers the 4-digit PIN to be sent to OLED."""
    if tx_id not in active_txs:
        return jsonify({"success": False, "message": "Transaction not found"}), 404
    otp = active_txs[tx_id]["otp"]
    mqtt_publish(otp)
    print(f"[POS] PIN for {tx_id} sent to OLED: {otp}")
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
        
        # Perform Server-Side Reconstruction
        share_a = active_txs[tx_id]["share_a"]
        share_b = active_txs[tx_id]["share_b"]
        reconstructed = shredder.reconstruct(share_a, share_b)
        reconstructed_b64 = matrix_to_base64(reconstructed)
        
        print(f"[POS] Transaction {tx_id} COMPLETED [SUCCESS]")
        
        # Trigger OLED Reset & Success Animation
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
