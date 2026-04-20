import os
import random
import time
import paho.mqtt.client as mqtt
from flask import Flask, render_template, request, jsonify, session

app = Flask(__name__)
app.secret_key = "super_secret_key_for_ciphersight"

BROKER = os.environ.get("MQTT_BROKER", "broker.hivemq.com")
PORT = 1883
TOPIC = "phantasm/iot/display"

# Storage for active verification sessions (in-memory for demo purposes)
otp_store = {}

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
