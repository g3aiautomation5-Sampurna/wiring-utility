"python -c "
import cv2, numpy as np, glob

def evaluate_front_view(img):
    img_resized = cv2.resize(img, (1024, 576))
    hsv = cv2.cvtColor(img_resized, cv2.COLOR_BGR2HSV)
    
    mask_r = cv2.inRange(hsv, (0, 50, 30), (12, 255, 255)) + cv2.inRange(hsv, (160, 50, 30), (180, 255, 255))
    mask_b = cv2.inRange(hsv, (0, 0, 0), (180, 255, 45))
    mask_g = cv2.inRange(hsv, (35, 40, 40), (85, 255, 255))
    
    # Track Small PCB (Top)
    mask_small = mask_g[0:350, :]
    ys, xs = np.where(mask_small > 0)
    cx_small = int(np.median(xs)) if len(xs) else 550
    cy_small = int(np.median(ys)) if len(ys) else 275
    
    # Track Main PCB (Bottom)
    mask_bot = mask_g[350:576, :]
    yb_g, xb_g = np.where(mask_bot > 0)
    cx_bot = int(np.median(xb_g)) if len(xb_g) else 525
    cy_bot = int(np.median(yb_g)) + 350 if len(yb_g) else 420
    
    # Calculate bounding boxes
    al_y1, al_y2 = max(0, cy_bot - 187), min(576, cy_bot - 27)
    al_x1, al_x2 = max(0, cx_bot - 195), min(1024, cx_bot - 85)
    
    ar_y1, ar_y2 = max(0, cy_small - 104), min(576, cy_small + 36)
    ar_x1, ar_x2 = max(0, cx_small - 129), min(1024, cx_small + 96)
    
    bm_y1, bm_y2 = max(0, cy_bot - 97), min(576, cy_bot + 154)
    bm_x1, bm_x2 = max(0, cx_bot + 55), min(1024, cx_bot + 245)
    
    # 1. Above Left: Red on Upper Right, Black on Downward Left
    r_al = mask_r[al_y1:al_y2, al_x1:al_x2]
    b_al = mask_b[al_y1:al_y2, al_x1:al_x2]
    yr_al, xr_al = np.where(r_al > 0)
    yb_al, xb_al = np.where(b_al > 0)
    al_ok = False
    if len(xr_al) >= 20 and len(xb_al) >= 20:
        dy = np.mean(yr_al) - np.mean(yb_al) # < 0 means red is upper
        dx = np.mean(xr_al) - np.mean(xb_al) # > 0 means red is right
        # Red upper-right: dy < 0 (upper) and dx >= -5 (right / aligned)
        al_ok = (dy < 0 and dx >= -5) or (dx > 0)
        
    # 2. Above Right: Red on Upper Right, Black on Downward Left
    r_ar = mask_r[ar_y1:ar_y2, ar_x1:ar_x2]
    b_ar = mask_b[ar_y1:ar_y2, ar_x1:ar
<truncated 1762 bytes>
