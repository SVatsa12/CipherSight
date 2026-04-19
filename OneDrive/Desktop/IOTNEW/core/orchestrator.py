import paho.mqtt.client as mqtt
import time
import os
import numpy as np
from PIL import Image
from shredder import CipherShredder

BROKER = "broker.hivemq.com"
PORT = 1883
TOPIC = "phantasm/iot/display"

class CipherOrchestrator:
    def __init__(self):
        self.shredder = CipherShredder()
        self.client = mqtt.Client()
        
    def prepare_payload(self, matrix):
        canvas = Image.new('1', (128, 64), 0)
        qr_img = Image.fromarray((matrix * 255).astype(np.uint8), mode='L').convert('1')
        qr_img.thumbnail((64, 64))
        
        offset = ((128 - qr_img.width) // 2, (64 - qr_img.height) // 2)
        canvas.paste(qr_img, offset)
        
        data = list(canvas.getdata())
        payload = bytearray()
        
        for y in range(64):
            for x_byte in range(16):
                byte = 0
                for bit in range(8):
                    if data[y * 128 + (x_byte * 8 + bit)] == 255:
                        byte |= (1 << (7 - bit))
                payload.append(byte)
        return payload

    def run(self, text):
        try:
            a, b = self.shredder.shred(text)
            self.shredder.save_share(a, "share_a.png")
            self.shredder.save_share(b, "share_b.png")
            
            payload = self.prepare_payload(a)
            
            self.client.connect(BROKER, PORT, 60)
            self.client.loop_start()
            time.sleep(0.5)
            self.client.publish(TOPIC, payload, qos=1)
            time.sleep(1)
            self.client.loop_stop()
            self.client.disconnect()
            print(f"Update sent: {text}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    orch = CipherOrchestrator()
    orch.run("http://localhost:5000/verify?session=tx_9982")
