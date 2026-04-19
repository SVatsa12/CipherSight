import qrcode
import numpy as np
from PIL import Image
import os

class CipherShredder:
    def __init__(self, output_dir="outputs"):
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def generate_qr(self, data, box_size=2, border=2):
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=box_size,
            border=border,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert('1')
        return np.array(img, dtype=np.uint8)

    def shred(self, data):
        secret_matrix = self.generate_qr(data)
        h, w = secret_matrix.shape
        share_a = np.random.randint(0, 2, (h, w), dtype=np.uint8)
        share_b = share_a ^ (1 - secret_matrix)
        return share_a, share_b

    def save_share(self, matrix, filename):
        img = Image.fromarray((matrix * 255).astype(np.uint8), mode='L')
        path = os.path.join(self.output_dir, filename)
        img.save(path)
        return path

    def reconstruct(self, share_a, share_b):
        return 1 - (share_a ^ share_b)

if __name__ == "__main__":
    shredder = CipherShredder()
    text = "https://ciphersight.security/verify/12345"
    a, b = shredder.shred(text)
    shredder.save_share(a, "share_a.png")
    shredder.save_share(b, "share_b.png")
    recon = shredder.reconstruct(a, b)
    shredder.save_share(recon, "reconstructed.png")
