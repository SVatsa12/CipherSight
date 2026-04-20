from PIL import Image
import os

def to_header(path, name="share_a_bmp", out="firmware/shares.h"):
    if not os.path.exists(path): return
    img = Image.open(path).convert('1').resize((128, 64))
    data = list(img.getdata())
    
    with open(out, "w") as f:
        f.write(f"#ifndef SHARES_H\n#define SHARES_H\n#include <pgmspace.h>\nconst unsigned char {name}[] PROGMEM = {{\n")
        bytes_list = []
        for y in range(64):
            for xb in range(16):
                b = 0
                for bit in range(8):
                    if data[y * 128 + xb * 8 + bit] == 255: b |= (1 << (7 - bit))
                bytes_list.append(hex(b))
        for i in range(0, len(bytes_list), 12):
            f.write("  " + ", ".join(bytes_list[i:i+12]) + ",\n")
        f.write("};\n#endif")

if __name__ == "__main__":
    to_header("outputs/share_a.png")
