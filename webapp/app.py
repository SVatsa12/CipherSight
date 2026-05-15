import os
import random
import sys
from pathlib import Path
import paho.mqtt.client as mqtt
from flask import Flask, render_template, request, jsonify, send_from_directory

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import pos.app as pos_backend

app = Flask(__name__)
app.secret_key = "super_secret_key_for_ciphersight"

BROKER = os.environ.get("MQTT_BROKER", "broker.hivemq.com")
PORT = 1883
TOPIC = "phantasm/iot/display"
POS_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "pos" / "templates"

# Storage for active verification sessions (in-memory for demo purposes)
otp_store = {}

@app.route('/')
def landing():
    return send_from_directory(app.static_folder, 'landing.html')

@app.route('/documentation')
def documentation():
    return send_from_directory(app.static_folder, 'documentation.html')

@app.route('/merchant')
def merchant_page():
    return send_from_directory(str(POS_TEMPLATES_DIR), 'merchant.html')

@app.route('/customer')
def customer_page():
    return send_from_directory(str(POS_TEMPLATES_DIR), 'customer.html')

@app.route('/api/network-info', methods=['GET'])
def api_network_info():
    return pos_backend.network_info()

@app.route('/api/create-transaction', methods=['POST'])
def api_create_transaction():
    return pos_backend.create_transaction()

@app.route('/api/transaction/<tx_id>', methods=['GET'])
def api_get_transaction(tx_id):
    return pos_backend.get_transaction(tx_id)

@app.route('/api/display-pin/<tx_id>', methods=['POST'])
def api_display_pin(tx_id):
    return pos_backend.display_pin(tx_id)

@app.route('/api/verify-payment', methods=['POST'])
def api_verify_payment():
    return pos_backend.verify_payment()


def send_mqtt_code(code):
    client = mqtt.Client()
    try:
        client.connect(BROKER, PORT, 60)
        client.publish(TOPIC, code, qos=1)
        client.disconnect()
        return True
    except Exception as e:
        print(f"Error publishing to MQTT: {e}")
        return False

@app.route('/verify')
def verify_page():
    session_id = request.args.get('session')
    if not session_id:
        return "Invalid session", 400
    
    # Generate 4-digit code
    otp = str(random.randint(1000, 9999))
    otp_store[session_id] = otp
    
    # Send code to ESP32
    send_mqtt_code(otp)
    
    return render_template('index.html', session_id=session_id)

@app.route('/validate', methods=['POST'])
def validate_otp():
    data = request.json
    session_id = data.get('session_id')
    user_otp = data.get('otp')
    
    if session_id in otp_store and otp_store[session_id] == user_otp:
        # Clear OTP after successful use
        del otp_store[session_id]
        return jsonify({"success": True, "message": "Access Granted", "redirect": "https://ciphersight.security/success"})
    else:
        return jsonify({"success": False, "message": "Invalid verification code"}), 401

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
