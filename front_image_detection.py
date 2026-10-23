import cv2
import numpy as np
import os
import shutil

def check_front_origin(image_path_or_img):
    """
    Checks the region marked in yellow outline in the front image:
    Rule: Pass if the red wire goes inside this origin and is in front of the black wire, else fail.

    Returns:
        is_pass (bool)
        failed_reasons (list of str)
        details (dict): {
            'box': (x1, y1, x2, y2),
            'name': 'Front Origin',
            'pass': bool,
            'red_inside': bool,
            'red_in_front': bool,
            'red_pixels': int,
            'black_pixels': int,
            'failed_reasons': list
        }
    """
    if isinstance(image_path_or_img, str):
        img = cv2.imread(image_path_or_img)
        if img is None:
            return False, ["Could not read image file."], {}
    else:
        img = image_path_or_img

    img_resized = cv2.resize(img, (1024, 576))
    
    # 1. Origin Region of Interest (calibrated from user's yellow marked outline)
    # Box coordinates on standard 1024 x 576 resolution:
    # x1=295, y1=195, x2=375, y2=290
    x1, y1, x2, y2 = 295, 195, 375, 290
    roi = img_resized[y1:y2, x1:x2]
    
    r = roi[:, :, 2].astype(float)
    g = roi[:, :, 1].astype(float)
    b = roi[:, :, 0].astype(float)
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    
    # Red mask: robust to lighting/shadows in casing
    mask_r = ((cv2.inRange(hsv, (0, 45, 30), (15, 255, 255)) > 0) | 
              (cv2.inRange(hsv, (155, 45, 30), (180, 255, 255)) > 0)) & (r > g * 1.2) & (r > b * 1.2)
              
    # Black mask: dark wire / socket pixels not belonging to the red wire
    intensity = (r + g + b) / 3.0
    mask_b = (intensity < 45) & (~mask_r)
    
    red_count = int(np.sum(mask_r))
    black_count = int(np.sum(mask_b))
    
    yr, xr = np.where(mask_r)
    failed_reasons = []
    
    # Condition 1: Red wire goes inside this origin
    # The origin socket is located on the left of this marked box (x < 55)
    red_inside = False
    if red_count < 30:
        failed_reasons.append("Front Origin: Red wire not detected inside marked origin region.")
    elif xr.min() > 55:
        failed_reasons.append("Front Origin: Red wire does not reach inside the origin socket.")
    else:
        red_inside = True
        
    # Condition 2: Red wire is in front of black wire
    # Black wire arches above the socket in upper ROI (y < 40, x between 20 and 70)
    # Red wire travels beneath it towards the socket
    black_arch = mask_b[0:40, 20:70]
    red_span = mask_r[:, 20:70]
    
    yb, xb = np.where(black_arch)
    yr_s, xr_s = np.where(red_span)
    
    red_in_front = True
    if len(yb) >= 20 and len(yr_s) >= 20:
        # In image coordinates:
        # Higher Y coordinate = lower on screen = closer to camera / in FRONT.
        # Lower Y coordinate = higher on screen = further back / BEHIND.
        if yr_s.mean() < yb.mean():
            red_in_front = False
            failed_reasons.append("Front Origin: Red wire is BEHIND black wire (Black wire is in front).")
            
    is_pass = red_inside and red_in_front and (len(failed_reasons) == 0)
    
    details = {
        'box': (x1, y1, x2, y2),
        'name': 'Front Origin',
        'pass': is_pass,
        'red_inside': red_inside,
        'red_in_front': red_in_front,
        'red_pixels': red_count,
        'black_pixels': black_count,
        'failed_reasons': failed_reasons
    }
    
    return is_pass, failed_reasons, details

def check_front_image(image_path_or_img, save_result=True):
    """
    Main entry point for Front Image Detection module:
    - Runs check_front_origin on the marked yellow region
    - Generates visual annotated image with PASS/FAIL bounding box and diagnostic badge
    - Saves result to Result/FrontView/Pass or Result/FrontView/Fail
    """
    if isinstance(image_path_or_img, str):
        img_raw = cv2.imread(image_path_or_img)
        img_name = os.path.basename(image_path_or_img)
        if img_raw is None:
            return False, None, ["Failed to load image file."], {}
    else:
        img_raw = image_path_or_img
        img_name = "front_detection_result.jpg"

    img_annotated = cv2.resize(img_raw.copy(), (1024, 576))

    is_pass, failed_reasons, details = check_front_origin(img_annotated)

    # Draw the marked origin box
    x1, y1, x2, y2 = details.get('box', (295, 195, 375, 290))
    border_color = (0, 220, 0) if is_pass else (0, 0, 240)
    cv2.rectangle(img_annotated, (x1, y1), (x2, y2), border_color, 3)

    # Origin status badge
    badge_text = " Front Origin: PASS " if is_pass else " Front Origin: FAIL "
    text_bg = (0, 180, 0) if is_pass else (0, 0, 220)
    badge_y = y1 - 8 if y1 > 25 else y2 + 20
    text_size = cv2.getTextSize(badge_text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)[0]
    cv2.rectangle(img_annotated, (x1, badge_y - 18), (x1 + text_size[0], badge_y + 4), text_bg, -1)
    cv2.putText(img_annotated, badge_text, (x1, badge_y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)

    # Top-left Overall Status Banner
    banner_text = "FRONT DETECTION: PASS" if is_pass else "FRONT DETECTION: FAIL"
    banner_bg = (0, 160, 0) if is_pass else (0, 0, 200)
    cv2.rectangle(img_annotated, (15, 15), (380, 52), banner_bg, -1)
    cv2.putText(img_annotated, banner_text, (25, 41), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    # Save to Result/FrontView/Pass or Result/FrontView/Fail
    if save_result:
        target_sub = "Pass" if is_pass else "Fail"
        result_dir = os.path.join(os.getcwd(), "Result", "FrontView", target_sub)
        os.makedirs(result_dir, exist_ok=True)
        out_path = os.path.join(result_dir, img_name)
        cv2.imwrite(out_path, img_annotated)

    return is_pass, img_annotated, failed_reasons, details

def run_front_detection(image_path):
    """Console test runner for Front Image Detection."""
    print(f"\n======================================")
    print(f"Front Image Detection: {os.path.basename(image_path)}")
    print(f"======================================")

    all_pass, _, failed_reasons, details = check_front_image(image_path, save_result=True)

    print(f"Origin Check: {'PASS' if all_pass else 'FAIL'}")
    print(f" - Red wire goes inside origin: {'YES' if details.get('red_inside') else 'NO'}")
    print(f" - Red wire in front of black wire: {'YES' if details.get('red_in_front') else 'NO'}")

    if all_pass:
        print("\nOVERALL FRONT STATUS: PASS (Red wire inside origin and in front of black wire)")
    else:
        print("\nOVERALL FRONT STATUS: FAIL")
        for r in failed_reasons:
            print(f" - {r}")

    sub = "Pass" if all_pass else "Fail"
    print(f"-> Saved result image to: Result/FrontView/{sub}/{os.path.basename(image_path)}")
    return all_pass

if __name__ == "__main__":
    import sys
    test_images = [
        r"C:\Users\SM 461\.gemini\antigravity\brain\d2775043-6129-4b9f-8893-f45b60415f9a\.user_uploaded\media_1788428772738.jpg",
        r"Front view of PCB\WIN_20260903_09_08_19_Pro.jpg"
    ]
    if len(sys.argv) > 1:
        test_images = [sys.argv[1]]

    for img in test_images:
        if os.path.exists(img):
            run_front_detection(img)
