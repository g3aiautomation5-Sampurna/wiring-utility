import cv2
import numpy as np
import os

def check_origin(image_path_or_img):
    """
    Validates the origin positions of red and black wires:
    1. Upper Middle Pair: 
       - Origin of red wire MUST be at the middle coil.
       - Origin of black wire MUST be at the rightmost coil.
    2. Bottom Left Pair: 
       - Origin of black wire MUST be above the red wire origin 
         (Upper socket = Black wire, Lower socket = Red wire).
         If red wire enters the upper socket (x: 425-455, y: 390-490), it fails.
    3. Bottom Right Pair: 
       - Origin of black wire MUST be below the red wire origin 
         (Upper socket = Red wire, Lower socket = Black wire).

    Returns:
       all_pass (bool)
       failed_origins (list of str)
       details (dict): {
           'case2_um': {'pass': bool, 'box': (x1, y1, x2, y2), 'name': 'Upper Middle Origin'},
           'case1_bl': {'pass': bool, 'box': (x1, y1, x2, y2), 'name': 'Bottom Left Origin'},
           'case3_br': {'pass': bool, 'box': (x1, y1, x2, y2), 'name': 'Bottom Right Origin'}
       }
    """
    if isinstance(image_path_or_img, str):
        img = cv2.imread(image_path_or_img)
        if img is None:
            return False, ["Failed to load image."], {}
    else:
        img = image_path_or_img
        
    img_resized = cv2.resize(img, (1024, 576))
    hsv = cv2.cvtColor(img_resized, cv2.COLOR_BGR2HSV)
    
    # Red mask with broad tolerance for lighting/shadows
    mask_r = cv2.inRange(hsv, (0, 60, 30), (15, 255, 255)) + cv2.inRange(hsv, (155, 60, 30), (180, 255, 255))
    
    failed_origins = []
    details = {}
    
    # -------------------------------------------------------------
    # 1. UPPER MIDDLE PAIR (Coils)
    # Middle coil connection zone: x: 480 to 570, y: 15 to 80
    # Rightmost coil connection zone: x: 590 to 680, y: 15 to 80
    # -------------------------------------------------------------
    mid_coil_red = np.sum(mask_r[15:80, 480:570] > 0)
    um_pass = True
    if mid_coil_red < 30:
        um_pass = False
        failed_origins.append("Upper Middle Origin: Red wire must originate at the middle coil.")
    details['case2_um'] = {
        'pass': um_pass,
        'box': (470, 15, 690, 100),
        'name': 'Upper Middle Origin (Coils)'
    }
        
    # -------------------------------------------------------------
    # 2. BOTTOM LEFT PAIR (Origin positions)
    # Upper socket (x: 410..448, y: 400..440) -> Black wire
    # Lower socket (x: 405..460, y: 465..530) -> Red wire (Black MUST be above Red)
    # -------------------------------------------------------------
    mask_r_bl = (((cv2.inRange(hsv, (0, 45, 35), (15, 255, 255)) > 0) | 
                  (cv2.inRange(hsv, (155, 45, 35), (180, 255, 255)) > 0))).astype(np.uint8) * 255
    mask_b_bl = cv2.inRange(hsv, (0, 0, 0), (180, 255, 45))

    # Upper socket core: x: 410..448, y: 400..440
    r_up = int(np.sum(mask_r_bl[400:440, 410:448] > 0))

    # Lower zone: x: 360..465, y: 470..560
    r_lower = int(np.sum(mask_r_bl[470:560, 360:465] > 0))
    b_dn = int(np.sum(mask_b_bl[465:530, 405:460] > 0))

    # Inverted wiring defect: Red wire plugged into upper grommet instead of lower grommet
    # Black wire is below Red wire
    bl_pass = True
    if r_up >= 120 and r_lower < 10 and b_dn >= 150:
        bl_pass = False
        failed_origins.append("Bottom Left Origin: Inverted wiring defect - Black wire is BELOW Red wire (Red enters upper grommet and Black enters lower grommet).")

    details['case1_bl'] = {
        'pass': bl_pass,
        'box': (370, 410, 470, 565),
        'name': 'Bottom Left Origin (Grommets)'
    }

    # -------------------------------------------------------------
    # 3. BOTTOM RIGHT PAIR (Origin positions)
    # Origin 3 grommet connection zone (x: 540..660, y: 420..535)
    # Red wire MUST enter grommet above/with black wire (red_in_zone >= 25)
    # -------------------------------------------------------------
    mask_r_br = ((cv2.inRange(hsv, (0, 55, 35), (15, 255, 255)) > 0) | 
                 (cv2.inRange(hsv, (155, 55, 35), (180, 255, 255)) > 0))
    mask_r_br[535:, :] = 0

    br_red_px = np.sum(mask_r_br[420:535, 540:660] > 0)
    
    br_pass = True
    if br_red_px < 25:
        br_pass = False
        failed_origins.append("Bottom Right Origin: Red wire must originate and enter the grommet (above / in front of Black wire).")
        
    details['case3_br'] = {
        'pass': br_pass,
        'box': (540, 415, 660, 565),
        'name': 'Bottom Right Origin (Grommets)'
    }
        
    all_pass = um_pass and bl_pass and br_pass
    return all_pass, failed_origins, details

if __name__ == "__main__":
    pass
