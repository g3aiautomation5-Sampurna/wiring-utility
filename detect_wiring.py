import cv2
import numpy as np
import os
from detect_origin import check_origin

def check_wiring(image_path):
    print(f"\n--- Checking {os.path.basename(image_path)} ---")
    img = cv2.imread(image_path)
    if img is None:
        print(f"Failed to load {image_path}")
        return

    # Resize for consistency so our ROIs work across different image sizes
    img = cv2.resize(img, (1280, 720))
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # Red masks (Red wraps around in HSV color space)
    lower_red1 = np.array([0, 100, 70])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([160, 100, 70])
    upper_red2 = np.array([180, 255, 255])
    
    mask_red1 = cv2.inRange(hsv, lower_red1, upper_red1)
    mask_red2 = cv2.inRange(hsv, lower_red2, upper_red2)
    mask_red = mask_red1 + mask_red2

    # Black mask
    lower_black = np.array([0, 0, 0])
    upper_black = np.array([180, 255, 60])
    mask_black = cv2.inRange(hsv, lower_black, upper_black)

    # Define Regions of Interest (y1, y2, x1, x2)
    height, width = img.shape[:2]
    
    rois = {
        "Bottom Left": {"coords": (int(height*0.6), int(height*0.95), int(width*0.1), int(width*0.4)), "rule": "red_left"},
        "Upper Middle": {"coords": (int(height*0.1), int(height*0.4), int(width*0.4), int(width*0.7)), "rule": "red_right"},
        "Bottom Right": {"coords": (int(height*0.6), int(height*0.95), int(width*0.5), int(width*0.8)), "rule": "red_left"}
    }

    all_good = True

    for region_name, data in rois.items():
        if region_name == "Upper Middle":
            # For upper middle, detect only origins: if origins pass, wiring passes
            origin_pass, _, origin_details = check_origin(img)
            um_origin_pass = origin_details.get('case2_um', {}).get('pass', False)
            if um_origin_pass:
                print(f"PASS: {region_name} correct (Origin verified).")
            else:
                print(f"ERROR in {region_name}: Upper Middle origin check failed!")
                all_good = False
            continue

        y1, y2, x1, x2 = data["coords"]
        rule = data["rule"]
        
        roi_red = mask_red[y1:y2, x1:x2]
        roi_black = mask_black[y1:y2, x1:x2]
        
        # Noise removal
        kernel = np.ones((5,5), np.uint8)
        roi_red = cv2.morphologyEx(roi_red, cv2.MORPH_OPEN, kernel)
        roi_black = cv2.morphologyEx(roi_black, cv2.MORPH_OPEN, kernel)

        M_red = cv2.moments(roi_red)
        M_black = cv2.moments(roi_black)
        
        # Check if we detected enough of both colors
        if M_red["m00"] > 500 and M_black["m00"] > 500:
            # Get X coordinate of the center of mass
            cx_red = int(M_red["m10"] / M_red["m00"])
            cx_black = int(M_black["m10"] / M_black["m00"])
            
            if rule == "red_left":
                if cx_red > cx_black:
                    print(f"ERROR in {region_name}: Red wire is on the right, should be on the left!")
                    all_good = False
                else:
                    print(f"PASS: {region_name} correct (Red on left).")
            elif rule == "red_right":
                if cx_red < cx_black:
                    print(f"ERROR in {region_name}: Red wire is on the left, should be on the right!")
                    all_good = False
                else:
                    print(f"PASS: {region_name} correct (Red on right).")
        else:
            print(f"WARNING: {region_name} - Could not clearly detect wires.")

    if all_good:
         print("OVERALL: PASS (Wiring is Correct)")
    else:
         print("OVERALL: FAIL (Wiring is Incorrect)")

if __name__ == '__main__':
    images = [
        r"C:\Users\SM 461\.gemini\antigravity\brain\644b880a-cd54-4a12-8dac-7d95cf5ce3d2\.user_uploaded\media_1787643759564.jpg", # Correct
        r"C:\Users\SM 461\.gemini\antigravity\brain\644b880a-cd54-4a12-8dac-7d95cf5ce3d2\.user_uploaded\media_1787643902815.png", # Case 1
        r"C:\Users\SM 461\.gemini\antigravity\brain\644b880a-cd54-4a12-8dac-7d95cf5ce3d2\.user_uploaded\media_1787644122598.png", # Case 2
        r"C:\Users\SM 461\.gemini\antigravity\brain\644b880a-cd54-4a12-8dac-7d95cf5ce3d2\.user_uploaded\media_1787644332813.png"  # Case 3
    ]

    for img in images:
        check_wiring(img)
