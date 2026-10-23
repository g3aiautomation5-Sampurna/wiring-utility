import sys
import os
import shutil
import cv2
import io
import contextlib
from detect_origin import check_origin
import detect_wiring
from detect_origin2 import check_origin2_image, check_origin2_grommet

def run_both(image_path):
    """Single-image runner (Top View only)."""
    print(f"\n======================================")
    print(f"Testing Single Image: {image_path}")
    print(f"======================================")
    
    # 1. Run origin module
    print("--- Running Origin Detection Module ---")
    origin_pass, failed_origins, details = check_origin(image_path)
    if origin_pass:
        print("Origin Check: PASS")
    else:
        print("Origin Check: FAIL")
        for reason in failed_origins:
            print(f" - {reason}")
            
    # 2. Run wire module
    print("\n--- Running Wire Detection Module ---")
    f = io.StringIO()
    with contextlib.redirect_stdout(f):
        detect_wiring.check_wiring(image_path)
    wire_output = f.getvalue()
    print(wire_output.strip())
    
    wire_pass = "OVERALL: PASS" in wire_output
    all_pass = origin_pass and wire_pass
    
    # 3. Final Result
    print("\n--- Final Result ---")
    if all_pass:
        print("FINAL STATUS: PASS (Both modules passed)")
    else:
        print("FINAL STATUS: FAIL (One or both modules failed)")

    # 4. Save Image to Result/Pass or Result/Fail
    target_folder = "Pass" if all_pass else "Fail"
    result_dir = os.path.join(os.getcwd(), "Result", target_folder)
    os.makedirs(result_dir, exist_ok=True)
    filename = os.path.basename(image_path)
    out_file = os.path.join(result_dir, filename)
    shutil.copy(image_path, out_file)
    print(f"-> Saved image to: Result/{target_folder}/{filename}")
    return all_pass

def run_dual_view(top_view_path, origin2_path):
    """
    Dual-image runner:
    1. Evaluates Top View image for wire routing and origins.
    2. Evaluates Origin 2 dedicated image for grommet wire orientation.
    3. Combines both evaluations with override logic.
    """
    print(f"\n=======================================================")
    print(f"DUAL-IMAGE INSPECTION PIPELINE")
    print(f"Top View: {os.path.basename(top_view_path)}")
    print(f"Origin 2: {os.path.basename(origin2_path)}")
    print(f"=======================================================")

    # 1. Top View - Origin Detection
    print("\n[Step 1A] Evaluating Top View Origins...")
    top_origin_pass, top_failed_origins, origin_details = check_origin(top_view_path)
    bl_pass = origin_details.get('case1_bl', {}).get('pass', False)
    um_pass = origin_details.get('case2_um', {}).get('pass', False)
    br_pass = origin_details.get('case3_br', {}).get('pass', False)
    
    print(f" - Bottom Left Origin (Orig 1): {'PASS' if bl_pass else 'FAIL'}")
    print(f" - Upper Middle Origin (Orig 2): {'PASS' if um_pass else 'FAIL'}")
    print(f" - Bottom Right Origin (Orig 3): {'PASS' if br_pass else 'FAIL'}")

    # 2. Top View - Wire Routing Detection
    print("\n[Step 1B] Evaluating Top View Wire Routing...")
    f = io.StringIO()
    with contextlib.redirect_stdout(f):
        detect_wiring.check_wiring(top_view_path)
    wire_output = f.getvalue()
    print(wire_output.strip())
    wire_pass = "OVERALL: PASS" in wire_output

    # 3. Origin 2 Dedicated Image Detection
    print("\n[Step 2] Evaluating Dedicated Origin 2 Image...")
    origin2_pass, _, origin2_failed, origin2_details = check_origin2_image(origin2_path, save_result=True)
    print(f" - Origin 2 Dedicated Check: {'PASS' if origin2_pass else 'FAIL'}")
    if not origin2_pass:
        for reason in origin2_failed:
            print(f"   * {reason}")

    # 4. Combined Decision Logic
    # If Origin 2 failed in Top View, but passed in dedicated Origin 2 view -> PASS
    effective_origin2_pass = um_pass or origin2_pass
    combined_origins_pass = bl_pass and br_pass and effective_origin2_pass
    all_pass = wire_pass and combined_origins_pass

    print("\n=======================================================")
    print("COMBINED VERDICT SUMMARY:")
    print(f" - Wire Routing (Top View):    {'PASS' if wire_pass else 'FAIL'}")
    print(f" - Origin 1 (Bottom Left):      {'PASS' if bl_pass else 'FAIL'}")
    print(f" - Origin 2 (Grommet Verified): {'PASS' if effective_origin2_pass else 'FAIL'} " +
          ("(Verified via Image 2)" if (origin2_pass and not um_pass) else ""))
    print(f" - Origin 3 (Bottom Right):     {'PASS' if br_pass else 'FAIL'}")
    print(f"-------------------------------------------------------")
    if all_pass:
        print("FINAL COMBINED STATUS: PASS (All wiring and origins verified)")
    else:
        print("FINAL COMBINED STATUS: FAIL")
    print("=======================================================")

    # 5. Save results to Result/Pass or Result/Fail
    target_folder = "Pass" if all_pass else "Fail"
    result_dir = os.path.join(os.getcwd(), "Result", target_folder)
    os.makedirs(result_dir, exist_ok=True)
    
    shutil.copy(top_view_path, os.path.join(result_dir, "top_" + os.path.basename(top_view_path)))
    shutil.copy(origin2_path, os.path.join(result_dir, "orig2_" + os.path.basename(origin2_path)))
    print(f"-> Processed images archived to Result/{target_folder}/")
    
    return all_pass

if __name__ == "__main__":
    top_img = r"C:\Users\SM 461\.gemini\antigravity\brain\acec8ceb-5079-447b-b23a-89f35e44ef05\.user_uploaded\media_1787810811802.png"
    orig2_img = r"C:\Users\SM 461\.gemini\antigravity\brain\f6bba769-b980-4399-b026-bbd79f6abbdd\.user_uploaded\media_1788433619575.jpg"
    
    if os.path.exists(top_img) and os.path.exists(orig2_img):
        run_dual_view(top_img, orig2_img)
    elif os.path.exists(top_img):
        run_both(top_img)
