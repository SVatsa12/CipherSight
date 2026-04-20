import cv2
import cv2.aruco as aruco
import numpy as np
import os
import webbrowser
import time

def start_scanner():
    key_path = "outputs/share_b.png"
    if not os.path.exists(key_path):
        print("Error: Run orchestrator first.")
        return
    
    key = cv2.imread(key_path, cv2.IMREAD_GRAYSCALE)
    h_k, w_k = key.shape
    pts_src = np.array([[0, 0], [w_k-1, 0], [w_k-1, h_k-1], [0, h_k-1]], dtype="float32")

    detector = aruco.ArucoDetector(aruco.getPredefinedDictionary(aruco.DICT_4X4_50))
    cap = cv2.VideoCapture(0)
    qr = cv2.QRCodeDetector()
    
    last_open = 0

    while True:
        ret, frame = cap.read()
        if not ret: break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = detector.detectMarkers(gray)
        out = frame.copy()

        if ids is not None and len(ids) >= 4:
            pts_dst = np.zeros((4, 2), dtype="float32")
            found = 0
            for i, id_val in enumerate(ids.flatten()):
                if id_val < 4:
                    pts_dst[id_val] = np.mean(corners[i][0], axis=0)
                    found += 1

            if found == 4:
                h_mat, _ = cv2.findHomography(pts_src, pts_dst)
                h_inv = cv2.getPerspectiveTransform(pts_dst, pts_src)
                
                extracted = cv2.warpPerspective(gray, h_inv, (w_k, h_k))
                _, a_bin = cv2.threshold(extracted, 127, 1, cv2.THRESH_BINARY)
                _, b_bin = cv2.threshold(key, 127, 1, cv2.THRESH_BINARY)
                
                revealed = (1 - (a_bin ^ b_bin)) * 255
                revealed = revealed.astype(np.uint8)
                
                data, _, _ = qr.detectAndDecode(revealed)
                if data and time.time() - last_open > 5:
                    print(f"Redirecting to: {data}")
                    webbrowser.open(data)
                    last_open = time.time()

                warp_rev = cv2.warpPerspective(revealed, h_mat, (frame.shape[1], frame.shape[0]))
                mask = cv2.warpPerspective(np.ones_like(revealed)*255, h_mat, (frame.shape[1], frame.shape[0]))
                out[mask > 0] = warp_rev[mask > 0]
                cv2.polylines(out, [pts_dst.astype(np.int32)], True, (0, 255, 0), 2)

        cv2.imshow("Phantasm Scanner", out)
        if cv2.waitKey(1) == ord('q'): break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    run_ar_scanner() # Fixing the call name to match the previous version if needed, or just renaming
    # Actually, let's keep it consistent.
