import sys
import os
import cv2
import numpy as np
import time
from pipeline.depth.midas_onnx import MiDaSONNXBackend
from ultralytics import YOLO

def main():
    print("STARTING PRE-CALIBRATION ACCURACY AUDIT")
    # Initialize
    try:
        depth_backend = MiDaSONNXBackend(model_path="model-small.onnx")
        print("MiDaS ONNX Backend loaded.")
    except Exception as e:
        print(f"Failed to load backend: {e}")
        return

    # Load test image
    if os.path.exists("test.jpg"):
        img = cv2.imread("test.jpg")
        img = cv2.resize(img, (640, 480))
    else:
        print("test.jpg not found, creating synthetic image.")
        img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

    # 1. MiDaS ONNX output stability (static image)
    print("\n--- 1. MiDaS ONNX output stability ---")
    depths = []
    for _ in range(50):
        d_map = depth_backend.estimate(img).values
        depths.append(d_map[240, 320]) # center pixel
    depths = np.array(depths)
    print(f"Mean: {depths.mean():.4f}, Std: {depths.std():.4f}, CV: {depths.std()/depths.mean() if depths.mean() > 0 else 0:.6f}")
    if depths.std() == 0:
        print("PASS: Completely stable on exact static image.")
    
    # 2. Temporal stability test (simulated webcam noise)
    print("\n--- 2. Temporal stability test ---")
    noisy_depths = []
    for _ in range(100):
        noise = np.random.normal(0, 2, img.shape).astype(np.int16)
        noisy_img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        d_map = depth_backend.estimate(noisy_img).values
        # Central bbox: x=200..440, y=100..380
        bbox_depth = d_map[100:380, 200:440]
        # Central 50%
        h, w = bbox_depth.shape
        cy, cx = h//2, w//2
        rh, rw = h//4, w//4 # 50% dims means half height, half width
        sample = bbox_depth[cy-rh:cy+rh, cx-rw:cx+rw]
        noisy_depths.append(np.median(sample))
    
    noisy_depths = np.array(noisy_depths)
    mean_nd = noisy_depths.mean()
    std_nd = noisy_depths.std()
    cv_nd = std_nd / mean_nd if mean_nd > 0 else 0
    print(f"Mean: {mean_nd:.4f}, Std: {std_nd:.4f}, CV: {cv_nd:.4f}")
    
    # 3. Bounding-box sampling accuracy
    print("\n--- 3. Bounding-box sampling accuracy ---")
    # Simulate a bounding box on the depth map
    base_depth = depth_backend.estimate(img).values
    bbox_h, bbox_w = 200, 100
    cy, cx = 240, 320
    bbox = base_depth[cy-bbox_h//2:cy+bbox_h//2, cx-bbox_w//2:cx+bbox_w//2]
    
    def sample_region(b, percent):
        if percent == 1.0: return b
        h, w = b.shape
        rh, rw = int(h * percent / 2), int(w * percent / 2)
        bc_y, bc_x = h//2, w//2
        return b[bc_y-rh:bc_y+rh, bc_x-rw:bc_x+rw]

    for p, name in [(1.0, "Full"), (0.5, "Central 50%"), (0.3, "Central 30%"), (0.2, "Central 20%")]:
        region = sample_region(bbox, p)
        print(f"{name}: Mean={np.mean(region):.4f}, Std={np.std(region):.4f}, CV={np.std(region)/np.mean(region) if np.mean(region)>0 else 0:.4f}")
        
    # 4. Spatial consistency & 5. Monotonicity
    print("\n--- 4 & 5. Spatial consistency / Monotonicity ---")
    # Simulate a target moving further by downsizing an object and pasting it
    # We take a patch from the image, paste it at 100%, 75%, 50%, 25% scale on a black background
    target = cv2.resize(cv2.imread("test.jpg"), (100, 200))
    for scale in [1.0, 0.75, 0.5, 0.25]:
        bg = np.zeros((480, 640, 3), dtype=np.uint8)
        th, tw = int(200*scale), int(100*scale)
        scaled_target = cv2.resize(target, (tw, th))
        # paste in center
        sy, sx = 240 - th//2, 320 - tw//2
        bg[sy:sy+th, sx:sx+tw] = scaled_target
        d = depth_backend.estimate(bg).values
        # sample center
        disp = np.median(d[sy:sy+th, sx:sx+tw])
        print(f"Scale {scale*100}% -> Disparity: {disp:.4f}")
        
    # 7. Distance smoothing test
    print("\n--- 7. Distance smoothing test (EMA 0.35) ---")
    alpha = 0.35
    signal = [10.0]*10 + [20.0]*10 # step function
    smoothed = []
    curr = signal[0]
    for s in signal:
        curr = alpha * s + (1 - alpha) * curr
        smoothed.append(curr)
    print(f"Raw: {signal}")
    print(f"Smoothed: {[round(x,2) for x in smoothed]}")
    
    # 9. Resolution/performance test
    print("\n--- 9. Resolution/performance test ---")
    start = time.time()
    for _ in range(30):
        depth_backend.estimate(img)
    end = time.time()
    fps = 30 / (end - start)
    print(f"Speed: {fps:.2f} FPS at 640x480 on CPU")

    # 10. Sanity checks
    print("\n--- 10. Sanity checks ---")
    d_map = depth_backend.estimate(img).values
    has_nan = np.isnan(d_map).any()
    has_inf = np.isinf(d_map).any()
    has_neg = (d_map < 0).any()
    print(f"NaN: {has_nan}, Inf: {has_inf}, Negative: {has_neg}")

if __name__ == '__main__':
    main()
