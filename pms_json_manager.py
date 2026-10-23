import os
import sys
import re
import time
import json
import uuid
import random
import subprocess
from datetime import datetime

# CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pms_config.json")

# For keeping json file out of exe 
if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(APP_DIR, "pms_config.json")
OUTPUT_DIR = os.path.join(APP_DIR, "Result", "PMS_Payloads")

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Result", "PMS_Payloads")

DEFAULT_CONFIG = {
    "use_mac_as_serial": True,
    "production_line_no": "1",
    "jig_uid": "CGJIGxxxxxxxxxx00111",
    "testing_stage": "X_POWER_SUPPLY_4Point3",
    "slave_version_no": "4.3",
    "default_apo_number_id": "56",
    "table_report": "Z_VI_TEST",
    "table_serial": "K_ALL_SERIAL_NUMBER",
    "table_status": "E_DEVICE",
    "pms_broker_ip": "127.0.0.1",
    "pms_broker_port": 1883,
}

def load_or_create_config():
    """Loads configuration from pms_config.json or creates it with defaults."""
    if not os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, indent=4)
        except Exception as e:
            print(f"[PMS Config] Warning: Could not create {CONFIG_FILE}: {e}")
        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            # Ensure all default keys exist
            for k, v in DEFAULT_CONFIG.items():
                if k not in cfg:
                    cfg[k] = v
            return cfg
    except Exception as e:
        print(f"[PMS Config] Warning: Could not read {CONFIG_FILE}: {e}")
        return DEFAULT_CONFIG.copy()

def get_pc_mac_address():
    """
    Automatically detects the physical network adapter MAC address on any Windows/Linux/macOS PC.
    If 'device_mac_override' is set in pms_config.json, it will use that.
    Returns uppercase colon-formatted MAC: e.g. '38:18:2B:E7:92:F8'.
    """
    try:
        cfg = load_or_create_config()
        override = (cfg.get("device_mac_override") or "").strip()
        if override:
            return override.upper()
    except Exception:
        pass

    # Method 1: On Windows, use 'getmac' command to get active physical adapter
    if sys.platform.startswith("win"):
        try:
            cmd = "getmac /fo csv /nh"
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode(errors="ignore")
            for line in output.strip().splitlines():
                parts = [p.strip(' "') for p in line.split(',')]
                if parts and parts[0] and "N/A" not in parts[0] and "Disconnected" not in line:
                    mac_clean = parts[0].replace('-', ':').upper()
                    if re.match(r'^([0-9A-F]{2}:){5}[0-9A-F]{2}$', mac_clean):
                        return mac_clean
        except Exception:
            pass

    # Method 2: Standard cross-platform uuid.getnode()
    try:
        node = uuid.getnode()
        # Verify it's not a temporary/random address (check multicast bit)
        if not (node >> 40) & 0x01:
            mac_str = ':'.join(f"{(node >> (8 * i)) & 0xff:02X}" for i in reversed(range(6)))
            if re.match(r'^([0-9A-F]{2}:){5}[0-9A-F]{2}$', mac_str):
                return mac_str
    except Exception:
        pass

    # Fallback to general uuid representation
    node = uuid.getnode()
    return ':'.join(f"{(node >> (8 * i)) & 0xff:02X}" for i in reversed(range(6)))

def get_thinclient_uid():
    """
    Fetches the unique Thinclient / Machine Hardware UID that changes from PC to PC.
    Priority:
    1. If 'use_mac_as_serial' is set in pms_config.json, uses Device MAC.
    2. System Hardware UUID (Win32_ComputerSystemProduct.UUID)
    3. Windows Registry MachineGuid
    4. BIOS Serial Number
    5. Fallback: Host MAC Address
    """
    try:
        cfg = load_or_create_config()
        if cfg.get("use_mac_as_serial", False) or str(cfg.get("serial_source", "")).lower() == "mac":
            return get_pc_mac_address()
    except Exception:
        pass

    if sys.platform.startswith("win"):
        # 1. System Hardware UUID (Standard Thinclient / OEM UUID)
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_ComputerSystemProduct).UUID"],
                capture_output=True, text=True, timeout=3
            )
            out = res.stdout.strip()
            if out and len(out) > 8 and "00000000" not in out and "FFFFFFFF" not in out:
                return out
        except Exception:
            pass

        # 2. Windows Registry MachineGuid (Unique per Windows installation)
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
                guid, _ = winreg.QueryValueEx(key, "MachineGuid")
                if guid and guid.strip():
                    return guid.strip().upper()
        except Exception:
            pass

        # 3. BIOS Serial Number
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_BIOS).SerialNumber"],
                capture_output=True, text=True, timeout=3
            )
            out = res.stdout.strip()
            if out and len(out) > 3 and "Default" not in out and "To be filled" not in out:
                return out
        except Exception:
            pass

    # 4. Fallback: Host MAC Address
    mac = get_pc_mac_address()
    return mac.replace(":", "").upper()

def generate_utc_request_id():
    """
    Generates UtcRequest_ID as specified in document:
    13-digit epoch in ms + 19 random digits (e.g. 179101286776517797148103240069120)
    """
    epoch_ms = str(int(time.time() * 1000))
    random_digits = "".join([str(random.randint(0, 9)) for _ in range(19)])
    return epoch_ms + random_digits

def parse_sticker(scanned_code=None, default_apo=None):
    """
    Parses scanned barcode/QR sticker.
    Expected QR text format: 'Id: ..; Sr: ..;'
    - 'Id: <apo_number_id>' -> extracted as APoNumberId (e.g. '56')
    - 'Sr: <device_serial_no>' -> extracted as DeviceSerialNo (e.g. '001260101010122505100002640000142')

    Also supports:
    - Delimited format: '56,001260101...' or '56|00126...' -> (apo_id, serial_no)
    - Plain serial without APO: '00126...' -> (default_apo, serial_no)
    - Empty / N/A -> (default_apo, thinclient_uid)
    """
    if default_apo is None:
        cfg = load_or_create_config()
        default_apo = cfg.get("default_apo_number_id", "56")

    scanned = str(scanned_code).strip() if scanned_code else ""
    if not scanned or scanned in ["N/A", "None", "", "device"]:
        return str(default_apo), get_thinclient_uid()

    # 1. Match explicit Id: ... and/or Sr: ... pattern (case-insensitive)
    id_match = re.search(r'(?:^|[;,|\r\n\s])\s*(?:APoNumberId|APO(?:_?ID)?|Id)\s*[:=]\s*([^;,|\r\n]+)', scanned, re.IGNORECASE)
    sr_match = re.search(r'(?:^|[;,|\r\n\s])\s*(?:DeviceSerial(?:No)?|Serial(?:No)?|Sr(?:No)?|SN)\s*[:=]\s*([^;,|\r\n]+)', scanned, re.IGNORECASE)

    if id_match or sr_match:
        apo = id_match.group(1).strip() if id_match else str(default_apo)
        serial = sr_match.group(1).strip() if sr_match else get_thinclient_uid()
        if not serial:
            serial = get_thinclient_uid()
        if not apo:
            apo = str(default_apo)
        return apo, serial

    # 2. Legacy delimited formats (e.g. '56,00126...', '56|00126...')
    for delimiter in [",", "|", ";", "/"]:
        if delimiter in scanned:
            parts = [p.strip() for p in scanned.split(delimiter) if p.strip()]
            if len(parts) >= 2:
                apo = parts[0]
                serial = parts[1]
                if apo and serial:
                    return apo, serial
            elif len(parts) == 1:
                return str(default_apo), parts[0]

    return str(default_apo), scanned

def build_device_autowhitelisting(mac_id=None):
    """
    Builds the DeviceAutoWhitelisting payload.
    """
    config = load_or_create_config()
    if not mac_id:
        mac_id = get_pc_mac_address()

    req_id = generate_utc_request_id()
    payload = {
        "CmdType": "DeviceAutoWhitelisting",
        "UtcRequest_ID": req_id,
        "Device_MAC_ID": mac_id,
        "TopicToPublish": (
            f"{config['pms_publish_topic_prefix'].rstrip('/')}/{mac_id}"
        ),
        "TopicToSubscribe": (
            f"{config['pms_subscribe_topic_prefix'].rstrip('/')}/{mac_id}"
        )
    }
    return req_id, payload

def build_serial_no_validation(device_serial_no=None, apo_number_id=None, mac_id=None, testing_stage=None, slave_version=None):
    """
    Builds the SerialNoValidation payload.
    If device_serial_no is not provided, automatically uses the Thinclient UID / MAC.
    """
    cfg = load_or_create_config()
    if not mac_id:
        mac_id = get_pc_mac_address()

    # Auto-parse if a full QR string (e.g. 'Id: ..; Sr: ..;') was passed as device_serial_no
    if device_serial_no and any(k in str(device_serial_no).lower() for k in ["id:", "sr:"]):
        parsed_apo, parsed_serial = parse_sticker(device_serial_no, default_apo=apo_number_id)
        if not apo_number_id:
            apo_number_id = parsed_apo
        device_serial_no = parsed_serial

    if not device_serial_no or str(device_serial_no).strip() in ["", "None", "N/A"]:
        device_serial_no = get_thinclient_uid()
    if not apo_number_id:
        apo_number_id = cfg.get("default_apo_number_id", "56")
    if not testing_stage:
        testing_stage = cfg.get("testing_stage", "X_POWER_SUPPLY_4Point3")
    if not slave_version:
        slave_version = cfg.get("slave_version_no", "4.3")

    req_id = generate_utc_request_id()
    table_serial = cfg.get("table_serial_validation") or cfg.get("table_serial", "K_ALL_SERIAL_NUMBER")
    payload = {
        "CmdType": "SerialNoValidation",
        "UtcRequest_ID": req_id,
        "Device_MAC_ID": mac_id,
        "TableName": table_serial,
        "TestingStage": testing_stage,
        "SlaveVersionNo": slave_version,
        "ColumnsName": [
            {
                "APoNumberId": str(apo_number_id),
                "DeviceSerialNo": str(device_serial_no),
                "DevicePrintNo": "",
                "PowerSupplySerialNo": "",
                "PowerSupplyPrintNo": "",
                "DisplaySerialNo": "",
                "DisplayPrintNo": "",
                "LogicSerialNo": "",
                "LogicPrintNo": "",
                "RowCreationTimeStamp": "",
                "RowUpdationTimeStamp": "",
                "KAllSerialNumberId": "",
                "LineNo": ""
            }
        ]
    }
    return req_id, payload

def build_status_validation(device_serial_no=None, apo_number_id=None, mac_id=None):
    """
    Builds the StatusValidation payload (Interlocking check).
    If device_serial_no is not provided, automatically uses the Thinclient UID / MAC.
    """
    cfg = load_or_create_config()
    if not mac_id:
        mac_id = get_pc_mac_address()

    # Auto-parse if a full QR string (e.g. 'Id: ..; Sr: ..;') was passed as device_serial_no
    if device_serial_no and any(k in str(device_serial_no).lower() for k in ["id:", "sr:"]):
        parsed_apo, parsed_serial = parse_sticker(device_serial_no, default_apo=apo_number_id)
        if not apo_number_id:
            apo_number_id = parsed_apo
        device_serial_no = parsed_serial

    if not device_serial_no or str(device_serial_no).strip() in ["", "None", "N/A"]:
        device_serial_no = get_thinclient_uid()
    if not apo_number_id:
        apo_number_id = cfg.get("default_apo_number_id", "56")

    req_id = generate_utc_request_id()
    table_status = cfg.get("table_status_validation") or cfg.get("table_status", "E_DEVICE")
    payload = {
        "CmdType": "StatusValidation",
        "UtcRequest_ID": req_id,
        "Device_MAC_ID": mac_id,
        "TableName": table_status,
        "ColumnsName": [
            {
                "APoNumberId": str(apo_number_id),
                "EMainId": "",
                "DeviceSerialNo": str(device_serial_no),
                "RowCreationTimeStamp": "",
                "RowUpdationTimeStamp": "",
                "PowerSupplyBoardTest": "",
                "LogicBoardTest": "",
                "DisplayBoardTest": "",
                "PowerOnStageTest": "1",
                "HVTest": "1",
                "HRTTest": "",
                "FunctionalTest": "",
                "PackingStage": "",
                "ViTest": "",
                "LinkingStage": ""
            }
        ]
    }
    return req_id, payload

def build_report_store(device_serial_no=None, apo_number_id=None, takt_time=0.0, wire_origin_pass=True, vi_test_pass=True, mac_id=None, line_no=None, jig_uid=None):
    """
    Builds the ReportStore payload (Final Test Result) to be stored in table Z_VI_TEST.
    If device_serial_no is not provided, automatically uses the Thinclient UID / MAC.
    """
    cfg = load_or_create_config()
    if not mac_id:
        mac_id = get_pc_mac_address()

    # Auto-parse if a full QR string (e.g. 'Id: ..; Sr: ..;') was passed as device_serial_no
    if device_serial_no and any(k in str(device_serial_no).lower() for k in ["id:", "sr:"]):
        parsed_apo, parsed_serial = parse_sticker(device_serial_no, default_apo=apo_number_id)
        if not apo_number_id:
            apo_number_id = parsed_apo
        device_serial_no = parsed_serial

    if not device_serial_no or str(device_serial_no).strip() in ["", "None", "N/A"]:
        device_serial_no = get_thinclient_uid()
    if not apo_number_id:
        apo_number_id = cfg.get("default_apo_number_id", "56")
    if not line_no:
        line_no = cfg.get("plc_jig_production_line_no") or cfg.get("production_line_no", "1")
    if not jig_uid:
        jig_uid = cfg.get("jig_uid", "CGJIGxxxxxxxxxx00111")

    now = datetime.now()
    epoch_ms = int(now.timestamp() * 1000)
    req_id = generate_utc_request_id()
    table_report = cfg.get("table_report_store") or cfg.get("table_report", "Z_VI_TEST")

    payload = {
        "CmdType": "ReportStore",
        "UtcRequest_ID": req_id,
        "Device_MAC_ID": mac_id,
        "TableName": table_report,
        "ColumnsName": [
            {
                "APoNumberId": str(apo_number_id),
                "RowCreationTimeStamp": epoch_ms,
                "RowUpdationTimeStamp": epoch_ms,
                "WifiMasterMacid": mac_id,
                "WifiDate": now.strftime("%d-%B-%Y, %A"),
                "WifiTime": now.strftime("%H:%M:%S"),
                "PlcJigProductionLineNo": str(line_no),
                "DeviceSerialNo": str(device_serial_no),
                "TaktTime": round(float(takt_time), 3),
                "JigUid": str(jig_uid),
                "WireOrigin": 1 if wire_origin_pass else 0,
                "ViTest": 1 if vi_test_pass else 0
            }
        ]
    }
    return req_id, payload

def build_empty_report_store(device_serial_no="", apo_number_id="", mac_id=""):
    """
    Builds the ReportStore template with empty test results.
    Used before inspection is performed.
    """
    cfg = load_or_create_config()
    table_report = cfg.get("table_report_store") or cfg.get("table_report", "Z_VI_TEST")
    line_no = cfg.get("plc_jig_production_line_no") or cfg.get("production_line_no", "")
    jig_uid = cfg.get("jig_uid", "")

    return {
        "CmdType": "ReportStore",
        "UtcRequest_ID": "",
        "Device_MAC_ID": str(mac_id) if mac_id else "",
        "TableName": table_report,
        "ColumnsName": [
            {
                "APoNumberId": str(apo_number_id) if apo_number_id else "",
                "RowCreationTimeStamp": "",
                "RowUpdationTimeStamp": "",
                "WifiMasterMacid": str(mac_id) if mac_id else "",
                "WifiDate": "",
                "WifiTime": "",
                "PlcJigProductionLineNo": str(line_no) if line_no else "",
                "DeviceSerialNo": str(device_serial_no) if device_serial_no else "",
                "TaktTime": "",
                "JigUid": str(jig_uid) if jig_uid else "",
                "WireOrigin": "",
                "ViTest": ""
            }
        ]
    }

def build_empty_payloads():
    """
    Returns all 4 PMS JSON templates where all dynamic and data fields are empty.
    Used before scanning any barcode and before running any inspection.
    """
    cfg = load_or_create_config()
    table_serial = cfg.get("table_serial_validation") or cfg.get("table_serial", "K_ALL_SERIAL_NUMBER")
    table_status = cfg.get("table_status_validation") or cfg.get("table_status", "E_DEVICE")
    table_report = cfg.get("table_report_store") or cfg.get("table_report", "Z_VI_TEST")

    return {
        "DeviceAutoWhitelisting": {
            "CmdType": "DeviceAutoWhitelisting",
            "UtcRequest_ID": "",
            "Device_MAC_ID": "",
            "TopicToPublish": "",
            "TopicToSubscribe": ""
        },
        "SerialNoValidation": {
            "CmdType": "SerialNoValidation",
            "UtcRequest_ID": "",
            "Device_MAC_ID": "",
            "TableName": table_serial,
            "TestingStage": "",
            "SlaveVersionNo": "",
            "ColumnsName": [
                {
                    "APoNumberId": "",
                    "DeviceSerialNo": "",
                    "DevicePrintNo": "",
                    "PowerSupplySerialNo": "",
                    "PowerSupplyPrintNo": "",
                    "DisplaySerialNo": "",
                    "DisplayPrintNo": "",
                    "LogicSerialNo": "",
                    "LogicPrintNo": "",
                    "RowCreationTimeStamp": "",
                    "RowUpdationTimeStamp": "",
                    "KAllSerialNumberId": "",
                    "LineNo": ""
                }
            ]
        },
        "StatusValidation": {
            "CmdType": "StatusValidation",
            "UtcRequest_ID": "",
            "Device_MAC_ID": "",
            "TableName": table_status,
            "ColumnsName": [
                {
                    "APoNumberId": "",
                    "EMainId": "",
                    "DeviceSerialNo": "",
                    "RowCreationTimeStamp": "",
                    "RowUpdationTimeStamp": "",
                    "PowerSupplyBoardTest": "",
                    "LogicBoardTest": "",
                    "DisplayBoardTest": "",
                    "PowerOnStageTest": "",
                    "HVTest": "",
                    "HRTTest": "",
                    "FunctionalTest": "",
                    "PackingStage": "",
                    "ViTest": "",
                    "LinkingStage": ""
                }
            ]
        },
        "ReportStore": {
            "CmdType": "ReportStore",
            "UtcRequest_ID": "",
            "Device_MAC_ID": "",
            "TableName": table_report,
            "ColumnsName": [
                {
                    "APoNumberId": "",
                    "RowCreationTimeStamp": "",
                    "RowUpdationTimeStamp": "",
                    "WifiMasterMacid": "",
                    "WifiDate": "",
                    "WifiTime": "",
                    "PlcJigProductionLineNo": "",
                    "DeviceSerialNo": "",
                    "TaktTime": "",
                    "JigUid": "",
                    "WireOrigin": "",
                    "ViTest": ""
                }
            ]
        }
    }

def get_all_payloads(device_serial_no=None, apo_number_id=None, takt_time=0.0, wire_origin_pass=True, vi_test_pass=True, mac_id=None):
    """
    Returns all 4 required PMS payloads in one call.
    """
    if not mac_id:
        mac_id = get_pc_mac_address()

    # Auto-parse if a full QR string (e.g. 'Id: ..; Sr: ..;') was passed as device_serial_no
    if device_serial_no and any(k in str(device_serial_no).lower() for k in ["id:", "sr:"]):
        parsed_apo, parsed_serial = parse_sticker(device_serial_no, default_apo=apo_number_id)
        if not apo_number_id:
            apo_number_id = parsed_apo
        device_serial_no = parsed_serial

    if not device_serial_no or str(device_serial_no).strip() in ["", "None", "N/A"]:
        device_serial_no = get_thinclient_uid()
    if not apo_number_id:
        cfg = load_or_create_config()
        apo_number_id = cfg.get("default_apo_number_id", "56")
    
    _, p1 = build_device_autowhitelisting(mac_id)
    _, p2 = build_serial_no_validation(device_serial_no, apo_number_id, mac_id)
    _, p3 = build_status_validation(device_serial_no, apo_number_id, mac_id)
    _, p4 = build_report_store(device_serial_no, apo_number_id, takt_time, wire_origin_pass, vi_test_pass, mac_id)

    return {
        "mac_address": mac_id,
        "device_serial_no": device_serial_no,
        "apo_number_id": apo_number_id,
        "DeviceAutoWhitelisting": p1,
        "SerialNoValidation": p2,
        "StatusValidation": p3,
        "ReportStore": p4
    }

def save_payload_to_file(payload, name_prefix="payload"):
    """
    Saves a payload JSON to Result/PMS_Payloads/<prefix>_<timestamp>.json
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(OUTPUT_DIR, f"{name_prefix}_{ts}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=4)
    return filepath

if __name__ == "__main__":
    print("\n" + "="*70)
    print("SELEC CONTROLS - PMS JSON OUTPUT GENERATOR")
    print("="*70)
    
    mac = get_pc_mac_address()
    print(f"[*] Detected Machine Physical MAC Address: {mac}")
    
    cfg = load_or_create_config()
    print(f"[*] Loaded Configuration: {json.dumps(cfg, indent=2)}")
    
    # Uniform PC Identification: Use MAC Address as Serial No
    sample_serial = get_thinclient_uid()
    sample_apo = "56"
    sample_takt_time = 41.272
    sample_wire_pass = True
    sample_vi_pass = True

    print("\n--- 1. DeviceAutoWhitelisting Payload ---")
    _, p1 = build_device_autowhitelisting(mac)
    print(json.dumps(p1, indent=2))
    save_payload_to_file(p1, "1_DeviceAutoWhitelisting")

    print("\n--- 2. SerialNoValidation Payload ---")
    _, p2 = build_serial_no_validation(sample_serial, sample_apo, mac)
    print(json.dumps(p2, indent=2))
    save_payload_to_file(p2, "2_SerialNoValidation")

    print("\n--- 3. StatusValidation Payload ---")
    _, p3 = build_status_validation(sample_serial, sample_apo, mac)
    print(json.dumps(p3, indent=2))
    save_payload_to_file(p3, "3_StatusValidation")

    print("\n--- 4. ReportStore Payload (Test Result Output) ---")
    _, p4 = build_report_store(sample_serial, sample_apo, sample_takt_time, sample_wire_pass, sample_vi_pass, mac)
    print(json.dumps(p4, indent=2))
    save_payload_to_file(p4, "4_ReportStore")

    print("\n" + "="*70)
    print(f"[SUCCESS] All JSON payloads successfully generated and saved to: {OUTPUT_DIR}")
    print("="*70 + "\n")
