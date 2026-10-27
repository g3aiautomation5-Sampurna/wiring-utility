import os
import sys

# Ensure working directory is always the application folder (supports both PyInstaller .exe and script)
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
    os.chdir(BASE_DIR)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    os.chdir(BASE_DIR)

import io
import base64
import shutil
import csv
from datetime import datetime
import cv2
import numpy as np
import time
import json
from flask import Flask, render_template_string, request, jsonify, send_file
import webbrowser
import threading

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from pms_mqtt import pms_mqtt

from detect_origin import check_origin
from detect_origin2 import check_origin3_grommet, check_origin3_image, check_origin2_grommet, check_origin2_image

from pms_json_manager import (
    get_pc_mac_address,
    parse_sticker,
    build_device_autowhitelisting,
    build_serial_no_validation,
    build_status_validation,
    build_report_store,
    build_empty_report_store,
    build_empty_payloads,
    save_payload_to_file,
    load_or_create_config
)

app = Flask(__name__)

# Ensure Result directories exist
os.makedirs(os.path.join(os.getcwd(), "Result", "Pass"), exist_ok=True)
os.makedirs(os.path.join(os.getcwd(), "Result", "Fail"), exist_ok=True)

EXCEL_PATH = os.path.join(os.getcwd(), "Result", "Inspection_Log.xlsx")
CSV_PATH = os.path.join(os.getcwd(), "Result", "Inspection_Log.csv")

def log_to_excel(record):
    """
    Appends the inspection record to Result/Inspection_Log.xlsx and Result/Inspection_Log.csv.
    """
    os.makedirs(os.path.join(os.getcwd(), "Result"), exist_ok=True)

    headers = [
        "Timestamp",
        "Device / Serial No.",
        "Overall Verdict",
        "Origin 1 (BL)",
        "Origin 2 (UM Coil)",
        "Origin 3 (Grommet)",
        "Origin 3 (BR Top)",
        "Wire Case 1 (BL)",
        "Wire Case 2 (UM)",
        "Wire Case 3 (BR)",
        "Diagnostic Summary",
        "Snapshot Folder"
    ]

    row_data = [
        record.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        record.get("device_id", "N/A"),
        "PASS" if record.get("combined_pass") else "FAIL",
        "PASS" if record.get("obl_pass") else "FAIL",
        "PASS" if record.get("oum_pass") else "FAIL",
        "PASS" if record.get("orig3_grommet_pass") else "FAIL",
        "PASS" if record.get("obr_pass") else "FAIL",
        "PASS" if record.get("c1_pass") else "FAIL",
        "PASS" if record.get("c2_pass") else "FAIL",
        "PASS" if record.get("c3_pass") else "FAIL",
        record.get("notes_summary", ""),
        record.get("saved_folder", "")
    ]

    # 1. Update CSV Log
    csv_exists = os.path.exists(CSV_PATH)
    try:
        with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not csv_exists:
                writer.writerow(headers)
            writer.writerow(row_data)
    except Exception as e:
        print(f"Warning: could not write to CSV log: {e}")

    # 2. Update Excel (.xlsx) Log with styling
    file_exists = os.path.exists(EXCEL_PATH)
    if file_exists:
        try:
            wb = openpyxl.load_workbook(EXCEL_PATH)
            ws = wb.active
        except Exception:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Inspection Log"
            file_exists = False
    else:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Inspection Log"

    if not file_exists:
        ws.append(headers)
        header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        header_font = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
        for col_num, h in enumerate(headers, 1):
            c = ws.cell(row=1, column=col_num)
            c.fill = header_fill
            c.font = header_font
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.freeze_panes = "A2"
        ws.row_dimensions[1].height = 26

    ws.append(row_data)
    current_row = ws.max_row
    ws.row_dimensions[current_row].height = 22

    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    pass_fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
    pass_font = Font(name="Segoe UI", size=10, bold=True, color="166534")

    fail_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
    fail_font = Font(name="Segoe UI", size=10, bold=True, color="991B1B")

    regular_font = Font(name="Segoe UI", size=10, color="0F172A")

    for col_idx in range(1, len(row_data) + 1):
        cell = ws.cell(row=current_row, column=col_idx)
        cell.border = thin_border
        cell.font = regular_font
        cell.alignment = Alignment(vertical="center", horizontal="center" if col_idx <= 10 else "left")

        val = str(cell.value)
        if val == "PASS":
            cell.fill = pass_fill
            cell.font = pass_font
        elif val == "FAIL":
            cell.fill = fail_fill
            cell.font = fail_font

    # Auto-fit column widths
    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 14)

    try:
        wb.save(EXCEL_PATH)
    except Exception as e:
        print(f"Warning: could not save Excel file (it may be open): {e}")

def draw_labeled_box(img, pt1, pt2, is_pass, label):
    """Draws bounding box with clear colored badge banner."""
    x1, y1 = pt1
    x2, y2 = pt2
    border_color = (0, 220, 0) if is_pass else (0, 0, 240)
    cv2.rectangle(img, (x1, y1), (x2, y2), border_color, 3)

    badge_text = f" {label}: {'PASS' if is_pass else 'FAIL'} "
    badge_bg = (0, 180, 0) if is_pass else (0, 0, 220)
    
    badge_y = y1 - 8 if y1 > 25 else y1 + 24
    text_size = cv2.getTextSize(badge_text, cv2.FONT_HERSHEY_SIMPLEX, 0.52, 2)[0]
    cv2.rectangle(img, (x1, badge_y - 18), (x1 + text_size[0], badge_y + 4), badge_bg, -1)
    cv2.putText(img, badge_text, (x1, badge_y), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255, 255, 255), 2)

def decode_image(data_uri_or_bytes):
    if isinstance(data_uri_or_bytes, str) and data_uri_or_bytes.startswith("data:image"):
        header, encoded = data_uri_or_bytes.split(",", 1)
        data = base64.b64decode(encoded)
        nparr = np.frombuffer(data, np.uint8)
        return cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    elif isinstance(data_uri_or_bytes, bytes):
        nparr = np.frombuffer(data_uri_or_bytes, np.uint8)
        return cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    return None

def encode_image_to_base64(img_bgr):
    ret, buf = cv2.imencode(".jpg", img_bgr)
    if not ret:
        return None
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode("utf-8")

def process_top_inspection(img_raw):
    img_top = cv2.resize(img_raw, (1024, 576))
    hsv_top = cv2.cvtColor(img_top, cv2.COLOR_BGR2HSV)

    # 1. ORIGINS EVALUATION & ANNOTATION
    origin_pass, top_failed_origins, origin_details = check_origin(img_top)
    obl_pass = origin_details.get('case1_bl', {}).get('pass', False)
    oum_pass = origin_details.get('case2_um', {}).get('pass', False)
    obr_pass = origin_details.get('case3_br', {}).get('pass', False)

    img_origins = img_top.copy()
    draw_labeled_box(img_origins, (370, 410), (470, 565), obl_pass, "Origin 1 (BL)")
    draw_labeled_box(img_origins, (470, 15), (690, 100), oum_pass, "Origin 2 (UM)")
    draw_labeled_box(img_origins, (540, 415), (660, 565), obr_pass, "Origin 3 (BR)")

    # 2. WIRES EVALUATION & ANNOTATION
    mask_r = cv2.inRange(hsv_top, (0, 100, 50), (12, 255, 255)) + cv2.inRange(hsv_top, (160, 100, 50), (180, 255, 255))
    mask_b = cv2.inRange(hsv_top, (0, 0, 0), (180, 255, 45))

    # Case 1 (BL)
    bl_r = mask_r[270:330, 310:470]
    bl_b = mask_b[270:330, 310:470]
    xr_bl = np.where(bl_r > 0)[1]
    xb_bl = np.where(bl_b > 0)[1]
    rx_bl = np.median(xr_bl) if len(xr_bl) else -1
    bx_bl = np.median(xb_bl) if len(xb_bl) else -1
    bl_wire_pass = bool(rx_bl < bx_bl) if (rx_bl != -1 and bx_bl != -1) else True
    # Case 2 (UM) - Detect only origins; if origins pass, wiring passes
    um_wire_pass = bool(oum_pass)

    # Case 3 (BR) - Wire routing at PCB exit (y: 390..440, x: 570..670)
    br_r = mask_r[390:440, 570:670]
    br_b = mask_b[390:440, 570:670]
    xr_br = np.where(br_r > 0)[1] + 570
    xb_br = np.where(br_b > 0)[1] + 570
    rx_br = np.median(xr_br) if len(xr_br) > 15 else -1
    bx_br = np.median(xb_br) if len(xb_br) > 15 else -1
    br_wire_pass = bool(rx_br < bx_br) if (rx_br != -1 and bx_br != -1) else True

    img_wires = img_top.copy()
    draw_labeled_box(img_wires, (310, 260), (470, 555), bl_wire_pass, "Case 1 (BL)")
    draw_labeled_box(img_wires, (470, 0), (710, 200), um_wire_pass, "Case 2 (UM)")
    draw_labeled_box(img_wires, (570, 385), (715, 565), br_wire_pass, "Case 3 (BR)")

    return {
        "top_wires_annotated": encode_image_to_base64(img_wires),
        "top_origins_annotated": encode_image_to_base64(img_origins),
        "img_wires": img_wires,
        "img_origins": img_origins,
        "obl_pass": bool(obl_pass),
        "oum_pass": bool(oum_pass),
        "obr_pass": bool(obr_pass),
        "c1_pass": bool(bl_wire_pass),
        "c2_pass": bool(um_wire_pass),
        "c3_pass": bool(br_wire_pass)
    }

def process_orig3_inspection(img_raw):
    is_p, img_o3, failed_o3, details_o3 = check_origin3_image(img_raw, save_result=False)
    return {
        "orig3_annotated": encode_image_to_base64(img_o3),
        "img_o3": img_o3,
        "orig3_grommet_pass": bool(is_p),
        "failed_reasons": failed_o3
    }

process_orig2_inspection = process_orig3_inspection

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Wiring & Origin Inspection</title>
    <style>
        :root {
            --bg-base: #0b0f19;
            --bg-surface: #121826;
            --bg-surface-elevated: #1a2333;
            --border-subtle: #1e293b;
            --border-highlight: #334155;
            --text-main: #f1f5f9;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --accent-primary: #3b82f6;
            --accent-primary-hover: #2563eb;
            --color-pass: #10b981;
            --color-pass-bg: rgba(16, 185, 129, 0.12);
            --color-fail: #ef4444;
            --color-fail-bg: rgba(239, 68, 68, 0.12);
            --radius-sm: 6px;
            --radius-md: 10px;
            --radius-lg: 14px;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        }

        body {
            background-color: var(--bg-base);
            color: var(--text-main);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            overflow-x: hidden;
            font-size: 14px;
        }

        /* Minimal Header */
        header {
            background: var(--bg-surface);
            border-bottom: 1px solid var(--border-subtle);
            padding: 8px 18px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 14px;
            min-height: 56px;
            flex-wrap: wrap;
        }

        .brand-group {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .brand-icon {
            width: 28px;
            height: 28px;
            background: linear-gradient(135deg, #3b82f6, #6366f1);
            border-radius: var(--radius-sm);
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 800;
            font-size: 14px;
            color: #fff;
        }

        .brand-title {
            font-size: 15px;
            font-weight: 700;
            letter-spacing: -0.2px;
            color: #ffffff;
        }

        .brand-tag {
            font-size: 11px;
            color: var(--text-muted);
            background: var(--bg-surface-elevated);
            padding: 2px 7px;
            border-radius: 4px;
            border: 1px solid var(--border-subtle);
        }

        /* Pill Navigation in Header */
        .nav-pills {
            display: flex;
            background: var(--bg-base);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-sm);
            padding: 3px;
            gap: 2px;
        }

        .nav-pill {
            background: transparent;
            border: none;
            color: var(--text-secondary);
            font-size: 12px;
            font-weight: 600;
            padding: 5px 12px;
            border-radius: 4px;
            cursor: pointer;
            transition: all 0.15s ease;
            display: inline-flex;
            align-items: center;
            gap: 5px;
        }

        .nav-pill:hover {
            color: var(--text-main);
        }

        .nav-pill.active {
            background: var(--bg-surface-elevated);
            color: #60a5fa;
            box-shadow: 0 1px 3px rgba(0,0,0,0.3);
        }

        .nav-divider {
            width: 1px;
            height: 18px;
            background: var(--border-subtle);
            margin: auto 4px;
        }

        /* Header Right Controls */
        .header-actions {
            display: flex;
            align-items: center;
            gap: 8px;
            flex-wrap: wrap;
        }

        /* QR Code Input Container */
        .qr-input-group {
            display: flex;
            align-items: center;
            background: var(--bg-base);
            border: 1px solid var(--border-highlight);
            border-radius: var(--radius-sm);
            padding: 3px 8px;
            gap: 6px;
            transition: all 0.2s ease;
        }

        .qr-input-group:focus-within {
            border-color: #3b82f6;
            box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
        }

        .qr-icon {
            font-size: 13px;
            opacity: 0.85;
        }

        .qr-input {
            background: transparent;
            border: none;
            color: #f8fafc;
            font-size: 12px;
            font-weight: 600;
            width: 210px;
            outline: none;
        }

        .qr-badge {
            font-size: 10px;
            padding: 2px 7px;
            border-radius: 4px;
            font-weight: 700;
            white-space: nowrap;
            user-select: none;
            letter-spacing: 0.3px;
            transition: all 0.2s ease;
        }

        .qr-badge.idle {
            background: rgba(100, 116, 139, 0.2);
            color: #94a3b8;
            border: 1px solid #334155;
        }

        .qr-badge.validating {
            background: rgba(245, 158, 11, 0.2);
            color: #fbbf24;
            border: 1px solid #f59e0b;
        }

        .qr-badge.success {
            background: rgba(16, 185, 129, 0.25);
            color: #34d399;
            border: 1px solid #10b981;
        }

        .qr-badge.failed {
            background: rgba(239, 68, 68, 0.25);
            color: #f87171;
            border: 1px solid #ef4444;
        }

        .qr-input::placeholder {
            color: var(--text-muted);
            font-weight: 400;
        }

        .btn-clear-qr {
            background: transparent;
            border: none;
            color: var(--text-muted);
            font-size: 11px;
            cursor: pointer;
            padding: 0 2px;
            line-height: 1;
        }

        .btn-clear-qr:hover {
            color: #f87171;
        }

        .btn-header {
            background: var(--bg-surface-elevated);
            color: var(--text-secondary);
            border: 1px solid var(--border-subtle);
            padding: 6px 12px;
            border-radius: var(--radius-sm);
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            transition: all 0.15s ease;
        }

        .btn-header:hover {
            color: var(--text-main);
            border-color: var(--border-highlight);
            background: #222d42;
        }

        /* PMS JSON Modal */
        .modal-backdrop {
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0, 0, 0, 0.75);
            backdrop-filter: blur(4px);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 9999;
        }
        .modal-box {
            background: #111827;
            border: 1px solid #374151;
            border-radius: 8px;
            width: 760px;
            max-width: 92vw;
            max-height: 85vh;
            display: flex;
            flex-direction: column;
            box-shadow: 0 20px 40px rgba(0,0,0,0.6);
        }
        .modal-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 14px 20px;
            border-bottom: 1px solid #374151;
        }
        .modal-header h3 {
            margin: 0;
            font-size: 15px;
            font-weight: 600;
            color: #f3f4f6;
        }
        .modal-close {
            background: none;
            border: none;
            color: #9ca3af;
            font-size: 22px;
            cursor: pointer;
            line-height: 1;
        }
        .modal-close:hover { color: #fff; }
        .modal-tabs {
            display: flex;
            gap: 8px;
            padding: 10px 20px;
            background: #162032;
            border-bottom: 1px solid #374151;
            overflow-x: auto;
        }
        .modal-tab {
            background: transparent;
            border: 1px solid transparent;
            color: #94a3b8;
            font-size: 11px;
            font-weight: 600;
            padding: 6px 12px;
            border-radius: 4px;
            cursor: pointer;
            white-space: nowrap;
        }
        .modal-tab.active {
            background: #3b82f6;
            color: #fff;
        }
        .modal-pre {
            flex: 1;
            margin: 0;
            padding: 16px 20px;
            background: #0b0f19;
            color: #38bdf8;
            font-family: 'Consolas', 'Courier New', monospace;
            font-size: 12px;
            line-height: 1.5;
            overflow: auto;
            max-height: 52vh;
        }
        .modal-footer {
            display: flex;
            justify-content: flex-end;
            gap: 10px;
            padding: 12px 20px;
            border-top: 1px solid #374151;
            background: #162032;
        }
        .btn-copy-json {
            background: #3b82f6;
            color: #fff;
            border: none;
            padding: 6px 14px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
        }
        .btn-copy-json:hover { background: #2563eb; }
        .btn-modal-close {
            background: #1f2937;
            color: #d1d5db;
            border: 1px solid #374151;
            padding: 6px 14px;
            border-radius: 4px;
            font-size: 12px;
            cursor: pointer;
        }
        .btn-modal-close:hover { color: #fff; }

        /* Slide In/Out Config Toast Popup */
        #configToastContainer {
            position: fixed;
            top: 24px;
            right: 24px;
            z-index: 99999;
            pointer-events: none;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        .config-toast {
            pointer-events: auto;
            min-width: 360px;
            max-width: 460px;
            background: #111827;
            border: 1px solid #374151;
            border-radius: 8px;
            box-shadow: 0 12px 30px rgba(0, 0, 0, 0.6), 0 2px 6px rgba(0, 0, 0, 0.4);
            overflow: hidden;
            position: relative;
            transform: translateX(120%);
            opacity: 0;
            transition: transform 0.35s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.35s ease;
            cursor: pointer;
        }

        .config-toast.show {
            transform: translateX(0);
            opacity: 1;
        }

        .config-toast.hide {
            transform: translateX(120%);
            opacity: 0;
        }

        .config-toast.success {
            border-left: 5px solid #10b981;
        }

        .config-toast.failed {
            border-left: 5px solid #ef4444;
        }

        .toast-content {
            display: flex;
            align-items: flex-start;
            gap: 12px;
            padding: 14px 16px;
        }

        .toast-icon {
            width: 32px;
            height: 32px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 16px;
            font-weight: bold;
            flex-shrink: 0;
            margin-top: 1px;
        }

        .toast-icon.success {
            background: rgba(16, 185, 129, 0.2);
            color: #10b981;
            border: 1px solid rgba(16, 185, 129, 0.4);
        }

        .toast-icon.failed {
            background: rgba(239, 68, 68, 0.2);
            color: #ef4444;
            border: 1px solid rgba(239, 68, 68, 0.4);
        }

        .toast-text {
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .toast-header-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
        }

        .toast-title {
            font-size: 14px;
            font-weight: 700;
            color: #f8fafc;
        }

        .toast-badge {
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.5px;
            padding: 2px 7px;
            border-radius: 3px;
        }

        .toast-badge.success {
            background: rgba(16, 185, 129, 0.2);
            color: #34d399;
            border: 1px solid #059669;
        }

        .toast-badge.failed {
            background: rgba(239, 68, 68, 0.2);
            color: #f87171;
            border: 1px solid #dc2626;
        }

        .toast-body {
            font-size: 12px;
            color: #cbd5e1;
            line-height: 1.45;
        }

        .toast-meta {
            display: flex;
            gap: 12px;
            font-size: 11px;
            color: #94a3b8;
            margin-top: 2px;
        }

        .toast-meta span strong {
            color: #38bdf8;
            font-family: 'Consolas', monospace;
        }

        .toast-close-btn {
            background: none;
            border: none;
            color: #94a3b8;
            font-size: 18px;
            cursor: pointer;
            padding: 0 4px;
            line-height: 1;
        }

        .toast-close-btn:hover {
            color: #fff;
        }

        /* Progress timer bar at the bottom */
        .toast-progress {
            position: absolute;
            bottom: 0;
            left: 0;
            height: 3px;
            width: 100%;
            background: rgba(255, 255, 255, 0.1);
        }

        .toast-progress-bar {
            height: 100%;
            width: 100%;
            transform-origin: left;
        }

        .toast-progress-bar.success {
            background: #10b981;
        }

        .toast-progress-bar.failed {
            background: #ef4444;
        }

        @keyframes toastProgressCountdown {
            from { transform: scaleX(1); }
            to { transform: scaleX(0); }
        }

        .btn-start {
            background: linear-gradient(135deg, #10b981, #059669);
            color: #ffffff;
            border: none;
            padding: 7px 18px;
            border-radius: var(--radius-sm);
            font-size: 13px;
            font-weight: 700;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 6px;
            box-shadow: 0 2px 8px rgba(16, 185, 129, 0.3);
            transition: all 0.2s ease;
        }

        .btn-start:not(:disabled):hover {
            background: linear-gradient(135deg, #059669, #047857);
            transform: translateY(-1px);
            box-shadow: 0 4px 14px rgba(16, 185, 129, 0.45);
        }

        .btn-start:not(:disabled):active {
            transform: translateY(0);
        }

        .btn-start:disabled {
            background: #1e293b;
            color: #64748b;
            border: 1px solid #334155;
            cursor: not-allowed;
            box-shadow: none;
            transform: none;
            opacity: 0.6;
        }

        .btn-start.ready-pulse {
            animation: pulse-ready 1.8s infinite;
        }

        @keyframes pulse-ready {
            0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.6); }
            70% { box-shadow: 0 0 0 8px rgba(16, 185, 129, 0); }
            100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
        }

        /* Layout */
        .main-layout {
            display: flex;
            flex: 1;
            padding: 14px 18px;
            gap: 14px;
            max-width: 1750px;
            margin: 0 auto;
            width: 100%;
        }

        .viewport-wrapper {
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 10px;
            min-width: 0;
        }

        .sidebar-wrapper {
            width: 360px;
            display: flex;
            flex-direction: column;
            gap: 10px;
            flex-shrink: 0;
        }

        /* Viewport Card */
        .viewport-card {
            background: var(--bg-surface);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-md);
            overflow: hidden;
            display: flex;
            flex-direction: column;
            flex: 1;
            min-height: 520px;
        }

        .viewport-content {
            flex: 1;
            display: flex;
            position: relative;
            background: #06090e;
            align-items: center;
            justify-content: center;
            overflow: hidden;
        }

        /* Full Single Camera Viewport */
        .camera-full-container {
            width: 100%;
            height: 100%;
            position: absolute;
            top: 0;
            left: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: border-color 0.2s;
        }

        .camera-full-container.drag-over {
            background: rgba(59, 130, 246, 0.1);
        }

        .camera-overlay-badge {
            position: absolute;
            top: 14px;
            left: 14px;
            background: rgba(11, 15, 25, 0.85);
            backdrop-filter: blur(6px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            padding: 5px 12px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 8px;
            z-index: 10;
        }

        .badge-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #64748b;
        }

        .badge-dot.active {
            background: var(--color-pass);
            box-shadow: 0 0 8px var(--color-pass);
        }

        .camera-actions-overlay {
            position: absolute;
            top: 14px;
            right: 14px;
            z-index: 10;
            display: flex;
            gap: 8px;
        }

        .btn-pill-action {
            background: rgba(18, 24, 38, 0.9);
            color: #cbd5e1;
            border: 1px solid rgba(255, 255, 255, 0.12);
            padding: 5px 10px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 600;
            cursor: pointer;
            backdrop-filter: blur(4px);
            transition: all 0.15s ease;
        }

        .btn-pill-action:hover {
            background: #3b82f6;
            color: #fff;
            border-color: #3b82f6;
        }

        .camera-full-container video, .camera-full-container img {
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
            user-select: none;
        }

        .guide-canvas {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            pointer-events: none;
        }

        /* Single Result View */
        .single-view {
            width: 100%;
            height: 100%;
            position: absolute;
            top: 0;
            left: 0;
            display: none;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 8px;
        }

        .single-view img {
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
            border-radius: 4px;
        }

        /* Bottom Minimal Controls Bar */
        .bottom-bar {
            background: var(--bg-surface);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-sm);
            padding: 7px 12px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-size: 12px;
            color: var(--text-secondary);
        }

        .cam-controls {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .cam-controls select {
            background: var(--bg-surface-elevated);
            color: var(--text-main);
            border: 1px solid var(--border-subtle);
            border-radius: 4px;
            padding: 3px 8px;
            font-size: 11px;
            outline: none;
            max-width: 150px;
        }

        .btn-icon {
            background: var(--bg-surface-elevated);
            color: var(--text-secondary);
            border: 1px solid var(--border-subtle);
            padding: 3px 8px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 11px;
        }

        .btn-icon:hover {
            color: var(--text-main);
            border-color: var(--border-highlight);
        }

        /* Sidebar Elements */
        .sidebar-card {
            background: var(--bg-surface);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-md);
            padding: 14px;
        }

        /* Verdict Box */
        .verdict-box {
            text-align: center;
            padding: 16px 12px;
            border-radius: var(--radius-md);
            border: 1px solid var(--border-subtle);
            background: var(--bg-surface);
            transition: all 0.3s ease;
        }

        .verdict-box.pass {
            background: var(--color-pass-bg);
            border-color: rgba(16, 185, 129, 0.4);
        }

        .verdict-box.fail {
            background: var(--color-fail-bg);
            border-color: rgba(239, 68, 68, 0.4);
        }

        .verdict-status {
            font-size: 20px;
            font-weight: 800;
            letter-spacing: 0.5px;
            color: var(--text-muted);
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }

        .verdict-box.pass .verdict-status {
            color: var(--color-pass);
        }

        .verdict-box.fail .verdict-status {
            color: var(--color-fail);
        }

        .verdict-device {
            font-size: 12px;
            font-weight: 700;
            color: var(--text-main);
            margin-top: 5px;
        }

        .verdict-desc {
            font-size: 11px;
            color: var(--text-muted);
            margin-top: 3px;
        }

        /* Checklist Section */
        .section-header {
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-muted);
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .check-table {
            width: 100%;
            display: flex;
            flex-direction: column;
            gap: 3px;
        }

        .check-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 6px 8px;
            background: rgba(255, 255, 255, 0.02);
            border-radius: 4px;
            font-size: 12px;
        }

        .check-name {
            display: flex;
            align-items: center;
            gap: 8px;
            color: var(--text-main);
            font-weight: 500;
        }

        .status-pill {
            font-size: 11px;
            font-weight: 700;
            padding: 2px 7px;
            border-radius: 4px;
            background: #1e293b;
            color: #64748b;
        }

        .status-pill.pass {
            background: rgba(16, 185, 129, 0.15);
            color: #34d399;
        }

        .status-pill.fail {
            background: rgba(239, 68, 68, 0.15);
            color: #f87171;
        }

        /* Diagnostics Accordion */
        details {
            background: var(--bg-surface);
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-md);
            overflow: hidden;
        }

        details summary {
            padding: 10px 14px;
            font-size: 12px;
            font-weight: 600;
            color: var(--text-secondary);
            cursor: pointer;
            user-select: none;
            outline: none;
        }

        details summary:hover {
            color: var(--text-main);
        }

        .diag-log {
            padding: 10px 14px;
            background: #080c14;
            color: #cbd5e1;
            font-family: 'Consolas', monospace;
            font-size: 11px;
            line-height: 1.4;
            white-space: pre-wrap;
            max-height: 140px;
            overflow-y: auto;
            border-top: 1px solid var(--border-subtle);
        }

        /* Pulse Flash on Start */
        @keyframes pulse-flash {
            0% { opacity: 0.3; }
            100% { opacity: 1; }
        }
        .flash-anim {
            animation: pulse-flash 0.25s ease-out;
        }

        input[type="file"] {
            display: none;
        }

        /* MQTT Connection Indicator */
        .mqtt-status {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 7px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            white-space: nowrap;
        }

        .mqtt-status-dot {
            width: 9px;
            height: 9px;
            border-radius: 50%;
            background: #ef4444;
            flex-shrink: 0;
        }

        .mqtt-status.disconnected {
            color: #fca5a5;
            background: rgba(239, 68, 68, 0.12);
        }

        .mqtt-status.connected {
            color: #86efac;
            background: rgba(34, 197, 94, 0.12);
        }

        .mqtt-status.connected .mqtt-status-dot {
            background: #22c55e;
            box-shadow: 0 0 7px rgba(34, 197, 94, 0.65);
        }
    </style>
</head>
<body>
    <!-- HEADER -->
    <header>
        <div class="brand-group">
            <div class="brand-icon">W</div>
            <div>
                <span class="brand-title">Wiring Inspection</span>
                <span class="brand-tag">Dual Camera</span>
            </div>
        </div>

        <!-- Pill Nav (Live feeds & Inspection Results) -->
        <div class="nav-pills">
            <button class="nav-pill active" id="pillLiveTop" onclick="setViewMode('live_top')">📹 Live Top View</button>
            <button class="nav-pill" id="pillLiveOrig" onclick="setViewMode('live_orig3')">📹 Live Origin 3</button>
            <div class="nav-divider"></div>
            <button class="nav-pill" id="pillTopWires" onclick="setViewMode('res_top_wires')">🔌 Top Wires</button>
            <button class="nav-pill" id="pillTopOrigins" onclick="setViewMode('res_top_origins')">📍 Top Origins</button>
            <button class="nav-pill" id="pillOrig3" onclick="setViewMode('res_orig3')">🎯 Origin 3</button>
        </div>

        <!-- Actions (QR input, Batch Upload, Excel, START) -->
        <div class="header-actions">
            <!-- QR / Barcode Scanner Input Box -->
            <div class="qr-input-group" title="Scan QR Code (Format: Id: ..; Sr: ..;) or Device Serial No.">
                <span class="qr-icon">🏷️</span>
                <input type="text" id="deviceSerialInput" class="qr-input" placeholder="Scan QR (Id: ..; Sr: ..;) or Serial..." autocomplete="off" autofocus />
                <span id="qrValidationBadge" class="qr-badge idle" title="PMS Validation Status">Scan to Validate</span>
                <button class="btn-clear-qr" id="btnClearQr" onclick="clearQrInput()" title="Clear Device ID">✕</button>
            </div>

            <button class="btn-header" onclick="document.getElementById('fileBothInput').click()" title="Select both test images">
                📁 Upload
            </button>
            <button class="btn-header" onclick="openExcelSheet()" title="Open Inspection Log in Microsoft Excel">
                📊 Excel Log
            </button>
            <button class="btn-header" onclick="openPmsJsonModal()" title="View & Copy Selec PMS JSON output">
                📋 PMS JSON
            </button>
            <div id="mqttStatus" class="mqtt-status disconnected">
                <span class="mqtt-status-dot"></span>
                <span id="mqttStatusText">SERVER  Disconnected</span>
            </div>
            <button class="btn-header" id="btnLiveReset" onclick="resetToLiveCameras()" title="Switch back to live video streams">
                🔄 Live
            </button>
            <button class="btn-start" id="btnStartInspection" onclick="triggerStartInspection()" disabled title="Scan QR Code and wait for PMS server validation (CONFIG SUCCESSFUL) to activate START">
                ▶ START
            </button>
        </div>
    </header>

    <!-- MAIN BODY -->
    <div class="main-layout">
        <!-- LEFT: Viewport & Bottom Bar -->
        <div class="viewport-wrapper">
            <div class="viewport-card">
                <div class="viewport-content" id="viewportArea">
                    <!-- Live Top Camera Viewport (Full Screen) -->
                    <div class="camera-full-container" id="containerTop" ondragover="handleDragOver(event)" ondragleave="handleDragLeave(event)" ondrop="handleDrop(event, 'top')" onclick="handleBoxClick('top')">
                        <div class="camera-overlay-badge">
                            <span class="badge-dot" id="dotTop"></span>
                            <span id="labelTop">Top View (Arducam_TOP)</span>
                        </div>
                        <div class="camera-actions-overlay">
                            <button class="btn-pill-action" onclick="event.stopPropagation(); setViewMode('live_orig3')">Switch to Origin 3 ➔</button>
                            <button class="btn-pill-action" onclick="event.stopPropagation(); document.getElementById('fileTopInput').click()">📁 Upload Image</button>
                        </div>
                        <video id="videoTop" autoplay playsinline muted></video>
                        <img id="imgUploadTop" style="display: none;" alt="Top Preview" />
                        <canvas id="overlayTop" class="guide-canvas"></canvas>
                    </div>

                    <!-- Live Origin Camera Viewport (Full Screen) -->
                    <div class="camera-full-container" id="containerOrig" style="display: none;" ondragover="handleDragOver(event)" ondragleave="handleDragLeave(event)" ondrop="handleDrop(event, 'orig3')" onclick="handleBoxClick('orig3')">
                        <div class="camera-overlay-badge">
                            <span class="badge-dot" id="dotOrig"></span>
                            <span id="labelOrig">Origin View (Arducam_ORIGIN - Origin 3)</span>
                        </div>
                        <div class="camera-actions-overlay">
                            <button class="btn-pill-action" onclick="event.stopPropagation(); setViewMode('live_top')">⬅ Switch to Top View</button>
                            <button class="btn-pill-action" onclick="event.stopPropagation(); document.getElementById('fileOrig3Input').click()">📁 Upload Image</button>
                        </div>
                        <video id="videoOrig3" autoplay playsinline muted></video>
                        <img id="imgUploadOrig" style="display: none;" alt="Origin Preview" />
                        <canvas id="overlayOrig3" class="guide-canvas"></canvas>
                    </div>

                    <!-- Single Result View -->
                    <div class="single-view" id="singleViewArea">
                        <div class="camera-overlay-badge">
                            <span id="resultViewLabel">Inspection Result</span>
                        </div>
                        <div class="camera-actions-overlay">
                            <button class="btn-pill-action" onclick="replaceImageForCurrentTab()">📁 Replace Image</button>
                            <button class="btn-pill-action" onclick="setViewMode('live_top')">🔄 Back to Live</button>
                        </div>
                        <img id="singleResultImg" alt="Result Inspection View" />
                    </div>
                </div>
            </div>

            <!-- Bottom Minimal Controls -->
            <div class="bottom-bar">
                <div class="cam-controls">
                    <span>Top:</span>
                    <select id="selectCamTop" onchange="onCameraSelectionChanged()"></select>
                    <span>Origin:</span>
                    <select id="selectCamOrig" onchange="onCameraSelectionChanged()"></select>
                    <button class="btn-icon" onclick="swapCameras()" title="Swap Camera Inputs">⇄ Swap</button>
                    <button class="btn-icon" onclick="restartLiveCameras()" title="Refresh Camera Streams">🔄 Refresh</button>
                </div>
                <div id="footerStatus">Scan QR Code or enter Device Serial No. to validate with server and activate START.</div>
            </div>
        </div>

        <!-- RIGHT: Clean Minimal Sidebar -->
        <div class="sidebar-wrapper">
            <!-- Overall Verdict Banner -->
            <div class="verdict-box" id="verdictBanner">
                <div class="verdict-status" id="verdictText">AWAITING START</div>
                <div class="verdict-device" id="verdictDevice">Device: —</div>
                <div class="verdict-desc" id="verdictDesc">Scan QR code to validate with PMS server & activate START button</div>
            </div>

            <!-- Unified Results Checklist -->
            <div class="sidebar-card">
                <div class="section-header">
                    <span>Origins Verification</span>
                    <span style="font-size: 10px; color: var(--text-muted);">Dual Camera Check</span>
                </div>
                <div class="check-table">
                    <div class="check-row">
                        <div class="check-name">Origin 3 (Grommet View)</div>
                        <span class="status-pill" id="pillOrig3Grommet">—</span>
                    </div>
                    <div class="check-row">
                        <div class="check-name">Origin 1 (Bottom Left)</div>
                        <span class="status-pill" id="pillObl">—</span>
                    </div>
                    <div class="check-row">
                        <div class="check-name">Origin 2 (Top Middle)</div>
                        <span class="status-pill" id="pillOum">—</span>
                    </div>
                    <div class="check-row">
                        <div class="check-name">Origin 3 (Bottom Right)</div>
                        <span class="status-pill" id="pillObr">—</span>
                    </div>
                </div>

                <div class="section-header" style="margin-top: 14px;">
                    <span>Wiring Routing</span>
                    <span style="font-size: 10px; color: var(--text-muted);">Top View</span>
                </div>
                <div class="check-table">
                    <div class="check-row">
                        <div class="check-name">Case 1: Bottom Left</div>
                        <span class="status-pill" id="pillC1">—</span>
                    </div>
                    <div class="check-row">
                        <div class="check-name">Case 2: Upper Middle</div>
                        <span class="status-pill" id="pillC2">—</span>
                    </div>
                    <div class="check-row">
                        <div class="check-name">Case 3: Bottom Right</div>
                        <span class="status-pill" id="pillC3">—</span>
                    </div>
                </div>
            </div>

            <!-- Collapsible Diagnostic Log -->
            <details>
                <summary>Diagnostic Details</summary>
                <div class="diag-log" id="diagLog">Ready for inspection.</div>
            </details>
        </div>
    </div>

    <!-- Hidden File Inputs -->
    <input type="file" id="fileTopInput" accept="image/*" onchange="handleManualUpload(event, 'top')">
    <input type="file" id="fileOrig3Input" accept="image/*" onchange="handleManualUpload(event, 'orig3')">
    <input type="file" id="fileBothInput" accept="image/*" multiple onchange="handleBatchUpload(event)">

    <!-- JAVASCRIPT CONTROLLER -->
    <script>
        let streamTop = null;
        let streamOrig3 = null;
        let animFrameTop = null;
        let animFrameOrig3 = null;

        let rawTopBase64 = null;
        let rawOrig3Base64 = null;
        let uploadedTopBase64 = null;
        let uploadedOrigBase64 = null;

        let resTopWiresAnnotated = null;
        let resTopOriginsAnnotated = null;
        let resOrig3Annotated = null;

        let currentViewMode = 'live_top';
        let devicesList = [];

        const videoTop = document.getElementById('videoTop');
        const videoOrig3 = document.getElementById('videoOrig3');
        const imgUploadTop = document.getElementById('imgUploadTop');
        const imgUploadOrig = document.getElementById('imgUploadOrig');

        const overlayTop = document.getElementById('overlayTop');
        const overlayOrig3 = document.getElementById('overlayOrig3');
        const containerTop = document.getElementById('containerTop');
        const containerOrig = document.getElementById('containerOrig');
        const singleViewArea = document.getElementById('singleViewArea');
        const singleResultImg = document.getElementById('singleResultImg');

        const selectCamTop = document.getElementById('selectCamTop');
        const selectCamOrig = document.getElementById('selectCamOrig');
        const btnStartInspection = document.getElementById('btnStartInspection');
        const deviceSerialInput = document.getElementById('deviceSerialInput');

        function parseQrInput(text) {
            if (!text) return { id: '', sr: '' };
            const idMatch = text.match(/(?:^|[;,|\s])\s*(?:APoNumberId|APO(?:_?ID)?|Id)\s*[:=]\s*([^;,|]+)/i);
            const srMatch = text.match(/(?:^|[;,|\s])\s*(?:DeviceSerial(?:No)?|Serial(?:No)?|Sr(?:No)?|SN)\s*[:=]\s*([^;,|]+)/i);
            let id = idMatch ? idMatch[1].trim() : '';
            let sr = srMatch ? srMatch[1].trim() : '';
            if (!id && !sr) {
                for (const sep of [',', '|', ';', '/']) {
                    if (text.includes(sep)) {
                        const parts = text.split(sep).map(p => p.trim()).filter(Boolean);
                        if (parts.length >= 2) {
                            id = parts[0];
                            sr = parts[1];
                            break;
                        }
                    }
                }
                if (!sr && !id) {
                    sr = text.trim();
                }
            }
            return { id, sr };
        }

        let currentValidatedCode = null;
        let isValidating = false;

        async function validateScannedDevice() {
            const rawVal = deviceSerialInput.value.trim();
            if (!rawVal) {
                setValidationState('idle', 'Scan to Validate');
                btnStartInspection.disabled = true;
                btnStartInspection.classList.remove('ready-pulse');
                pmsPayloadsCache = null;
                document.getElementById('footerStatus').innerText = "Scan QR Code or enter Device Serial No. to validate with server and activate START.";
                return;
            }

            if (isValidating) return;

            // If already validated for this exact string and button is currently active
            if (currentValidatedCode === rawVal && !btnStartInspection.disabled) {
                return;
            }

            isValidating = true;
            btnStartInspection.disabled = true;
            btnStartInspection.classList.remove('ready-pulse');
            pmsPayloadsCache = null; // Important: "else these json fields will stay empty"
            setValidationState('validating', '⏳ Sending Payloads...');
            document.getElementById('footerStatus').innerText = "Sending Whitelisting, SerialNo, and StatusValidation payloads to server. Waiting for CONFIG SUCCESSFUL...";

            try {
                const res = await fetch('/api/pms/validate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ device_id: rawVal })
                });
                const data = await res.json();

                if (res.ok && data.validated) {
                    currentValidatedCode = rawVal;
                    // Response received from server, UtcRequest_ID matched, CONFIG SUCCESSFUL
                    pmsPayloadsCache = data.payloads;
                    pmsPayloadsCache.server_responses = data.server_responses || {};
                    pmsPayloadsCache._forDevice = rawVal;
                    setValidationState('success', '✔ CONFIG SUCCESSFUL');
                    btnStartInspection.disabled = false;
                    btnStartInspection.classList.add('ready-pulse');
                    document.getElementById('footerStatus').innerText = `✔ Server responded CONFIG SUCCESSFUL for Serial [${data.serial_no}], APO [${data.apo_id}]. START button ACTIVATED.`;

                    // Display popup when config is successful
                    showConfigResultPopup(true, {
                        title: "PMS Configuration Successful",
                        serial_no: data.serial_no,
                        apo_id: data.apo_id,
                        message: "All 3 validation payloads (Whitelisting, SerialNo, Status) confirmed CONFIG SUCCESSFUL by server. The START button is now ACTIVATED."
                    });
                } else {
                    currentValidatedCode = null;
                    pmsPayloadsCache = null; // fields stay empty!
                    setValidationState('failed', '✖ Validation Failed');
                    btnStartInspection.disabled = true;
                    btnStartInspection.classList.remove('ready-pulse');
                    const errMsg = data.message || 'Server rejected configuration or request ID mismatched.';
                    document.getElementById('footerStatus').innerText = `✖ PMS Validation Failed: ${errMsg}. START button remains disabled.`;

                    // Display popup when config is unsuccessful
                    showConfigResultPopup(false, {
                        title: "PMS Configuration Failed",
                        serial_no: data.serial_no || rawVal,
                        apo_id: data.apo_id,
                        error: errMsg,
                        message: "Server rejected configuration or request ID mismatched. START button remains disabled and JSON fields stay empty."
                    });
                }
            } catch (err) {
                currentValidatedCode = null;
                pmsPayloadsCache = null; // fields stay empty!
                setValidationState('failed', '✖ Server Error');
                btnStartInspection.disabled = true;
                btnStartInspection.classList.remove('ready-pulse');
                document.getElementById('footerStatus').innerText = `✖ Cannot reach PMS validation service: ${err.message}. START button disabled.`;

                // Display popup when config is unsuccessful due to network/timeout error
                showConfigResultPopup(false, {
                    title: "PMS Connection Error / Timeout",
                    serial_no: rawVal,
                    error: err.message,
                    message: "Cannot reach PMS validation service or server response timed out. START button remains disabled."
                });
            } finally {
                isValidating = false;
            }
        }

        function setValidationState(state, text) {
            const badge = document.getElementById('qrValidationBadge');
            if (!badge) return;
            badge.className = `qr-badge ${state}`;
            badge.innerText = text;
        }

        function focusQrInput() {
            if (deviceSerialInput) {
                deviceSerialInput.focus();
                if (deviceSerialInput.value) {
                    deviceSerialInput.select();
                }
            }
        }

        window.addEventListener('DOMContentLoaded', async () => {
            // Immediate auto-focus as soon as app opens or reloads
            focusQrInput();
            setTimeout(focusQrInput, 50);
            setTimeout(focusQrInput, 300);

            // Initial state: START button disabled until validation succeeds with CONFIG SUCCESSFUL
            btnStartInspection.disabled = true;
            btnStartInspection.classList.remove('ready-pulse');
            setValidationState('idle', 'Scan to Validate');
            pmsPayloadsCache = null;

            // QR scanner enters text into text box and fires Enter to validate
            deviceSerialInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    validateScannedDevice();
                }
            });

            // If input is changed or cleared after validation, disable START button immediately
            let inputDebounceTimer = null;
            deviceSerialInput.addEventListener('input', () => {
                const val = deviceSerialInput.value.trim();
                if (val !== currentValidatedCode) {
                    btnStartInspection.disabled = true;
                    btnStartInspection.classList.remove('ready-pulse');
                    pmsPayloadsCache = null; // Keep JSON fields empty until server confirms
                    if (!val) {
                        setValidationState('idle', 'Scan to Validate');
                        document.getElementById('footerStatus').innerText = "Scan QR Code or enter Device Serial No. to validate with server and activate START.";
                    } else {
                        setValidationState('idle', 'Press Enter to Validate');
                        document.getElementById('footerStatus').innerText = "Device ID entered. Press Enter or scan to send payloads and validate with PMS server.";
                    }
                }

                // Auto-trigger validation if a completed QR string is scanned / pasted
                clearTimeout(inputDebounceTimer);
                if (val && (val.includes(';') || val.includes('|')) && (val.toLowerCase().includes('id:') || val.toLowerCase().includes('sr:'))) {
                    inputDebounceTimer = setTimeout(() => {
                        if (val !== currentValidatedCode) {
                            validateScannedDevice();
                        }
                    }, 350);
                }
            });

            await initCameraDevices();

            // Re-focus after camera stream initialization completes
            focusQrInput();
            setTimeout(focusQrInput, 500);

            // Keyboard shortcuts: Spacebar triggers inspection; Esc dismisses active toast
            window.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') {
                    const activeToast = document.querySelector('.config-toast.show');
                    if (activeToast) {
                        dismissToast(activeToast);
                    }
                }
                if (e.code === 'Space' && e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
                    e.preventDefault();
                    if (!btnStartInspection.disabled) {
                        triggerStartInspection();
                    } else {
                        document.getElementById('footerStatus').innerText = "⚠️ START is disabled: QR must be scanned and validated by server (CONFIG SUCCESSFUL) first.";
                    }
                }
            });
        });

        // Also ensure textbox is focused on window load and window focus/switch
        window.addEventListener('load', () => {
            focusQrInput();
            setTimeout(focusQrInput, 200);
        });

        window.addEventListener('focus', () => {
            focusQrInput();
        });

        // Auto re-focus textbox when clicking outside interactive controls
        document.addEventListener('click', (e) => {
            const tag = e.target.tagName;
            if (tag !== 'BUTTON' && tag !== 'SELECT' && tag !== 'INPUT' && tag !== 'TEXTAREA' && !e.target.closest('#pmsJsonModal') && !e.target.closest('#configToastContainer') && !e.target.closest('.modal-content')) {
                focusQrInput();
            }
        });

        function clearQrInput() {
            deviceSerialInput.value = '';
            currentValidatedCode = null;
            pmsPayloadsCache = null;
            btnStartInspection.disabled = true;
            btnStartInspection.classList.remove('ready-pulse');
            setValidationState('idle', 'Scan to Validate');
            document.getElementById('footerStatus').innerText = "Ready. Scan QR Code (Id: ..; Sr: ..;) to validate and activate START.";
            focusQrInput();
        }

        async function initCameraDevices() {
            try {
                const tempStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
                tempStream.getTracks().forEach(t => t.stop());

                const allDevices = await navigator.mediaDevices.enumerateDevices();
                devicesList = allDevices.filter(d => d.kind === 'videoinput');

                selectCamTop.innerHTML = '';
                selectCamOrig.innerHTML = '';

                const savedTopId = localStorage.getItem('selected_top_cam');
                const savedOrigId = localStorage.getItem('selected_orig_cam');

                let topIdx = 0;
                let origIdx = devicesList.length > 1 ? 1 : 0;

                devicesList.forEach((dev, idx) => {
                    const baseLabel = dev.label || `Camera ${idx + 1}`;
                    const label = devicesList.filter(d => (d.label || '') === dev.label).length > 1 
                        ? `${baseLabel} (#${idx + 1})` 
                        : baseLabel;
                    const lower = label.toLowerCase();

                    selectCamTop.add(new Option(label, dev.deviceId));
                    selectCamOrig.add(new Option(label, dev.deviceId));

                    if (savedTopId && dev.deviceId === savedTopId) {
                        topIdx = idx;
                    } else if (!savedTopId && (lower.includes('top') || lower.includes('arducam_top'))) {
                        topIdx = idx;
                    }

                    if (savedOrigId && dev.deviceId === savedOrigId) {
                        origIdx = idx;
                    } else if (!savedOrigId && (lower.includes('origin') || lower.includes('arducam_origin') || lower.includes('grommet'))) {
                        origIdx = idx;
                    }
                });

                if (devicesList.length > 0) {
                    selectCamTop.selectedIndex = topIdx;
                    selectCamOrig.selectedIndex = origIdx;
                    await startDualStreams();
                } else {
                    document.getElementById('footerStatus').innerText = "No cameras detected. Use Upload button to test images.";
                }
            } catch (err) {
                console.warn("Camera init error:", err);
                document.getElementById('footerStatus').innerText = "Camera access unavailable. Using upload mode.";
            }
        }

        async function startDualStreams() {
            stopAllStreams();

            const topDeviceId = selectCamTop.value;
            const origDeviceId = selectCamOrig.value;

            if (topDeviceId) localStorage.setItem('selected_top_cam', topDeviceId);
            if (origDeviceId) localStorage.setItem('selected_orig_cam', origDeviceId);

            if (!uploadedTopBase64) {
                try {
                    const constraintsTop = topDeviceId ? { video: { deviceId: { exact: topDeviceId }, width: 1280, height: 720 } } : { video: { width: 1280, height: 720 } };
                    streamTop = await navigator.mediaDevices.getUserMedia(constraintsTop);
                    videoTop.srcObject = streamTop;
                    videoTop.style.display = 'block';
                    imgUploadTop.style.display = 'none';
                    await videoTop.play();
                    document.getElementById('dotTop').classList.add('active');
                    renderTopGuides();
                } catch (e) {
                    console.warn("Top stream error:", e);
                    document.getElementById('dotTop').classList.remove('active');
                }
            }

            if (!uploadedOrigBase64) {
                try {
                    const constraintsOrig = origDeviceId ? { video: { deviceId: { exact: origDeviceId }, width: 1280, height: 720 } } : { video: { width: 1280, height: 720 } };
                    streamOrig3 = await navigator.mediaDevices.getUserMedia(constraintsOrig);
                    videoOrig3.srcObject = streamOrig3;
                    videoOrig3.style.display = 'block';
                    imgUploadOrig.style.display = 'none';
                    await videoOrig3.play();
                    document.getElementById('dotOrig').classList.add('active');
                    renderOrig3Guides();
                } catch (e) {
                    console.warn("Origin stream error:", e);
                    document.getElementById('dotOrig').classList.remove('active');
                }
            }

            setViewMode(currentViewMode || 'live_top');
        }

        function stopAllStreams() {
            if (streamTop) {
                streamTop.getTracks().forEach(t => t.stop());
                streamTop = null;
            }
            if (streamOrig3) {
                streamOrig3.getTracks().forEach(t => t.stop());
                streamOrig3 = null;
            }
            if (animFrameTop) cancelAnimationFrame(animFrameTop);
            if (animFrameOrig3) cancelAnimationFrame(animFrameOrig3);
        }

        function restartLiveCameras() {
            startDualStreams();
        }

        function onCameraSelectionChanged() {
            startDualStreams();
        }

        function swapCameras() {
            const temp = selectCamTop.selectedIndex;
            selectCamTop.selectedIndex = selectCamOrig.selectedIndex;
            selectCamOrig.selectedIndex = temp;
            startDualStreams();
        }

        function resetToLiveCameras() {
            uploadedTopBase64 = null;
            uploadedOrigBase64 = null;
            document.getElementById('labelTop').innerText = "Top View (Arducam_TOP)";
            document.getElementById('labelOrig').innerText = "Origin View (Arducam_ORIGIN - Origin 3)";
            setViewMode('live_top');
            startDualStreams();
            document.getElementById('footerStatus').innerText = "Restored Live Cameras.";
        }

        function renderTopGuides() {
            if (uploadedTopBase64) return;
            if (!streamTop || !videoTop.videoWidth) {
                animFrameTop = requestAnimationFrame(renderTopGuides);
                return;
            }
            overlayTop.width = videoTop.clientWidth;
            overlayTop.height = videoTop.clientHeight;
            const ctx = overlayTop.getContext('2d');
            ctx.clearRect(0, 0, overlayTop.width, overlayTop.height);

            const sx = overlayTop.width / 1024;
            const sy = overlayTop.height / 576;

            drawGuideBox(ctx, 250*sx, 10*sy, 780*sx, 570*sy, '#38bdf8', 'PCB Alignment');
            drawGuideBox(ctx, 370*sx, 410*sy, 470*sx, 565*sy, '#a78bfa', 'Origin 1');
            drawGuideBox(ctx, 470*sx, 15*sy, 690*sx, 100*sy, '#a78bfa', 'Origin 2');
            drawGuideBox(ctx, 540*sx, 415*sy, 660*sx, 565*sy, '#a78bfa', 'Origin 3');

            animFrameTop = requestAnimationFrame(renderTopGuides);
        }

        function renderOrig3Guides() {
            if (uploadedOrigBase64) return;
            if (!streamOrig3 || !videoOrig3.videoWidth) {
                animFrameOrig3 = requestAnimationFrame(renderOrig3Guides);
                return;
            }
            overlayOrig3.width = videoOrig3.clientWidth;
            overlayOrig3.height = videoOrig3.clientHeight;
            const ctx = overlayOrig3.getContext('2d');
            ctx.clearRect(0, 0, overlayOrig3.width, overlayOrig3.height);

            const sx = overlayOrig3.width / 1024;
            const sy = overlayOrig3.height / 576;

            drawGuideBox(ctx, 80*sx, 260*sy, 280*sx, 490*sy, '#38bdf8', 'Origin 3 Target');

            animFrameOrig3 = requestAnimationFrame(renderOrig3Guides);
        }

        function drawGuideBox(ctx, sx1, sy1, sx2, sy2, color, text) {
            ctx.strokeStyle = color;
            ctx.lineWidth = 1.5;
            ctx.setLineDash([3, 3]);
            ctx.strokeRect(sx1, sy1, sx2 - sx1, sy2 - sy1);
            ctx.setLineDash([]);
            if (text) {
                ctx.font = '11px -apple-system, sans-serif';
                ctx.fillStyle = color;
                ctx.fillText(text, sx1 + 3, sy1 - 5);
            }
        }

        function grabFrameFromVideo(videoEl) {
            if (!videoEl || !videoEl.videoWidth) return null;
            const canvas = document.createElement('canvas');
            canvas.width = 1024;
            canvas.height = 576;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(videoEl, 0, 0, 1024, 576);
            return canvas.toDataURL('image/jpeg', 0.95);
        }

        async function triggerStartInspection() {
            if (btnStartInspection.disabled) {
                return;
            }
            btnStartInspection.disabled = true;
            btnStartInspection.classList.remove('ready-pulse');
            document.getElementById('footerStatus').innerText = "Inspecting both cameras and logging to Excel...";

            if (uploadedTopBase64) {
                rawTopBase64 = uploadedTopBase64;
            } else if (streamTop && videoTop.videoWidth) {
                rawTopBase64 = grabFrameFromVideo(videoTop);
            }

            if (uploadedOrigBase64) {
                rawOrig3Base64 = uploadedOrigBase64;
            } else if (streamOrig3 && videoOrig3.videoWidth) {
                rawOrig3Base64 = grabFrameFromVideo(videoOrig3);
            }

            if (!rawTopBase64 || !rawOrig3Base64) {
                alert("Please ensure both Top View and Origin View images are available via live cameras or upload.");
                btnStartInspection.disabled = false;
                return;
            }

            const currentContainer = currentViewMode === 'live_orig3' ? containerOrig : containerTop;
            currentContainer.classList.add('flash-anim');
            setTimeout(() => currentContainer.classList.remove('flash-anim'), 300);

            const scannedDeviceId = deviceSerialInput.value.trim() || `PCB-${new Date().toISOString().replace(/[-:T.]/g, '').slice(0, 14)}`;

            try {
                const res = await fetch('/api/inspect', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        device_id: scannedDeviceId,
                        top_image: rawTopBase64,
                        orig3_image: rawOrig3Base64,
                        orig2_image: rawOrig3Base64
                    })
                });
                const data = await res.json();
                applyResults(data, scannedDeviceId);
            } catch (err) {
                console.error(err);
                document.getElementById('footerStatus').innerText = "Inspection request failed.";
            } finally {
                btnStartInspection.disabled = true;
                btnStartInspection.classList.remove('ready-pulse');
                currentValidatedCode = null;
                setValidationState('idle', 'Scan Next QR');
                focusQrInput();
            }
        }

        
        
        function applyResults(data, deviceId) {
            resTopWiresAnnotated = data.top_wires_annotated;
            resTopOriginsAnnotated = data.top_origins_annotated;
            resOrig3Annotated = data.orig3_annotated || data.orig2_annotated;

            const r = data.results || {};

            // Final verdict comes from the backend after PMS validation.
            const finalVerdict = data.verdict || "SERVER UNREACHABLE";
            const pmsStatus = data.pms_report_status || "UNREACHABLE";
            const pmsResponse = data.pms_mqtt_response || {};

            setPill(
                'pillOrig3Grommet',
                r.orig3_grommet_pass ?? r.orig2_grommet_pass
            );
            setPill('pillObl', r.obl_pass);
            setPill('pillOum', r.oum_pass);
            setPill('pillObr', r.obr_pass);
            setPill('pillC1', r.c1_pass);
            setPill('pillC2', r.c2_pass);
            setPill('pillC3', r.c3_pass);

            const banner = document.getElementById('verdictBanner');
            const verdictText = document.getElementById('verdictText');
            const verdictDevice = document.getElementById('verdictDevice');
            const verdictDesc = document.getElementById('verdictDesc');

            const displayId = data.serial_no
                ? (
                    data.apo_id
                        ? `${data.serial_no} (APO: ${data.apo_id})`
                        : data.serial_no
                )
                : deviceId;

            verdictDevice.innerText = `Device: ${displayId}`;

            // Display the final outcome, not data.combined_pass.
            if (finalVerdict === "SERVER UNREACHABLE") {
                banner.className = "verdict-box fail";
                verdictText.innerText = "SERVER UNREACHABLE";

                verdictDesc.innerText =
                    pmsResponse.message ||
                    "No matching response received from PMS. Please check the server and MQTT connection.";

            } else if (pmsStatus === "REJECTED") {
                banner.className = "verdict-box fail";
                verdictText.innerText = "FAIL";

                const reason =
                    data.pms_rejection_reason ||
                    pmsResponse.reason ||
                    pmsResponse.request_status ||
                    "PMS rejected the ReportStore request.";

                verdictDesc.innerText = `PMS rejected ReportStore: ${reason}`;

            } else if (pmsStatus === "ACCEPTED" && finalVerdict === "PASS") {
                banner.className = "verdict-box pass";
                verdictText.innerText = "PASS";
                verdictDesc.innerText =
                    "AI inspection passed and PMS accepted ReportStore.";

            } else if (pmsStatus === "ACCEPTED" && finalVerdict === "FAIL") {
                banner.className = "verdict-box fail";
                verdictText.innerText = "FAIL";
                verdictDesc.innerText =
                    "AI inspection failed. PMS accepted ReportStore.";

            } else {
                // Fail safely if the backend did not provide a recognized
                // final verdict and PMS validation status.
                banner.className = "verdict-box fail";
                verdictText.innerText = "SERVER UNREACHABLE";
                verdictDesc.innerText =
                    "PMS validation status is missing or invalid. Check the backend logs.";
            }

            if (data.notes) {
                document.getElementById('diagLog').innerText = data.notes;
            }

            // Cache the ReportStore payload generated for this run.
            if (data.pms_report_json) {
                if (!pmsPayloadsCache) {
                    pmsPayloadsCache = {};
                }

                pmsPayloadsCache.ReportStore = data.pms_report_json;
            }

            document.getElementById('footerStatus').innerText =
                `Inspection finished (${verdictText.innerText}). ` +
                `Device [${deviceId}]. PMS status: ${pmsStatus}.`;

            setViewMode('res_top_wires');
        }


        async function openExcelSheet() {
            try {
                const res = await fetch('/api/open_excel', { method: 'POST' });
                const data = await res.json();
                if (data.status === 'success') {
                    document.getElementById('footerStatus').innerText = "Opened Result/Inspection_Log.xlsx.";
                    window.location.href = '/api/download_excel';
                } else {
                    alert(data.message || "Could not open Excel sheet.");
                }
            } catch (e) {
                window.location.href = '/api/download_excel';
            }
        }

        function setPill(id, isPass) {
            const el = document.getElementById(id);
            if (!el) return;
            if (isPass) {
                el.innerText = "PASS";
                el.className = "status-pill pass";
            } else {
                el.innerText = "FAIL";
                el.className = "status-pill fail";
            }
        }

        function setViewMode(mode) {
            currentViewMode = mode;
            document.querySelectorAll('.nav-pill').forEach(btn => btn.classList.remove('active'));

            if (mode === 'live_top') {
                document.getElementById('pillLiveTop').classList.add('active');
                containerTop.style.display = 'flex';
                containerOrig.style.display = 'none';
                singleViewArea.style.display = 'none';
            } else if (mode === 'live_orig3' || mode === 'live_orig2') {
                document.getElementById('pillLiveOrig').classList.add('active');
                containerTop.style.display = 'none';
                containerOrig.style.display = 'flex';
                singleViewArea.style.display = 'none';
            } else {
                containerTop.style.display = 'none';
                containerOrig.style.display = 'none';
                singleViewArea.style.display = 'flex';

                if (mode === 'res_top_wires') {
                    document.getElementById('pillTopWires').classList.add('active');
                    document.getElementById('resultViewLabel').innerText = "Result: Top View Wire Routing Paths";
                    singleResultImg.src = resTopWiresAnnotated || rawTopBase64 || '';
                } else if (mode === 'res_top_origins') {
                    document.getElementById('pillTopOrigins').classList.add('active');
                    document.getElementById('resultViewLabel').innerText = "Result: Top View Wire Origins";
                    singleResultImg.src = resTopOriginsAnnotated || rawTopBase64 || '';
                } else if (mode === 'res_orig3' || mode === 'res_orig2') {
                    document.getElementById('pillOrig3').classList.add('active');
                    document.getElementById('resultViewLabel').innerText = "Result: Origin 3 Dedicated Grommet";
                    singleResultImg.src = resOrig3Annotated || rawOrig3Base64 || '';
                }
            }
        }

        function replaceImageForCurrentTab() {
            if (currentViewMode === 'res_orig3' || currentViewMode === 'res_orig2') {
                document.getElementById('fileOrig3Input').click();
            } else {
                document.getElementById('fileTopInput').click();
            }
        }

        function handleBoxClick(target) {
            if (target === 'top') {
                document.getElementById('fileTopInput').click();
            } else {
                document.getElementById('fileOrig3Input').click();
            }
        }

        function handleDragOver(e) {
            e.preventDefault();
            e.currentTarget.classList.add('drag-over');
        }

        function handleDragLeave(e) {
            e.preventDefault();
            e.currentTarget.classList.remove('drag-over');
        }

        function handleDrop(e, target) {
            e.preventDefault();
            e.currentTarget.classList.remove('drag-over');
            const files = e.dataTransfer.files;
            if (!files || files.length === 0) return;

            if (files.length >= 2) {
                loadFile(files[0], 'top');
                loadFile(files[1], 'orig3');
            } else {
                loadFile(files[0], target);
            }
        }

        function handleBatchUpload(e) {
            const files = e.target.files;
            if (!files || files.length === 0) return;

            if (files.length === 1) {
                loadFile(files[0], (currentViewMode === 'live_orig3' || currentViewMode === 'live_orig2') ? 'orig3' : 'top');
            } else {
                let topFile = files[0];
                let origFile = files[1];
                const n0 = files[0].name.toLowerCase();
                if (n0.includes('orig') || n0.includes('grommet') || n0.includes('front')) {
                    origFile = files[0];
                    topFile = files[1];
                }
                loadFile(topFile, 'top');
                loadFile(origFile, 'orig3');
            }
        }

        function handleManualUpload(e, target) {
            const file = e.target.files[0];
            if (!file) return;
            loadFile(file, target);
        }

        function loadFile(file, target) {
            const reader = new FileReader();
            reader.onload = function(evt) {
                const data = evt.target.result;
                if (target === 'top') {
                    uploadedTopBase64 = data;
                    rawTopBase64 = data;
                    videoTop.style.display = 'none';
                    imgUploadTop.src = data;
                    imgUploadTop.style.display = 'block';
                    document.getElementById('labelTop').innerText = `Top: ${file.name.slice(0, 14)}`;
                    document.getElementById('dotTop').classList.add('active');
                } else {
                    uploadedOrigBase64 = data;
                    rawOrig3Base64 = data;
                    videoOrig3.style.display = 'none';
                    imgUploadOrig.src = data;
                    imgUploadOrig.style.display = 'block';
                    document.getElementById('labelOrig').innerText = `Origin 3: ${file.name.slice(0, 14)}`;
                    document.getElementById('dotOrig').classList.add('active');
                }

                if (currentViewMode !== 'live_top' && currentViewMode !== 'live_orig3') {
                    setViewMode(currentViewMode);
                }
                document.getElementById('footerStatus').innerText = `Loaded ${file.name}. Ready to inspect.`;
            };
            reader.readAsDataURL(file);
        }

        // PMS JSON Modal Logic
        let pmsPayloadsCache = null;
        let activePmsTab = 'report';

        async function openPmsJsonModal() {
            const modal = document.getElementById('pmsJsonModal');
            if (modal) modal.style.display = 'flex';
            const rawVal = document.getElementById('deviceSerialInput') ? document.getElementById('deviceSerialInput').value.trim() : '';

            try {
                if (!pmsPayloadsCache || pmsPayloadsCache._forDevice !== rawVal) {
                    const res = await fetch(`/api/pms/payloads?device_id=${encodeURIComponent(rawVal)}`);
                    const data = await res.json();
                    const existingReport = pmsPayloadsCache ? pmsPayloadsCache.ReportStore : null;
                    if (data && data.payloads) {
                        pmsPayloadsCache = data.payloads;
                        pmsPayloadsCache.server_responses = data.server_responses || {};
                        pmsPayloadsCache._forDevice = rawVal;
                        // If we have an actual completed inspection report cached (not empty), retain it
                        if (existingReport && existingReport.ColumnsName && existingReport.ColumnsName[0] && existingReport.ColumnsName[0].TaktTime !== "") {
                            pmsPayloadsCache.ReportStore = existingReport;
                        }
                    }
                }
            } catch (err) {
                console.error("Failed to load PMS JSON:", err);
                const pre = document.getElementById('pmsJsonPre');
                if (pre) pre.innerText = "Failed to load PMS JSON: " + err.message;
            }
            renderPmsModalJson();
        }

        function closePmsJsonModal(e) {
            if (!e || e.target.id === 'pmsJsonModal' || (e.target.classList && (e.target.classList.contains('modal-close') || e.target.classList.contains('btn-modal-close')))) {
                const modal = document.getElementById('pmsJsonModal');
                if (modal) modal.style.display = 'none';
            }
        }

        function switchModalTab(tab) {
            activePmsTab = tab;
            document.querySelectorAll('.modal-tab').forEach(b => b.classList.remove('active'));
            if (tab === 'report') document.getElementById('tabReport')?.classList.add('active');
            if (tab === 'whitelist') document.getElementById('tabWhitelist')?.classList.add('active');
            if (tab === 'serial') document.getElementById('tabSerial')?.classList.add('active');
            if (tab === 'status') document.getElementById('tabStatus')?.classList.add('active');
            if (tab === 'responses') document.getElementById('tabResponses')?.classList.add('active');
            renderPmsModalJson();
        }

        function renderPmsModalJson() {
            const pre = document.getElementById('pmsJsonPre');
            if (!pre) return;
            if (!pmsPayloadsCache) {
                pre.innerText = "Loading PMS JSON payloads...";
                return;
            }
            let jsonTarget = pmsPayloadsCache.ReportStore;
            if (activePmsTab === 'whitelist') jsonTarget = pmsPayloadsCache.DeviceAutoWhitelisting;
            if (activePmsTab === 'serial') jsonTarget = pmsPayloadsCache.SerialNoValidation;
            if (activePmsTab === 'status') jsonTarget = pmsPayloadsCache.StatusValidation;
            if (activePmsTab === 'responses') jsonTarget = pmsPayloadsCache.server_responses || {};
            pre.innerText = JSON.stringify(jsonTarget || {}, null, 2);
        }

        function copyPmsJson() {
            const txt = document.getElementById('pmsJsonPre').innerText;
            navigator.clipboard.writeText(txt).then(() => {
                const btn = document.querySelector('.btn-copy-json');
                const orig = btn.innerText;
                btn.innerText = '✔ Copied!';
                setTimeout(() => btn.innerText = orig, 1500);
            });
        }

        // Slide In/Out Config Toast Popup for Success or Failure
        function showConfigResultPopup(isSuccess, info) {
            const container = document.getElementById('configToastContainer');
            if (!container) return;

            // Remove previous toasts to keep display clean and focused
            container.innerHTML = '';

            const toast = document.createElement('div');
            toast.className = `config-toast ${isSuccess ? 'success' : 'failed'}`;

            const duration = isSuccess ? 3200 : 4200; // 3.2s on success, 4.2s on error

            const title = info.title || (isSuccess ? 'PMS Configuration Successful' : 'PMS Configuration Failed');
            const badgeText = isSuccess ? 'CONFIG SUCCESSFUL' : 'CONFIG FAILED';
            const bodyMsg = isSuccess
                ? (info.message || 'All 3 validation payloads confirmed. START button ACTIVATED.')
                : (info.error ? `Reason: ${info.error}` : (info.message || 'Server rejected configuration.'));

            const serialText = info.serial_no ? `<span>Serial: <strong>${escapeHtml(info.serial_no)}</strong></span>` : '';
            const apoText = info.apo_id ? `<span>APO: <strong>${escapeHtml(info.apo_id)}</strong></span>` : '';
            const metaHtml = (serialText || apoText) ? `<div class="toast-meta">${serialText}${apoText}</div>` : '';

            toast.innerHTML = `
                <div class="toast-content">
                    <div class="toast-icon ${isSuccess ? 'success' : 'failed'}">
                        ${isSuccess ? '✔' : '✖'}
                    </div>
                    <div class="toast-text">
                        <div class="toast-header-row">
                            <span class="toast-title">${escapeHtml(title)}</span>
                            <span class="toast-badge ${isSuccess ? 'success' : 'failed'}">${badgeText}</span>
                            <button class="toast-close-btn" onclick="dismissToast(this.closest('.config-toast'))" title="Dismiss">&times;</button>
                        </div>
                        <div class="toast-body">${escapeHtml(bodyMsg)}</div>
                        ${metaHtml}
                    </div>
                </div>
                <div class="toast-progress">
                    <div class="toast-progress-bar ${isSuccess ? 'success' : 'failed'}" style="animation: toastProgressCountdown ${duration / 1000}s linear forwards;"></div>
                </div>
            `;

            container.appendChild(toast);

            // Slide in smoothly
            requestAnimationFrame(() => {
                toast.classList.add('show');
            });

            // Automatically slide out and remove after short amount of time
            const hideTimer = setTimeout(() => {
                dismissToast(toast);
            }, duration);
            toast._hideTimer = hideTimer;

            // Click to dismiss early if desired
            toast.addEventListener('click', (e) => {
                if (e.target.tagName !== 'BUTTON') {
                    dismissToast(toast);
                }
            });

            // Textbox always remains active and focused
            focusQrInput();
        }

        function dismissToast(toast) {
            if (!toast || toast.classList.contains('hide')) return;
            clearTimeout(toast._hideTimer);
            toast.classList.remove('show');
            toast.classList.add('hide');
            setTimeout(() => {
                if (toast && toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 360);
            focusQrInput();
        }

        function escapeHtml(str) {
            return String(str || '').replace(/[&<>"']/g, (m) => ({
                '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
            }[m]));
        }

        // MQTT connection status indicator
        async function updateMqttStatus() {
            const indicator = document.getElementById('mqttStatus');
            const statusText = document.getElementById('mqttStatusText');

            if (!indicator || !statusText) return;

            try {
                const response = await fetch('/api/pms/status', {
                    cache: 'no-store'
                });

                if (!response.ok) {
                    throw new Error('Status request failed');
                }

                const data = await response.json();

                if (data.connected === true && data.subscribed === true) {
                    indicator.classList.remove('disconnected');
                    indicator.classList.add('connected');
                    statusText.textContent = 'SERVER  Connected';
                } else {
                    indicator.classList.remove('connected');
                    indicator.classList.add('disconnected');
                    statusText.textContent = 'SERVER  Disconnected';
                }
            } catch (error) {
                indicator.classList.remove('connected');
                indicator.classList.add('disconnected');
                statusText.textContent = 'SERVER  Disconnected';
            }
        }

        // Check immediately, then refresh every 2 seconds
        updateMqttStatus();
        setInterval(updateMqttStatus, 2000);
    </script>

    <!-- PMS JSON Modal -->
    <div id="pmsJsonModal" class="modal-backdrop" style="display:none;" onclick="closePmsJsonModal(event)">
        <div class="modal-box" onclick="event.stopPropagation()">
            <div class="modal-header">
                <h3>📡 Selec Controls - PMS JSON Output</h3>
                <button class="modal-close" onclick="closePmsJsonModal()">&times;</button>
            </div>
            <div class="modal-tabs">
                <button class="modal-tab active" id="tabReport" onclick="switchModalTab('report')">4. ReportStore (Test Result)</button>
                <button class="modal-tab" id="tabWhitelist" onclick="switchModalTab('whitelist')">1. Whitelisting</button>
                <button class="modal-tab" id="tabSerial" onclick="switchModalTab('serial')">2. Serial Validation</button>
                <button class="modal-tab" id="tabStatus" onclick="switchModalTab('status')">3. Status Validation</button>
                <button class="modal-tab" id="tabResponses" onclick="switchModalTab('responses')">5. Server Responses</button>
            </div>
            <pre id="pmsJsonPre" class="modal-pre">Loading JSON...</pre>
            <div class="modal-footer">
                <button class="btn-copy-json" onclick="copyPmsJson()">📋 Copy JSON</button>
                <button class="btn-modal-close" onclick="closePmsJsonModal()">Close</button>
            </div>
        </div>
    </div>

    <!-- Slide In/Out Config Toast Container -->
    <div id="configToastContainer"></div>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML_PAGE)

@app.route("/api/pms/status", methods=["GET"])
def pms_status_endpoint():
    return jsonify(pms_mqtt.get_connection_status())

@app.route("/api/open_excel", methods=["POST"])
def open_excel_endpoint():
    try:
        if os.path.exists(EXCEL_PATH):
            os.startfile(EXCEL_PATH)
            return jsonify({"status": "success", "message": "Excel file opened."})
        elif os.path.exists(CSV_PATH):
            os.startfile(CSV_PATH)
            return jsonify({"status": "success", "message": "CSV log opened."})
        else:
            return jsonify({"status": "error", "message": "No inspection log generated yet. Run an inspection first."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route("/api/download_excel")
def download_excel_endpoint():
    if os.path.exists(EXCEL_PATH):
        return send_file(EXCEL_PATH, as_attachment=True, download_name="Inspection_Log.xlsx")
    elif os.path.exists(CSV_PATH):
        return send_file(CSV_PATH, as_attachment=True, download_name="Inspection_Log.csv")
    return "No inspection log generated yet", 404

# Authorization cache for scanned devices validated via PMS MQTT
validated_device_cache = {
    "serial_no": None,
    "apo_id": None,
    "timestamp": 0.0,
    "raw_input": None,
    "payloads": None
}

@app.route("/api/pms/validate", methods=["POST"])
def pms_validate_endpoint():
    """
    Validates a scanned device against PMS MQTT server before activating the START button:
    1. Extracts APoNumberId and DeviceSerialNo from scanned QR text (e.g. 'Id: ..; Sr: ..;').
    2. Sends DeviceAutoWhitelisting, SerialNoValidation, and StatusValidation sequentially.
    3. Confirms that the server responds with CmdType='ResponseFromServer', matching UtcRequest_ID,
       and RequestStatus='CONFIG SUCCESSFUL'.
    4. Caches the authorization and validated payloads so that the START button is activated
       and JSON payloads are populated.
    """
    global validated_device_cache
    data = request.get_json() or {}
    device_id = str(data.get("device_id") or "").strip()

    if not device_id:
        return jsonify({
            "status": "error",
            "validated": False,
            "message": "No serial number or QR code provided. Please scan a QR code first.",
            "payloads": build_empty_payloads(),
            "server_responses": {}
        }), 400

    apo_id, serial_no = parse_sticker(device_id)

    try:
        print("\n" + "=" * 60)
        print(f"[PMS VALIDATION GATE] Validating scanned device: Serial={serial_no}, APO={apo_id}...")
        print("=" * 60)

        res = pms_mqtt.run_startup_validation(
            device_serial_no=serial_no,
            apo_number_id=apo_id
        )

        validated_payloads = res.get("payloads") or {}
        server_responses = res.get("server_responses") or {}

        validated_device_cache = {
            "serial_no": serial_no,
            "apo_id": apo_id,
            "timestamp": time.time(),
            "raw_input": device_id,
            "payloads": validated_payloads,
            "server_responses": server_responses
        }

        print(f"[PMS VALIDATION GATE] All 3 validations confirmed CONFIG SUCCESSFUL for {serial_no}. START button enabled.\n")

        return jsonify({
            "status": "success",
            "validated": True,
            "serial_no": serial_no,
            "apo_id": apo_id,
            "raw_qr": device_id,
            "payloads": validated_payloads,
            "server_responses": server_responses,
            "message": f"Server responded CONFIG SUCCESSFUL for Whitelisting, SerialNo, and StatusValidation. START button activated."
        })

    except Exception as exc:
        print(f"[PMS VALIDATION GATE] Validation failed for {serial_no}: {exc}\n")
        validated_device_cache = {
            "serial_no": None,
            "apo_id": None,
            "timestamp": 0.0,
            "raw_input": None,
            "payloads": None,
            "server_responses": None
        }
        return jsonify({
            "status": "error",
            "validated": False,
            "serial_no": serial_no,
            "apo_id": apo_id,
            "raw_qr": device_id,
            "message": str(exc),
            "payloads": build_empty_payloads(),
            "server_responses": {}
        }), 503

@app.route("/api/inspect", methods=["POST"])
def inspect_endpoint():
    global validated_device_cache
    t_start = time.time()
    data = request.get_json() or {}
    device_id = data.get("device_id") or "N/A"

    apo_id, serial_no = parse_sticker(device_id)

    # Pre-Inspection Validation Gate:
    # START inspection must ONLY proceed if DeviceAutoWhitelisting, SerialNoValidation,
    # and StatusValidation were sent and server responded CONFIG SUCCESSFUL matching UtcRequest_ID.
    now_t = time.time()
    is_prevalidated = (
        validated_device_cache.get("serial_no") == serial_no
        and validated_device_cache.get("payloads") is not None
        and (now_t - validated_device_cache.get("timestamp", 0.0)) < 600.0
    )

    if not is_prevalidated:
        print(f"[PMS GATE] Blocked unvalidated inspection attempt for Serial={serial_no}.")
        return jsonify({
            "status": "error",
            "stage": "pms_validation",
            "message": "Device not validated. Payloads must be sent and server must respond CONFIG SUCCESSFUL with matching UtcRequest_ID before START is allowed.",
            "inspection_started": False
        }), 403

    # Reset cache after starting inspection so each board requires a fresh scan and validation
    validated_device_cache = {
        "serial_no": None,
        "apo_id": None,
        "timestamp": 0.0,
        "raw_input": None,
        "payloads": None
    }

    top_img_data = data.get("top_image")
    orig3_img_data = data.get("orig3_image") or data.get("orig2_image")

    response_payload = {}
    top_res = {}
    orig3_res = {}

    top_img_bgr = None
    orig3_img_bgr = None

    if top_img_data:
        top_img_bgr = decode_image(top_img_data)
        if top_img_bgr is not None:
            top_res = process_top_inspection(top_img_bgr)
            response_payload["top_wires_annotated"] = top_res["top_wires_annotated"]
            response_payload["top_origins_annotated"] = top_res["top_origins_annotated"]

    if orig3_img_data:
        orig3_img_bgr = decode_image(orig3_img_data)
        if orig3_img_bgr is not None:
            orig3_res = process_orig3_inspection(orig3_img_bgr)
            response_payload["orig3_annotated"] = orig3_res["orig3_annotated"]
            response_payload["orig2_annotated"] = orig3_res["orig3_annotated"]

    # Decision Engine: Combine results from both cameras
    obl_pass = top_res.get("obl_pass", False)
    oum_pass = top_res.get("oum_pass", False)
    raw_obr_pass = top_res.get("obr_pass", False)
    c1_pass = top_res.get("c1_pass", False)
    c2_pass = top_res.get("c2_pass", False)
    c3_pass = top_res.get("c3_pass", False)
    orig3_grommet_pass = orig3_res.get("orig3_grommet_pass", False)

    # Effective Origin 3: Passes if dedicated Arducam_ORIGIN passes OR top view passes
    effective_origin3_pass = raw_obr_pass or orig3_grommet_pass

    wire_all_pass = c1_pass and c2_pass and c3_pass
    origins_all_pass = obl_pass and oum_pass and effective_origin3_pass
    combined_pass = wire_all_pass and origins_all_pass

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    timestamp_file = datetime.now().strftime("%Y%m%d_%H%M%S")

    notes_lines = []
    notes_lines.append(f"═════════════ INSPECTION LOG: {serial_no} ═════════════")
    notes_lines.append(f"🏷️  Device Serial: {serial_no} | APO Number ID: {apo_id}\n")

    # 1. Wire Paths
    notes_lines.append("🔌 WIRE ROUTING PATHS (Arducam_TOP):")
    notes_lines.append(f" • Case 1 (Bottom Left):  {'✔ PASS' if c1_pass else '✖ FAIL (Red is on Right)'}")
    notes_lines.append("   👉 Correct Rule: Red wire MUST be on LEFT of Black wire.\n")

    notes_lines.append(f" • Case 2 (Upper Middle): {'✔ PASS' if c2_pass else '✖ FAIL (Origin Failed)'}")
    notes_lines.append("   👉 Correct Rule: Red wire MUST originate at Middle Coil (wiring verified via origin).\n")

    notes_lines.append(f" • Case 3 (Bottom Right): {'✔ PASS' if c3_pass else '✖ FAIL (Red is on Right)'}")
    notes_lines.append("   👉 Correct Rule: Red wire MUST be on LEFT of Black wire.\n")

    # 2. Origins
    notes_lines.append("📍 WIRE ORIGIN CONNECTIONS:")
    notes_lines.append(f" • Origin 1 (Bottom Left):  {'✔ PASS' if obl_pass else '✖ FAIL'}")
    notes_lines.append("   👉 Correct Rule: Black wire enters Upper Socket, Red enters Lower Socket (Black above Red).\n")

    notes_lines.append(f" • Origin 2 (Top Middle):   {'✔ PASS' if oum_pass else '✖ FAIL'}")
    notes_lines.append("   👉 Correct Rule: Red wire connects to Middle Coil, Black wire to Rightmost Coil.\n")

    notes_lines.append(f" • Origin 3 (Bottom Right): {'✔ PASS' if effective_origin3_pass else '✖ FAIL'}" + 
                       (" [Verified via Arducam_ORIGIN Dedicated View]" if (orig3_grommet_pass and not raw_obr_pass) else ""))
    notes_lines.append("   👉 Correct Rule: Red wire origin MUST be ABOVE Black wire origin.\n")

    # 3. Dedicated Origin 3
    notes_lines.append("🎯 DEDICATED ORIGIN 3 GROMMET (Arducam_ORIGIN):")
    notes_lines.append(f" • Grommet Connection:    {'✔ PASS (Both Red & Black Wires Connected)' if orig3_grommet_pass else '✖ FAIL (Wire Missing at Grommet)'}")
    notes_lines.append("   👉 Correct Rule: Both Red and Black wires MUST be present and connected to the grommet.\n")

    # Save snapshot images to Result/Pass or Result/Fail
    target_folder = "Pass" if combined_pass else "Fail"
    result_dir = os.path.join(os.getcwd(), "Result", target_folder)
    os.makedirs(result_dir, exist_ok=True)

    # Save annotated inspection views
    clean_device_id = "".join(c for c in serial_no if c.isalnum() or c in ('-', '_')).strip() or "device"
    prefix = f"{timestamp_file}_{clean_device_id}"

    if "img_wires" in top_res and top_res["img_wires"] is not None:
        cv2.imwrite(os.path.join(result_dir, f"{prefix}_top_wires.jpg"), top_res["img_wires"])
        cv2.imwrite(os.path.join(result_dir, "latest_top_wires.jpg"), top_res["img_wires"])

    if "img_origins" in top_res and top_res["img_origins"] is not None:
        cv2.imwrite(os.path.join(result_dir, f"{prefix}_top_origins.jpg"), top_res["img_origins"])
        cv2.imwrite(os.path.join(result_dir, "latest_top_origins.jpg"), top_res["img_origins"])

    if "img_o3" in orig3_res and orig3_res["img_o3"] is not None:
        cv2.imwrite(os.path.join(result_dir, f"{prefix}_orig3_grommet.jpg"), orig3_res["img_o3"])
        cv2.imwrite(os.path.join(result_dir, "latest_orig3_grommet.jpg"), orig3_res["img_o3"])

    # Save raw captures for traceability
    if top_img_bgr is not None:
        cv2.imwrite(os.path.join(result_dir, f"{prefix}_raw_top.jpg"), top_img_bgr)
    if orig3_img_bgr is not None:
        cv2.imwrite(os.path.join(result_dir, f"{prefix}_raw_orig3.jpg"), orig3_img_bgr)

    # Collect concise failure summary for Excel
    fail_items = []
    if not obl_pass: fail_items.append("Origin 1 (BL)")
    if not oum_pass: fail_items.append("Origin 2 (UM Coil)")
    if not effective_origin3_pass: fail_items.append("Origin 3 (BR/Grommet)")
    if not c1_pass: fail_items.append("Wire Case 1 (BL)")
    if not c2_pass: fail_items.append("Wire Case 2 (UM)")
    if not c3_pass: fail_items.append("Wire Case 3 (BR)")
    notes_summary = "All checks passed" if combined_pass else f"Failed: {', '.join(fail_items)}"

    # 4. Log to Excel Sheet & CSV
    excel_record = {
        "timestamp": now_str,
        "device_id": serial_no,
        "combined_pass": combined_pass,
        "orig3_grommet_pass": orig3_grommet_pass,
        "obl_pass": obl_pass,
        "oum_pass": oum_pass,
        "obr_pass": effective_origin3_pass,
        "c1_pass": c1_pass,
        "c2_pass": c2_pass,
        "c3_pass": c3_pass,
        "notes_summary": notes_summary,
        "saved_folder": f"Result/{target_folder}"
    }
    log_to_excel(excel_record)

    # 5. Generate and Log Selec PMS Report JSON Output (PASS or FAIL)
    takt_time = time.time() - t_start
    verdict_label = "PASS" if combined_pass else "FAIL"
    try:
        req_id, pms_report_payload = build_report_store(
            device_serial_no=serial_no,
            apo_number_id=apo_id,
            takt_time=takt_time,
            wire_origin_pass=origins_all_pass,
            vi_test_pass=combined_pass
        )

        # 1. Save in Result/PMS_Payloads/ with explicit PASS/FAIL prefix
        pms_json_path = save_payload_to_file(pms_report_payload, f"{verdict_label}_report_{clean_device_id}")

        # 2. Also save directly in Result/Pass/ or Result/Fail/ alongside the snapshot images
        folder_json_path = os.path.join(result_dir, f"{prefix}_{verdict_label}_report.json")
        with open(folder_json_path, "w", encoding="utf-8") as f:
            json.dump(pms_report_payload, f, indent=4)

        # 3. Save latest_pms_report.json in Result/Pass/ or Result/Fail/
        latest_folder_json = os.path.join(result_dir, "latest_pms_report.json")
        with open(latest_folder_json, "w", encoding="utf-8") as f:
            json.dump(pms_report_payload, f, indent=4)

        # 4. Save latest_run.json in Result/PMS_Payloads/
        latest_overall_json = os.path.join(os.path.dirname(pms_json_path), "latest_run.json")
        with open(latest_overall_json, "w", encoding="utf-8") as f:
            json.dump(pms_report_payload, f, indent=4)

        # response_payload["pms_report_json"] = pms_report_payload
        # response_payload["pms_json_file"] = folder_json_path
        # response_payload["verdict"] = verdict_label

        # # Publish the actual inspection result to PMS.(Aryan)
        # try:
        #     pms_response = pms_mqtt.publish_report(
        #         pms_report_payload
        #     )
        #     response_payload["pms_mqtt_response"] = pms_response

        # except Exception as exc:
        #     print(f"[PMS] ReportStore publish error: {exc}")
        #     response_payload["pms_mqtt_response"] = {
        #         "received": False,
        #         "message": str(exc)
        #     }

        
        response_payload["pms_report_json"] = pms_report_payload
        response_payload["pms_json_file"] = folder_json_path

        # Keep the AI inspection result separate from the final verdict.
        response_payload["ai_verdict"] = verdict_label

        # Publish ReportStore and wait for PMS validation.
        try:
            pms_response = pms_mqtt.publish_report(
                pms_report_payload
            )

            response_payload["pms_mqtt_response"] = pms_response

            if (
                pms_response.get("received") is True
                and pms_response.get("accepted") is True
            ):
                # PMS accepted ReportStore: use the AI inspection verdict.
                response_payload["verdict"] = verdict_label
                response_payload["pms_report_status"] = "ACCEPTED"

            elif pms_response.get("received") is True:
                # PMS responded but did not accept ReportStore.
                response_payload["verdict"] = "FAIL"
                response_payload["pms_report_status"] = "REJECTED"

                response_payload["pms_rejection_reason"] = (
                    pms_response.get("reason")
                    or pms_response.get("request_status")
                    or "PMS rejected the ReportStore request."
                )

            else:
                # No matching PMS response after the retry attempts.
                response_payload["verdict"] = "SERVER UNREACHABLE"
                response_payload["pms_report_status"] = "UNREACHABLE"

        except Exception as exc:
            print(f"[PMS] ReportStore publish error: {exc}")

            response_payload["pms_mqtt_response"] = {
                "received": False,
                "accepted": False,
                "message": str(exc)
            }


            response_payload["verdict"] = "SERVER UNREACHABLE"
            response_payload["pms_report_status"] = "UNREACHABLE"


        notes_lines.append(f"\n📡 PMS JSON REPORT ({verdict_label}):")
        notes_lines.append(f" • Verdict: {verdict_label} (ViTest: {1 if combined_pass else 0}, WireOrigin: {1 if origins_all_pass else 0})")
        notes_lines.append(f" • TaktTime: {round(takt_time, 3)}s")
        notes_lines.append(f" • Saved in Result/{target_folder}/: {os.path.basename(folder_json_path)}")
        notes_lines.append(f" • Saved in Result/PMS_Payloads/: {os.path.basename(pms_json_path)}")
    except Exception as e:
        print(f"[PMS Report] Warning: Could not generate PMS report: {e}")

    notes_lines.append(f"\n📊 Logged record to: Result/Inspection_Log.xlsx")
    notes_lines.append(f"📁 Saved result images to: Result/{target_folder}/")

    response_payload["results"] = {
        "obl_pass": obl_pass,
        "oum_pass": oum_pass,
        "obr_pass": effective_origin3_pass,
        "raw_obr_pass": raw_obr_pass,
        "c1_pass": c1_pass,
        "c2_pass": c2_pass,
        "c3_pass": c3_pass,
        "orig3_grommet_pass": orig3_grommet_pass,
        "orig2_grommet_pass": orig3_grommet_pass
    }
    response_payload["device_id"] = serial_no
    response_payload["raw_qr"] = device_id
    response_payload["serial_no"] = serial_no
    response_payload["apo_id"] = apo_id
    response_payload["combined_pass"] = combined_pass
    response_payload["saved_folder"] = f"Result/{target_folder}"
    response_payload["excel_log"] = "Result/Inspection_Log.xlsx"
    response_payload["notes"] = "\n".join(notes_lines)

    return jsonify(response_payload)

@app.route("/api/pms/payloads", methods=["GET", "POST"])
def pms_payloads_endpoint():
    """
    Returns all 4 required PMS JSON payloads.
    The JSON fields will stay empty until the device has been scanned AND
    the server has responded with matching UtcRequest_ID and CONFIG SUCCESSFUL.
    """
    device_id = str(request.args.get("device_id") or "").strip()

    if not device_id:
        return jsonify({
            "status": "success",
            "detected_mac": "",
            "raw_qr": "",
            "scanned_serial_no": "",
            "device_serial_no": "",
            "apo_number_id": "",
            "payloads": build_empty_payloads(),
            "server_responses": {}
        })

    apo_id, serial_no = parse_sticker(device_id)

    # Check if this exact device has completed server validation with CONFIG SUCCESSFUL
    is_validated = (
        validated_device_cache.get("serial_no") == serial_no
        and validated_device_cache.get("payloads") is not None
        and (time.time() - validated_device_cache.get("timestamp", 0.0)) < 600.0
    )

    if not is_validated:
        # User requirement: "else these json fields will stay empty"
        return jsonify({
            "status": "unvalidated",
            "detected_mac": "",
            "raw_qr": device_id,
            "scanned_serial_no": serial_no,
            "device_serial_no": "",
            "apo_number_id": "",
            "payloads": build_empty_payloads(),
            "server_responses": {}
        })

    # Device is confirmed validated by server! Return the validated payloads.
    mac = get_pc_mac_address()
    validated_payloads = validated_device_cache.get("payloads") or {}
    server_responses = validated_device_cache.get("server_responses") or {}
    return jsonify({
        "status": "success",
        "detected_mac": mac,
        "raw_qr": device_id,
        "scanned_serial_no": serial_no,
        "device_serial_no": serial_no,
        "apo_number_id": apo_id,
        "payloads": validated_payloads,
        "server_responses": server_responses
    })

def open_browser():
    time.sleep(1.8)
    url = "http://127.0.0.1:7860/"
    opened = False
    try:
        opened = webbrowser.open(url, new=2)
    except Exception as e:
        print(f"[Browser] webbrowser.open: {e}")
    if not opened and sys.platform.startswith("win"):
        try:
            import subprocess
            subprocess.run(f'start "" "{url}"', shell=True)
        except Exception as e:
            print(f"[Browser] start command: {e}")

# if __name__ == "__main__":
#     print("\n" + "="*65)
#     print(" Dual-Camera Wiring & Origin Inspection System (Web App)")
#     print(" Running at: http://127.0.0.1:7860/")
#     print(" Inspection Log: Result/Inspection_Log.xlsx")
#     print(" Opening default web browser automatically...")
#     print("="*65 + "\n")
    
#     # Auto open browser in background thread
#     threading.Thread(target=open_browser, daemon=True).start()
#     app.run(host="127.0.0.1", port=7860, debug=False)



if __name__ == "__main__":
    print("\n" + "=" * 65)
    print(" Dual-Camera Wiring & Origin Inspection System (Web App)")
    print(" Running at: http://127.0.0.1:7860/")
    print(" Inspection Log: Result/Inspection_Log.xlsx")
    print(" Opening default web browser automatically...")
    print("=" * 65 + "\n")

    # Start MQTT connection in the background
    def start_mqtt_connection():
        try:
            print("[PMS MQTT] Starting connection...")
            pms_mqtt.connect()
            print("[PMS MQTT] Connected and subscribed successfully.")
        except Exception as e:
            print(f"[PMS MQTT] Connection failed: {e}")

    threading.Thread(
        target=start_mqtt_connection,
        daemon=True,
        name="PMS-MQTT-Connection"
    ).start()

    # Auto open browser in background thread
    threading.Thread(target=open_browser, daemon=True).start()

    app.run(host="127.0.0.1", port=7860, debug=False)
