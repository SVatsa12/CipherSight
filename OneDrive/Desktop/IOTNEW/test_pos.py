import requests
import time

BASE_URL = "http://localhost:5000"

def test_pos_flow():
    # 1. Create Transaction
    print("Testing /api/create-transaction...")
    payload = {"amount": "49.99"}
    try:
        r = requests.post(f"{BASE_URL}/api/create-transaction", json=payload)
        r.raise_for_status()
        data = r.json()
        tx_id = data['tx_id']
        print(f"Success: Created {tx_id}")
        
        # 2. Trigger PIN display
        print("Testing /api/display-pin...")
        r = requests.post(f"{BASE_URL}/api/display-pin/{tx_id}")
        r.raise_for_status()
        print("Success: PIN displayed")
        
        # 3. Verify Payment (guessing correct OTP from logs manually if needed, but let's see if we can get it or just test failure)
        print("Testing /api/verify-payment with wrong OTP...")
        r = requests.post(f"{BASE_URL}/api/verify-payment", json={"tx_id": tx_id, "otp": "0000"})
        print(f"Response (should be 401): {r.status_code}")
        
        return True
    except Exception as e:
        print(f"Test failed: {e}")
        return False

if __name__ == "__main__":
    test_pos_flow()
