import cv2
import numpy as np
import glob
import os

rois = {
    'Top_Left_Inductor_Source': (450, 560, 40, 160),
    'Top_Right_Inductor_Source': (560, 680, 40, 160),
    'Bottom_Left_Source': (370, 460, 470, 560),
    'Bottom_Middle_Source': (530, 610, 470, 560),
    'Bottom_Right_Source': (620, 690, 470, 560)
}

correct_files = glob.glob(r'C:\Users\SM 461\Desktop\Try 2\Correct Sources Dataset\*.jpg')[:10]
correct_images = [cv2.resize(cv2.imread(f), (1024, 576)) for f in correct_files]

def verify(img_path):
    print(f"\nVerifying {os.path.basename(img_path)}:")
    img = cv2.imread(img_path)
    if img is None: return
    img = cv2.resize(img, (1024, 576))
    
    for name, (x1, x2, y1, y2) in rois.items():
        roi_test = img[y1:y2, x1:x2]
        
        best_score = -1
        for ref_img in correct_images:
            roi_ref = ref_img[y1:y2, x1:x2]
            # Template match
            res = cv2.matchTemplate(roi_test, roi_ref, cv2.TM_CCOEFF_NORMED)
            score = np.max(res)
            if score > best_score:
                best_score = score
                
        print(f"  {name}: {best_score:.3f}")

verify(r'C:\Users\SM 461\.gemini\antigravity\brain\aee83f41-828f-4235-9706-324cb50bcb81\.user_uploaded\media_1787737616374.png')
verify(r'C:\Users\SM 461\Desktop\Try 2\Wiring Dataset\Wrong Wiring\case 1\wrongwiring_case 1 (1).jpg')
verify(r'C:\Users\SM 461\Desktop\Try 2\Wiring Dataset\Wrong Wiring\case 2\wrongwiring_case 2 (1).jpg')
