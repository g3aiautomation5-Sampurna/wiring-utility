import os
import cv2
import numpy as np
from ultralytics import YOLO

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SIDE_MODEL_PATH = os.path.join(BASE_DIR, "models", "origin3_model.pt")
if not os.path.exists(SIDE_MODEL_PATH):
    SIDE_MODEL_PATH = os.path.join(BASE_DIR, "models", "yolov8n.pt")

_side_model = None

def get_side_model():
    global _side_model
    if _side_model is None:
        model_path = SIDE_MODEL_PATH
        if not os.path.exists(model_path) and os.path.isdir(os.path.join(BASE_DIR, "models")):
            for f in os.listdir(os.path.join(BASE_DIR, "models")):
                if f.endswith(".pt") and "pose" not in f.lower():
                    model_path = os.path.join(BASE_DIR, "models", f)
                    break
        if os.path.exists(model_path):
            _side_model = YOLO(model_path)
    return _side_model

def check_origin2_grommet(image_path_or_img):
    """
    Validates side image using YOLO detection model.
    All detection-based rules and coordinate-based ROIs removed.

    Returns:
        is_pass (bool)
        failed_reasons (list of str)
        details (dict): {
            'name': 'Origin 3 (Grommet)',
            'pass': bool,
            'annotated': np.ndarray,
            'failed_reasons': list,
            'detected_labels': list
        }
    """
    if isinstance(image_path_or_img, str):
        img_raw = cv2.imread(image_path_or_img)
        if img_raw is None:
            return False, ["Could not read image file."], {}
    else:
        img_raw = image_path_or_img

    if img_raw is None:
        return False, ["Invalid or empty image."], {}

    model = get_side_model()
    img_res = cv2.resize(img_raw, (1024, 576))

    if model is None:
        return False, ["Side model not loaded."], {'annotated': img_res}

    results = model(img_res, verbose=False)
    res = results[0]

    detected_labels = []
    has_defect = False
    has_pass_label = False
    names = res.names or {}

    has_origin3 = False
    if len(res.boxes) > 0:
        for box in res.boxes:
            cls_id = int(box.cls[0].item()) if hasattr(box.cls, '__len__') else int(box.cls)
            conf = float(box.conf[0].item()) if hasattr(box.conf, '__len__') else float(box.conf)
            name = str(names.get(cls_id, cls_id)).lower()
            # Ignore unrelated background COCO objects
            if any(w in name for w in ['person', 'suitcase', 'backpack', 'tie', 'bottle', 'chair', 'cup', 'bed', 'laptop']):
                continue
            detected_labels.append(f"{name} ({conf:.2f})")
            if any(w in name for w in ['fail', 'defect', 'ng', 'bad', 'wrong', 'error']):
                has_defect = True
            if 'origin_3' in name or 'origin3' in name or 'pass' in name or 'ok' in name:
                has_origin3 = True

    is_pass = bool(has_origin3 and not has_defect)

    # When the model runs and results into Pass then do nothing
    # and if it fails then in an fstring store what all cases have failed
    if is_pass:
        failed_cases_str = ""
        failed_reasons = []
    else:
        failed_cases_str = f"Failed Cases: Origin 3 (Side View)"
        failed_reasons = [failed_cases_str]

    details = {
        'name': 'Origin 3 (Grommet)',
        'pass': is_pass,
        'failed_reasons': failed_reasons,
        'failed_cases_str': failed_cases_str,
        'annotated': res.plot(),
        'detected_labels': detected_labels
    }

    return is_pass, failed_reasons, details

def check_origin2_image(image_path_or_img, save_result=True):
    """
    Main entry point for Origin 3 detection:
    - Runs check_origin2_grommet
    - Annotated with YOLO model plot
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

    is_pass, failed_reasons, details = check_origin2_grommet(img_raw)
    img_annotated = details.get('annotated')
    if img_annotated is None:
        img_annotated = cv2.resize(img_raw.copy(), (1024, 576))

    if save_result:
        target_sub = "Pass" if is_pass else "Fail"
        result_dir = os.path.join(os.getcwd(), "Result", "Origin3", target_sub)
        os.makedirs(result_dir, exist_ok=True)
        out_path = os.path.join(result_dir, img_name)
        cv2.imwrite(out_path, img_annotated)

    return is_pass, img_annotated, failed_reasons, details

check_origin3_grommet = check_origin2_grommet
check_origin3_image = check_origin2_image

def run_origin2_detection(image_path):
    all_pass, _, failed_reasons, details = check_origin2_image(image_path, save_result=True)
    return all_pass

run_origin3_detection = run_origin2_detection

if __name__ == "__main__":
    pass
