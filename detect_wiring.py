import os
import cv2
import numpy as np
from detect_origin import check_origin

def check_wiring(image_path_or_img):
    name = os.path.basename(image_path_or_img) if isinstance(image_path_or_img, str) else "image"
    print(f"\n--- Checking {name} ---")

    if isinstance(image_path_or_img, str):
        img = cv2.imread(image_path_or_img)
        if img is None:
            print(f"Failed to load {image_path_or_img}")
            return False
    else:
        img = image_path_or_img

    if img is None:
        print("Invalid or empty image.")
        return False

    # Evaluated by YOLO pose estimation model (all coordinate-based ROIs and rules removed)
    all_good, failed_origins, details = check_origin(img)

    # When the model runs and results into Pass then do nothing
    # and if it fails then in an fstring store what all cases have failed
    if all_good:
        print("OVERALL: PASS (Detection Verified via Pose Estimation Model)")
        failed_cases_str = ""
    else:
        failed_cases_str = details.get("failed_cases_str") or f"Failed Cases: Top Wire Routing"
        print(f"OVERALL: FAIL -> {failed_cases_str}")
        for r in failed_origins:
            print(f" - {r}")
    return all_good

if __name__ == '__main__':
    images = [
        r"test_images\Camera Roll\top_01.jpg",
        r"test_images\Camera Roll\top_02.jpg"
    ]
    for img in images:
        if os.path.exists(img):
            check_wiring(img)
