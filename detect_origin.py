import os
import cv2
import numpy as np
from ultralytics import YOLO

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POSE_MODEL_PATH = os.path.join(BASE_DIR, "models", "wire_pose_model.pt")
if not os.path.exists(POSE_MODEL_PATH):
    POSE_MODEL_PATH = os.path.join(BASE_DIR, "models", "yolov8n-pose.pt")

_pose_model = None

def get_pose_model():
    global _pose_model
    if _pose_model is None:
        model_path = POSE_MODEL_PATH
        if not os.path.exists(model_path) and os.path.isdir(os.path.join(BASE_DIR, "models")):
            for f in os.listdir(os.path.join(BASE_DIR, "models")):
                if f.endswith(".pt") and "pose" in f.lower():
                    model_path = os.path.join(BASE_DIR, "models", f)
                    break
        if os.path.exists(model_path):
            _pose_model = YOLO(model_path)
    return _pose_model

def check_origin(image_path_or_img):
    """
    Validates top image using YOLO pose estimation model.
    All detection-based rules and coordinate-based ROIs removed.

    Returns:
       all_pass (bool)
       failed_origins (list of str)
       details (dict): {
           'case1_bl': {'pass': bool, 'name': 'Bottom Left Origin'},
           'case2_um': {'pass': bool, 'name': 'Upper Middle Origin'},
           'case3_br': {'pass': bool, 'name': 'Bottom Right Origin'},
           'annotated': np.ndarray,
           'detected_labels': list
       }
    """
    if isinstance(image_path_or_img, str):
        img = cv2.imread(image_path_or_img)
        if img is None:
            return False, ["Failed to load image."], {}
    else:
        img = image_path_or_img

    if img is None:
        return False, ["Invalid or empty image."], {}

    model = get_pose_model()
    img_resized = cv2.resize(img, (1024, 576))

    if model is None:
        return False, ["Pose estimation model not loaded."], {'annotated': img_resized}

    results = model(img_resized, verbose=False)
    res = results[0]

    detected_labels = []
    has_defect = False
    names = res.names or {}

    c1_red = c1_blk = c2_red = c2_blk = c3_red = c3_blk = None

    kpts_data = None
    if hasattr(res, 'keypoints') and res.keypoints is not None and len(res.keypoints.data) > 0:
        kpts_data = res.keypoints.data.cpu().numpy()

    if len(res.boxes) > 0:
        for idx, box in enumerate(res.boxes):
            cls_id = int(box.cls[0].item()) if hasattr(box.cls, '__len__') else int(box.cls)
            conf = float(box.conf[0].item()) if hasattr(box.conf, '__len__') else float(box.conf)
            name = str(names.get(cls_id, cls_id)).lower()
            # Ignore unrelated background COCO objects
            if any(w in name for w in ['person', 'suitcase', 'backpack', 'tie', 'bottle', 'chair', 'cup', 'bed', 'laptop']):
                continue
            detected_labels.append(f"{name} ({conf:.2f})")
            if any(w in name for w in ['fail', 'defect', 'ng', 'bad', 'wrong', 'error']):
                has_defect = True

            if 'wire_red' not in name and 'wire_black' not in name:
                continue

            xyxy = box.xyxy[0].tolist() if hasattr(box.xyxy, '__len__') else box.xyxy.tolist()
            cx = (xyxy[0] + xyxy[2]) / (2.0 * 1024.0)
            cy = (xyxy[1] + xyxy[3]) / (2.0 * 576.0)
            kp = kpts_data[idx] if kpts_data is not None and idx < len(kpts_data) else None

            wire_info = {'name': name, 'conf': conf, 'kp': kp, 'xyxy': xyxy}

            if cy < 0.40:
                if 'wire_red' in name and (c2_red is None or conf > c2_red['conf']): c2_red = wire_info
                elif 'wire_black' in name and (c2_blk is None or conf > c2_blk['conf']): c2_blk = wire_info
            elif cx < 0.50:
                if 'wire_red' in name and (c1_red is None or conf > c1_red['conf']): c1_red = wire_info
                elif 'wire_black' in name and (c1_blk is None or conf > c1_blk['conf']): c1_blk = wire_info
            else:
                if 'wire_red' in name and (c3_red is None or conf > c3_red['conf']): c3_red = wire_info
                elif 'wire_black' in name and (c3_blk is None or conf > c3_blk['conf']): c3_blk = wire_info

    # 1. Below Left (Case 1 / Origin 1)
    # Origin: Red wire's origin should be below black wire's origin (red.y > blk.y)
    # Terminal: Red wire's socket/terminal should be on the left of black wire's socket/terminal (red.x < blk.x)
    if c1_red is None or c1_blk is None or c1_red['kp'] is None or c1_blk['kp'] is None:
        obl_pass = False
        c1_pass = False
    else:
        obl_pass = bool(c1_red['kp'][0][1] > c1_blk['kp'][0][1] and not has_defect)
        c1_term_pass = bool(c1_red['kp'][2][0] < c1_blk['kp'][2][0] and not has_defect)
        c1_pass = bool(c1_term_pass and not has_defect)

    # 2. Upper Middle (Case 2 / Origin 2)
    # Origin: Red wire's origin should be on the left of black wire's origin (red.x < blk.x)
    # Terminal: Red wire's socket/terminal should be on the right of black wire's socket/terminal (red.x > blk.x)
    if c2_red is None or c2_blk is None or c2_red['kp'] is None or c2_blk['kp'] is None:
        oum_pass = False
        c2_pass = False
    else:
        oum_pass = bool(c2_red['kp'][0][0] < c2_blk['kp'][0][0] and not has_defect)
        c2_term_pass = bool(c2_red['kp'][2][0] > c2_blk['kp'][2][0] and not has_defect)
        c2_pass = bool(c2_term_pass and not has_defect)

    # 3. Below Right (Case 3 / Origin 3 Top)
    # Origin: Both wire origins should just exist
    # Terminal: Red wire's socket/terminal should be on the left of black wire's socket/terminal (red.x < blk.x)
    if c3_red is None or c3_blk is None or c3_red['kp'] is None or c3_blk['kp'] is None:
        obr_pass = False
        c3_pass = False
    else:
        obr_pass = bool(c3_red['kp'][0][2] > 0.20 and c3_blk['kp'][0][2] > 0.20 and not has_defect)
        c3_term_pass = bool(c3_red['kp'][2][0] < c3_blk['kp'][2][0] and not has_defect)
        c3_pass = bool(c3_term_pass and not has_defect)

    all_pass = bool(obl_pass and oum_pass and obr_pass and c1_pass and c2_pass and c3_pass and not has_defect)

    # When the model runs and results into Pass then do nothing
    # and if it fails then in an fstring store what all cases have failed
    if all_pass:
        failed_cases_str = ""
        failed_origins = []
    else:
        failed_cases = []
        if not obl_pass: failed_cases.append("Origin 1 (BL)")
        if not oum_pass: failed_cases.append("Origin 2 (UM)")
        if not obr_pass: failed_cases.append("Origin 3 (BR Top)")
        if not c1_pass: failed_cases.append("Case 1 (BL)")
        if not c2_pass: failed_cases.append("Case 2 (UM)")
        if not c3_pass: failed_cases.append("Case 3 (BR)")
        failed_list = ", ".join(failed_cases)
        failed_cases_str = f"Failed Cases: {failed_list}"
        failed_origins = [failed_cases_str]

    details = {
        'case1_bl': {'pass': obl_pass, 'c1_pass': c1_pass, 'name': 'Bottom Left Origin'},
        'case2_um': {'pass': oum_pass, 'c2_pass': c2_pass, 'name': 'Upper Middle Origin'},
        'case3_br': {'pass': obr_pass, 'c3_pass': c3_pass, 'name': 'Bottom Right Origin'},
        'c1_pass': c1_pass,
        'c2_pass': c2_pass,
        'c3_pass': c3_pass,
        'annotated': res.plot(),
        'detected_labels': detected_labels,
        'failed_cases_str': failed_cases_str
    }

    return all_pass, failed_origins, details

if __name__ == "__main__":
    pass
