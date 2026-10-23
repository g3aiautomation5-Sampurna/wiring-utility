# System Architecture: Dual-Camera Wire Harness & Origin Inspection System

## 1. System Overview

The **Dual-Camera Wire Harness & Origin Inspection System** is an automated optical inspection (AOI) solution designed for industrial quality assurance of wire harnesses and PCB assembly origins. It combines multi-camera vision acquisition, custom color/spatial morphology analysis, multi-view decision fusion, operator tooling, and automated traceability logging.

---

## 2. High-Level Architecture Diagram

```mermaid
flowchart TB
    subgraph HARDWARE["1. Hardware & Acquisition Layer"]
        CAM_TOP["Arducam_TOP\n(Top-Down Global Camera)"]
        CAM_ORIGIN["Arducam_ORIGIN\n(Angled Macro Grommet Camera)"]
        QR_SCANNER["Barcode / QR Scanner\n(USB HID / Keyboard Input)"]
    end

    subgraph PRESENTATION["2. Presentation & Operator Layer"]
        direction TB
        WEB_UI["Web Dashboard\n(HTML5 / CSS3 / Vanilla JS)"]
        GUI_TK["Legacy Desktop GUI\n(Tkinter / PIL)"]
        WEB_UI --- LIVE_FEED["Dual Live Video Feed & Canvas Overlay"]
        WEB_UI --- DIAG_PANEL["Diagnostic & Verdict HUD"]
        WEB_UI --- SN_INPUT["Device / Serial ID Capture"]
    end

    subgraph APP_SERVER["3. Application & Controller Layer (Flask / Python)"]
        FLASK_APP["Flask Web Server (web_wiring.py / :7860)"]
        ENDPOINTS["REST API Endpoints:\n• POST /api/inspect\n• POST /api/open_excel\n• GET /api/download_excel"]
        DECISION_ENGINE["Multi-View Decision & Fusion Engine"]
    end

    subgraph CV_PIPELINE["4. Computer Vision Inspection Engine (OpenCV / NumPy)"]
        direction TB
        PREPROCESS["Pre-processing & Color Segmentation\n(BGR to HSV, Dynamic Color Masks)"]
        
        subgraph MODULE_WIRE["Wire Routing Module (detect_wiring.py)"]
            CASE1["Case 1 (BL):\nRed Left of Black"]
            CASE2["Case 2 (UM):\nVerified via Origin (Coils)"]
            CASE3["Case 3 (BR):\nRed Left of Black (Exit)"]
        end

        subgraph MODULE_ORIGIN["Top Origin Module (detect_origin.py)"]
            ORIG1["Origin 1 (BL):\nBlack Upper / Red Lower Socket"]
            ORIG2["Origin 2 (UM):\nRed on Middle Coil"]
            ORIG3_TOP["Origin 3 (BR):\nRed Entry in Front/Above Black"]
        end

        subgraph MODULE_GROMMET["Dedicated Grommet Module (detect_origin2.py)"]
            BLUE_FINDER["Blue Terminal ROI Auto-Locator"]
            GROMMET_CROP["Adaptive Grommet Crop (130x140)"]
            DUAL_WIRE_CHECK["Dual Wire Presence (Red & Black)"]
        end
    end

    subgraph STORAGE["5. Persistence, Traceability & Reporting Layer"]
        EXCEL_LOG["Excel Inspection Log\n(openpyxl - Inspection_Log.xlsx)"]
        CSV_LOG["CSV Audit Log\n(Inspection_Log.csv)"]
        SNAP_PASS["Result/Pass/\n(Annotated & Raw Images)"]
        SNAP_FAIL["Result/Fail/\n(Annotated & Raw Images)"]
    end

    %% Connections
    CAM_TOP -->|USB Video Stream| WEB_UI
    CAM_ORIGIN -->|USB Video Stream| WEB_UI
    QR_SCANNER -->|Serial Number Scan| SN_INPUT
    
    WEB_UI -->|Snapshot Frame Payloads & Serial ID| ENDPOINTS
    ENDPOINTS --> FLASK_APP
    FLASK_APP --> PREPROCESS
    
    PREPROCESS --> MODULE_WIRE
    PREPROCESS --> MODULE_ORIGIN
    PREPROCESS --> MODULE_GROMMET

    MODULE_WIRE --> DECISION_ENGINE
    MODULE_ORIGIN --> DECISION_ENGINE
    MODULE_GROMMET --> DECISION_ENGINE

    DECISION_ENGINE -->|Multi-Camera Arbitration| FLASK_APP
    FLASK_APP -->|JSON Response + Annotated Base64| WEB_UI

    DECISION_ENGINE -->|Log Results| EXCEL_LOG
    DECISION_ENGINE -->|Log Results| CSV_LOG
    DECISION_ENGINE -->|Archive Captures| SNAP_PASS
    DECISION_ENGINE -->|Archive Captures| SNAP_FAIL
```

---

## 3. Detailed Dataflow & Inspection Pipeline

```mermaid
sequenceDiagram
    autonumber
    actor Operator
    participant UI as Web Dashboard (Browser)
    participant API as Flask Server (web_wiring.py)
    participant TOP_CV as Top-View Engine (detect_origin & detect_wiring)
    participant DED_CV as Grommet Engine (detect_origin2)
    participant Fusion as Decision Fusion Engine
    participant Store as Storage & Excel Logger

    Operator->>UI: Scan Device QR / Barcode & Trigger Inspect
    UI->>UI: Capture synchronised frames from Top & Origin cameras
    UI->>API: POST /api/inspect (Base64 Top & Origin frames + Device ID)
    
    par Top Camera Processing
        API->>TOP_CV: process_top_inspection(top_img)
        TOP_CV->>TOP_CV: Resize to 1024x576 & HSV conversion
        TOP_CV->>TOP_CV: Evaluate Origins (BL, UM, BR)
        TOP_CV->>TOP_CV: Evaluate Wire Paths (Case 1, 2, 3)
        TOP_CV->>TOP_CV: Generate Visual Annotated Overlays
        TOP_CV-->>API: Returns obl, oum, obr, c1, c2, c3 statuses
    and Dedicated Grommet Processing
        API->>DED_CV: process_orig3_inspection(orig3_img)
        DED_CV->>DED_CV: Auto-detect blue crimp terminal ($x \ge 140$)
        DED_CV->>DED_CV: Crop Grommet ROI & filter red/black pixels
        DED_CV->>DED_CV: Generate Visual Annotated Overlay
        DED_CV-->>API: Returns orig3_grommet_pass status
    end

    API->>Fusion: Arbitrate verdicts & resolve occlusions
    Note over Fusion: effective_origin3 = top_obr OR orig3_grommet<br/>combined_pass = all_wires_pass AND all_origins_pass
    Fusion-->>API: Overall PASS / FAIL + diagnostics

    par Persistence
        API->>Store: Save raw & annotated JPEGs to Result/Pass or Result/Fail
        API->>Store: Append record to Inspection_Log.xlsx & CSV
    end

    API-->>UI: Return JSON payload with annotated images & summary
    UI->>Operator: Display real-time Color Overlays, Status Badges & Logs
```

---

## 4. Multi-View Decision Fusion Logic

```mermaid
flowchart TD
    START([Start Inspection]) --> CAPTURE[Receive Dual Image Feeds]

    subgraph TOP_CHECKS["Top View Checks (Arducam_TOP)"]
        W1{"Case 1 BL Wire:\nRed Left of Black?"}
        W2{"Case 2 UM Wire:\nRed Right of Black?"}
        W3{"Case 3 BR Wire:\nRed Left of Black?"}
        O1{"Origin 1 BL:\nBlack Socket above Red?"}
        O2{"Origin 2 UM:\nRed on Middle Coil?"}
        O3_TOP{"Origin 3 BR (Top View):\nRed above Black?"}
    end

    subgraph DEDICATED_CHECK["Dedicated Macro Check (Arducam_ORIGIN)"]
        O3_DED{"Origin 3 Grommet:\nBoth Red & Black wires verified?"}
    end

    CAPTURE --> TOP_CHECKS
    CAPTURE --> DEDICATED_CHECK

    O3_TOP -->|Pass| O3_EFFECTIVE[Origin 3 Effective PASS]
    O3_TOP -->|Fail| O3_FALLBACK{Dedicated Grommet Passed?}
    O3_DED -->|Pass| O3_FALLBACK
    O3_FALLBACK -->|Yes| O3_EFFECTIVE
    O3_FALLBACK -->|No| O3_FAIL[Origin 3 FAIL]

    W1 & W2 & W3 --> WIRE_ALL{All 3 Wire Paths PASS?}
    O1 & O2 & O3_EFFECTIVE --> ORIGIN_ALL{All 3 Origins PASS?}

    WIRE_ALL -->|Yes| FINAL_CHECK
    WIRE_ALL -->|No| VERDICT_FAIL[VERDICT: FAIL]
    ORIGIN_ALL -->|Yes| FINAL_CHECK{Wires PASS & Origins PASS?}
    ORIGIN_ALL -->|No| VERDICT_FAIL

    FINAL_CHECK -->|Yes| VERDICT_PASS[VERDICT: PASS]
    FINAL_CHECK -->|No| VERDICT_FAIL

    VERDICT_PASS --> SAVE_PASS[Save to Result/Pass/ & Log Excel]
    VERDICT_FAIL --> SAVE_FAIL[Save to Result/Fail/ & Log Excel]
```

---

## 5. Subsystem Component Breakdown

| Layer / Component | Source File(s) | Primary Technology | Key Responsibilities |
| :--- | :--- | :--- | :--- |
| **Hardware & Devices** | `rename_camera.ps1`, `rename_camera.bat` | PowerShell, Win32 PNP | Registry-level USB camera renaming, multi-camera discovery, barcode scanner input |
| **Web Server & UI** | `web_wiring.py` | Flask, HTML5, CSS3, JavaScript | Single-page responsive operator dashboard, dual camera live preview, QR scanning, API endpoints |
| **Desktop GUI (Alt)** | `gui_wiring.py` | Tkinter, Pillow | Standalone desktop GUI fallback for direct local camera streams |
| **Wire Path Inspector** | `detect_wiring.py`, `web_wiring.py` | OpenCV, NumPy | HSV color segmentation, spatial moment analysis, connected component analysis across 3 critical routing ROIs |
| **Top Origin Inspector** | `detect_origin.py` | OpenCV, NumPy | Checks socket insertion polarity and inductor coil wiring terminals |
| **Dedicated Macro Inspector** | `detect_origin2.py` | OpenCV, NumPy | Blue terminal tracking, dynamic grommet ROI cropping, operator clothing noise rejection, wire presence validation |
| **CLI & Batch Pipeline** | `main.py` | Python 3 | Headless evaluation runner for test scripts, automated regression testing |
| **Data Logging & Excel** | `web_wiring.py` | openpyxl, CSV | Formatted, color-coded tabular audit logs with automated column resizing and freeze panes |
| **Packaging & Executable** | `web_wiring.spec`, `web_wiring.exe` | PyInstaller | Standalone portable zero-dependency executable for production deployment |
