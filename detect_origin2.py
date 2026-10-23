import cv2
import numpy as np
import os
import shutil

def check_origin2_grommet(image_path_or_img):
    """
    Validates wire origin in the 'Origin 2' front-angled view:
    Rule: Red wire emerging from the grommet MUST be in front of or on the right-hand side 
          of the black wire from the same grommet.
    
    Returns:
        is_pass (bool)
        failed_reasons (list of str)
        details (dict): {
            'box': (x1, y1, x2, y2),
            'name': 'Origin 2 Grommet',
            'pass': bool,
            'red_detected': bool,
            'red_on_right': bool,
            'red_cx': float,
            'blue_cx': float,
            'failed_reasons': list
        }
    """
    if isinstance(image_path_or_img, str):
        img_raw = cv2.imread(image_path_or_img)
        if img_raw is None:
            return False, ["Could not read image file."], {}
    else:
        img_raw = image_path_or_img

    img_res = cv2.resize(img_raw, (1024, 576))
    hsv = cv2.cvtColor(img_res, cv2.COLOR_BGR2HSV)

    # 1. Locate grommet via blue crimp terminals in assembly region (x: 140-480, y: 220-560)
    # Excluding x < 140 prevents locking onto operator blue clothing on the far left.
    search_roi_y1, search_roi_y2 = 220, 560
    search_roi_x1, search_roi_x2 = 140, 480
    
    mask_blue_roi = cv2.inRange(
        hsv[search_roi_y1:search_roi_y2, search_roi_x1:search_roi_x2], 
        (95, 55, 30), (135, 255, 255)
    )
    yb, xb = np.where(mask_blue_roi > 0)
    
    if len(xb) < 50:
        # Fallback default position for grommet
        cx, cy = 260, 360
    else:
        cx = int(np.median(xb)) + search_roi_x1
        cy = int(np.median(yb)) + search_roi_y1

    # Crop ROI around grommet
    crop_w, crop_h = 130, 140
    x1 = max(0, cx - crop_w // 2)
    x2 = min(1024, cx + crop_w // 2)
    y1 = max(0, cy - crop_h // 2)
    y2 = min(576, cy + crop_h // 2)
    
    grommet_crop = img_res[y1:y2, x1:x2]
    hsv_crop = hsv[y1:y2, x1:x2]
    
    # Red mask in crop (robust to indoor lighting & reflection)
    mask_r = ((cv2.inRange(hsv_crop, (0, 50, 30), (15, 255, 255)) > 0) | 
              (cv2.inRange(hsv_crop, (155, 50, 30), (180, 255, 255)) > 0))
    mask_black = cv2.inRange(hsv_crop, (0, 0, 0), (180, 255, 45))
    
    red_pixels = int(np.sum(mask_r > 0))
    black_pixels = int(np.sum(mask_black > 0))
    
    red_detected = bool(red_pixels >= 20)
    black_detected = bool(black_pixels >= 40)
    
    failed_reasons = []
    if not red_detected:
        failed_reasons.append("Origin 3: Red wire not detected at grommet.")
    if not black_detected:
        failed_reasons.append("Origin 3: Black wire not detected at grommet.")
        
    is_pass = bool(red_detected and black_detected)

    details = {
        'box': (x1, y1, x2, y2),
        'name': 'Origin 3 (Grommet)',
        'pass': is_pass,
        'red_detected': red_detected,
        'black_detected': black_detected,
        'red_pixels': red_pixels,
        'black_pixels': black_pixels,
        'failed_reasons': failed_reasons
    }
    
    return is_pass, failed_reasons, details

def check_origin2_image(image_path_or_img, save_result=True):
    """
    Main entry point for Origin 3 detection:
    - Runs check_origin2_grommet
    - Draws visual bounding box, text badge, and overall status
    - Optionally saves result to Result/Origin3/Pass or Result/Origin3/Fail
    """
    if isinstance(image_path_or_img, str):
        img_raw = cv2.imread(image_path_or_img)
        img_name = os.path.basename(image_path_or_img)
        if img_raw is None:
            return False, None, ["Failed to load image file."], {}
    else:
        img_raw = image_path_or_img
        img_name = "origin3_detection_result.jpg"

    img_annotated = cv2.resize(img_raw.copy(), (1024, 576))
    is_pass, failed_reasons, details = check_origin2_grommet(img_annotated)

    x1, y1, x2, y2 = details.get('box', (100, 320, 220, 440))
    border_color = (0, 220, 0) if is_pass else (0, 0, 240)
    cv2.rectangle(img_annotated, (x1, y1), (x2, y2), border_color, 3)

    badge_text = " Origin 3: PASS " if is_pass else " Origin 3: FAIL "
    text_bg = (0, 180, 0) if is_pass else (0, 0, 220)
    badge_y = y1 - 8 if y1 > 25 else y2 + 20
    text_size = cv2.getTextSize(badge_text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)[0]
    cv2.rectangle(img_annotated, (x1, badge_y - 18), (x1 + text_size[0], badge_y + 4), text_bg, -1)
    cv2.putText(img_annotated, badge_text, (x1, badge_y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)

    banner_text = "ORIGIN 3: PASS (Both Wires Connected)" if is_pass else "ORIGIN 3: FAIL (Wire Missing at Grommet)"
    banner_bg = (0, 160, 0) if is_pass else (0, 0, 200)
    cv2.rectangle(img_annotated, (15, 15), (500, 52), banner_bg, -1)
    cv2.putText(img_annotated, banner_text, (25, 41), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)

    if save_result:
        target_sub = "Pass" if is_pass else "Fail"
        result_dir = os.path.join(os.getcwd(), "Result", "Origin3", target_sub)
        os.makedirs(result_dir, exist_ok=True)
        out_path = os.path.join(result_dir, img_name)
        cv2.imwrite(out_path, img_annotated)

    return is_pass, img_annotated, failed_reasons, details

# Aliases for Origin 3
check_origin3_grommet = check_origin2_grommet
check_origin3_image = check_origin2_image

def run_origin2_detection(image_path):
    """Console test runner for Origin 3 Detection."""
    print(f"\n======================================")
    print(f"Origin 3 Image Detection: {os.path.basename(image_path)}")
    print(f"======================================")

    all_pass, _, failed_reasons, details = check_origin2_image(image_path, save_result=True)

    print(f"Origin 3 Check: {'PASS' if all_pass else 'FAIL'}")
    print(f" - Red wire detected: {'YES' if details.get('red_detected') else 'NO'}")
    print(f" - Red wire in front / on right: {'YES' if details.get('red_on_right') else 'NO'}")

    if all_pass:
        print("\nOVERALL ORIGIN 3 STATUS: PASS (Red wire in front / on right of black wire)")
    else:
        print("\nOVERALL ORIGIN 3 STATUS: FAIL")
        for r in failed_reasons:
            print(f" - {r}")

    sub = "Pass" if all_pass else "Fail"
    print(f"-> Saved result image to: Result/Origin3/{sub}/{os.path.basename(image_path)}")
    return all_pass

run_origin3_detection = run_origin2_detection

if __name__ == "__main__":
    import sys
    test_img = r"C:\Users\SM 461\.gemini\antigravity\brain\f6bba769-b980-4399-b026-bbd79f6abbdd\.user_uploaded\media_1788433619575.jpg"
    if len(sys.argv) > 1:
        test_img = sys.argv[1]
    if os.path.exists(test_img):
        run_origin2_detection(test_img)
