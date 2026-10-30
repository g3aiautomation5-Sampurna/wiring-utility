# import os
# import sys
# import re
# import time
# import json
# import uuid
# import random
# import subprocess
# from datetime import datetime

# # CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pms_config.json")

# # For keeping json file out of exe 
# if getattr(sys, "frozen", False):
#     APP_DIR = os.path.dirname(sys.executable)
# else:
#     APP_DIR = os.path.dirname(os.path.abspath(__file__))

# CONFIG_FILE = os.path.join(APP_DIR, "pms_config.json")

# def validate_config_json():
#     """
#     Validate the actual pms_config.json file without modifying it.

#     Checks:
#       1. The file exists and can be read.
#       2. It is valid JSON (reports line/column and the offending line).
#       3. The top level is a JSON object.
#       4. Required settings are present and have usable values.

#     Returns:
#         (True, None) if everything is fine.
#         (False, error_message) otherwise. error_message may span several lines.
#     """
#     try:
#         with open(CONFIG_FILE, "r", encoding="utf-8") as f:
#             raw_text = f.read()
#     except FileNotFoundError:
#         return False, f"pms_config.json was not found.\nExpected location:\n{CONFIG_FILE}"
#     except (OSError, UnicodeError) as e:
#         return False, f"Could not read pms_config.json: {e}"

#     # ---- 1. JSON syntax ----
#     try:
#         config = json.loads(raw_text)
#     except json.JSONDecodeError as e:
#         lines = raw_text.splitlines()
#         context = ""
#         if 1 <= e.lineno <= len(lines):
#             bad_line = lines[e.lineno - 1].strip()
#             if len(bad_line) > 120:
#                 bad_line = bad_line[:120] + "..."
#             context = f"\nLine {e.lineno}: {bad_line}"
#             if e.lineno > 1:
#                 prev_line = lines[e.lineno - 2].strip()
#                 if prev_line:
#                     if len(prev_line) > 120:
#                         prev_line = prev_line[:120] + "..."
#                     context += f"\nPrevious line {e.lineno - 1}: {prev_line}"
#         return False, (
#             f"Invalid JSON at line {e.lineno}, column {e.colno}: {e.msg}"
#             f"{context}\n"
#             "Tip: check for a missing/extra comma, missing quote or bracket."
#         )

#     # ---- 2. Must be an object ----
#     if not isinstance(config, dict):
#         return False, (
#             "pms_config.json must contain a JSON object "
#             "with key-value pairs, e.g. { \"key\": \"value\" }."
#         )

#     # ---- 3. Required settings ----
#     problems = []

#     def _positive_number(key):
#         if key not in config:
#             problems.append(f"Missing required key: {key}")
#             return
#         value = config[key]
#         if isinstance(value, bool):
#             problems.append(f"{key} must be a number greater than 0 (got true/false).")
#             return
#         try:
#             if float(value) <= 0:
#                 problems.append(f"{key} must be greater than 0 (got {value!r}).")
#         except (TypeError, ValueError):
#             problems.append(f"{key} must be a number (got {value!r}).")

#     _positive_number("pmsConnectionTimeout")
#     _positive_number("pmsServerResponseTimeout")

#     if "ValidationStatus" not in config:
#         problems.append("Missing required key: ValidationStatus")
#     else:
#         try:
#             int(config["ValidationStatus"])
#         except (TypeError, ValueError):
#             problems.append(
#                 f"ValidationStatus must be a whole number (got {config['ValidationStatus']!r})."
#             )

#     if "pmsBrokerPort" in config:
#         try:
#             port = int(config["pmsBrokerPort"])
#             if not 1 <= port <= 65535:
#                 problems.append(f"pmsBrokerPort must be between 1 and 65535 (got {port}).")
#         except (TypeError, ValueError):
#             problems.append(
#                 f"pmsBrokerPort must be a whole number (got {config['pmsBrokerPort']!r})."
#             )

#     if problems:
#         return False, "pms_config.json has invalid settings:\n- " + "\n- ".join(problems)

#     return True, None

# OUTPUT_DIR = os.path.join(APP_DIR, "Result", "PMS_Payloads")

# DEFAULT_CONFIG = {
#     "use_mac_as_serial": True,
#     "production_line_no": "1",
#     "jigUid": "CGJIGxxxxxxxxxx00111",
#     "testing_stage": "X_POWER_SUPPLY_4Point3",
#     "slave_version_no": "4.3",
#     "default_apo_number_id": "56",
#     "table_report": "Z_VI_TEST",
#     "table_serial": "K_ALL_SERIAL_NUMBER",
#     "table_status": "E_DEVICE",
#     # "pms_broker_ip": "127.0.0.1",
#     "pms_broker_port": 1883,
#     "pms_connection_timeout": 8,
# }

# def load_or_create_config():
#     """Loads configuration from pms_config.json or creates it with defaults."""
#     if not os.path.exists(CONFIG_FILE):
#         # READ-ONLY MODE: never create or write pms_config.json.
#         print(f"[PMS Config] Warning: {CONFIG_FILE} not found. Using in-memory defaults (file is NOT created).")
#         return DEFAULT_CONFIG.copy()

#     try:
#         with open(CONFIG_FILE, "r", encoding="utf-8") as f:
#             cfg = json.load(f)
#             # Ensure all default keys exist
#             for k, v in DEFAULT_CONFIG.items():
#                 if k not in cfg:
#                     cfg[k] = v
#             return cfg
#     except Exception as e:
#         print(f"[PMS Config] Warning: Could not read {CONFIG_FILE}: {e}")
#         return DEFAULT_CONFIG.copy()



# # Only these keys may be written to pms_config.json. Everything else stays read-only.
# WRITABLE_CONFIG_KEYS = {"jigUid", "plcJigProductionLineNo", "slaveVersionNo"}


# def update_config_value(key, value):
#     """
#     Update ONE whitelisted setting in pms_config.json.

#     The file is read as-is, only that one key is changed, and it is written
#     back. Default values are NOT merged in, so no extra keys get added.
#     Keys not in WRITABLE_CONFIG_KEYS are refused (read-only).
#     """
#     if key not in WRITABLE_CONFIG_KEYS:
#         print(f"[PMS Config] Read-only mode: refused to write '{key}' to {CONFIG_FILE}.")
#         return False

#     temp_file = CONFIG_FILE + ".tmp"

#     try:
#         # Read the raw file (no DEFAULT_CONFIG merge).
#         with open(CONFIG_FILE, "r", encoding="utf-8") as f:
#             config = json.load(f)

#         if not isinstance(config, dict):
#             print("[PMS Config] pms_config.json is not a JSON object; not updating.")
#             return False

#         config[key] = value

#         with open(temp_file, "w", encoding="utf-8") as f:
#             json.dump(config, f, indent=4)

#         # Replace the original only after the temporary file is written.
#         os.replace(temp_file, CONFIG_FILE)
#         return True

#     except Exception as e:
#         print(f"[PMS Config] Error updating '{key}': {e}")
#         try:
#             if os.path.exists(temp_file):
#                 os.remove(temp_file)
#         except OSError:
#             pass
#         return False


# def get_pc_mac_address():
#     """
#     Automatically detects the physical network adapter MAC address on any Windows/Linux/macOS PC.
#     If 'device_mac_override' is set in pms_config.json, it will use that.
#     Returns uppercase colon-formatted MAC: e.g. '38:18:2B:E7:92:F8'.
#     """
#     try:
#         cfg = load_or_create_config()
#         override = (cfg.get("device_mac_override") or "").strip()
#         if override:
#             return override.upper()
#     except Exception:
#         pass

#     # Method 1: On Windows, use 'getmac' command to get active physical adapter
#     if sys.platform.startswith("win"):
#         try:
#             cmd = "getmac /fo csv /nh"
#             output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode(errors="ignore")
#             for line in output.strip().splitlines():
#                 parts = [p.strip(' "') for p in line.split(',')]
#                 if parts and parts[0] and "N/A" not in parts[0] and "Disconnected" not in line:
#                     mac_clean = parts[0].replace('-', ':').upper()
#                     if re.match(r'^([0-9A-F]{2}:){5}[0-9A-F]{2}$', mac_clean):
#                         return mac_clean
#         except Exception:
#             pass

#     # Method 2: Standard cross-platform uuid.getnode()
#     try:
#         node = uuid.getnode()
#         # Verify it's not a temporary/random address (check multicast bit)
#         if not (node >> 40) & 0x01:
#             mac_str = ':'.join(f"{(node >> (8 * i)) & 0xff:02X}" for i in reversed(range(6)))
#             if re.match(r'^([0-9A-F]{2}:){5}[0-9A-F]{2}$', mac_str):
#                 return mac_str
#     except Exception:
#         pass

#     # Fallback to general uuid representation
#     node = uuid.getnode()
#     return ':'.join(f"{(node >> (8 * i)) & 0xff:02X}" for i in reversed(range(6)))

# def get_thinclient_uid():
#     """
#     Fetches the unique Thinclient / Machine Hardware UID that changes from PC to PC.
#     Priority:
#     1. If 'use_mac_as_serial' is set in pms_config.json, uses Device MAC.
#     2. System Hardware UUID (Win32_ComputerSystemProduct.UUID)
#     3. Windows Registry MachineGuid
#     4. BIOS Serial Number
#     5. Fallback: Host MAC Address
#     """
#     try:
#         cfg = load_or_create_config()
#         if cfg.get("useMacAsSerial", False) or str(cfg.get("serialSource", "")).lower() == "mac":
#             return get_pc_mac_address()
#     except Exception:
#         pass

#     if sys.platform.startswith("win"):
#         # 1. System Hardware UUID (Standard Thinclient / OEM UUID)
#         try:
#             res = subprocess.run(
#                 ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_ComputerSystemProduct).UUID"],
#                 capture_output=True, text=True, timeout=3
#             )
#             out = res.stdout.strip()
#             if out and len(out) > 8 and "00000000" not in out and "FFFFFFFF" not in out:
#                 return out
#         except Exception:
#             pass

#         # 2. Windows Registry MachineGuid (Unique per Windows installation)
#         try:
#             import winreg
#             with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
#                 guid, _ = winreg.QueryValueEx(key, "MachineGuid")
#                 if guid and guid.strip():
#                     return guid.strip().upper()
#         except Exception:
#             pass

#         # 3. BIOS Serial Number
#         try:
#             res = subprocess.run(
#                 ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_BIOS).SerialNumber"],
#                 capture_output=True, text=True, timeout=3
#             )
#             out = res.stdout.strip()
#             if out and len(out) > 3 and "Default" not in out and "To be filled" not in out:
#                 return out
#         except Exception:
#             pass

#     # 4. Fallback: Host MAC Address
#     mac = get_pc_mac_address()
#     return mac.replace(":", "").upper()

# # for production
# # def generate_utc_request_id():
# #     """
# #     Generates UtcRequest_ID as specified in document:
# #     13-digit epoch in ms + 19 random digits (e.g. 179101286776517797148103240069120)
# #     """
# #     epoch_ms = str(int(time.time() * 1000))
# #     random_digits = "".join([str(random.randint(0, 9)) for _ in range(19)])
# #     return epoch_ms + random_digits

# # For testing purpose
# def generate_utc_request_id():
#     """
#     Fixed UtcRequest_ID for testing purposes.
#     """
#     return "1234"

# def parse_sticker(scanned_code=None, default_apo=None):
#     """
#     Parses scanned barcode/QR sticker.
#     Expected QR text format: 'Id: ..; Sr: ..;'
#     - 'Id: <apo_number_id>' -> extracted as APoNumberId (e.g. '56')
#     - 'Sr: <device_serial_no>' -> extracted as DeviceSerialNo (e.g. '001260101010122505100002640000142')

#     Also supports:
#     - Delimited format: '56,001260101...' or '56|00126...' -> (apo_id, serial_no)
#     - Plain serial without APO: '00126...' -> (default_apo, serial_no)
#     - Empty / N/A -> (default_apo, thinclient_uid)
#     """
#     if default_apo is None:
#         cfg = load_or_create_config()
#         default_apo = "56"

#     scanned = str(scanned_code).strip() if scanned_code else ""
#     if not scanned or scanned in ["N/A", "None", "", "device"]:
#         return str(default_apo), get_thinclient_uid()

#     # 1. Match explicit Id: ... and/or Sr: ... pattern (case-insensitive)
#     id_match = re.search(r'(?:^|[;,|\r\n\s])\s*(?:APoNumberId|APO(?:_?ID)?|Id)\s*[:=]\s*([^;,|\r\n]+)', scanned, re.IGNORECASE)
#     sr_match = re.search(r'(?:^|[;,|\r\n\s])\s*(?:DeviceSerial(?:No)?|Serial(?:No)?|Sr(?:No)?|SN)\s*[:=]\s*([^;,|\r\n]+)', scanned, re.IGNORECASE)

#     if id_match or sr_match:
#         apo = id_match.group(1).strip() if id_match else str(default_apo)
#         serial = sr_match.group(1).strip() if sr_match else get_thinclient_uid()
#         if not serial:
#             serial = get_thinclient_uid()
#         if not apo:
#             apo = str(default_apo)
#         return apo, serial

#     # 2. Legacy delimited formats (e.g. '56,00126...', '56|00126...')
#     for delimiter in [",", "|", ";", "/"]:
#         if delimiter in scanned:
#             parts = [p.strip() for p in scanned.split(delimiter) if p.strip()]
#             if len(parts) >= 2:
#                 apo = parts[0]
#                 serial = parts[1]
#                 if apo and serial:
#                     return apo, serial
#             elif len(parts) == 1:
#                 return str(default_apo), parts[0]

#     return str(default_apo), scanned

# def build_device_autowhitelisting(mac_id=None):
#     """
#     Builds the DeviceAutoWhitelisting payload.
#     """
#     config = load_or_create_config()
#     if not mac_id:
#         mac_id = get_pc_mac_address()

#     req_id = generate_utc_request_id()
#     payload = {
#         "CmdType": "DeviceAutoWhitelisting",
#         "UtcRequest_ID": req_id,
#         "Device_MAC_ID": mac_id,
#         "TopicToPublish": (
#             f"{config['pmsPublishTopicPrefix'].rstrip('/')}/{mac_id}"
#         ),
#         "TopicToSubscribe": (
#             f"{config['pmsSubscribeTopicPrefix'].rstrip('/')}/{mac_id}"
#         )
#     }
#     return req_id, payload

# def build_serial_no_validation(device_serial_no=None, apo_number_id=None, mac_id=None, testing_stage=None, slave_version=None):
#     """
#     Builds the SerialNoValidation payload.
#     If device_serial_no is not provided, automatically uses the Thinclient UID / MAC.
#     """
#     cfg = load_or_create_config()
#     if not mac_id:
#         mac_id = get_pc_mac_address()

#     # Auto-parse if a full QR string (e.g. 'Id: ..; Sr: ..;') was passed as device_serial_no
#     if device_serial_no and any(k in str(device_serial_no).lower() for k in ["id:", "sr:"]):
#         parsed_apo, parsed_serial = parse_sticker(device_serial_no, default_apo=apo_number_id)
#         if not apo_number_id:
#             apo_number_id = parsed_apo
#         device_serial_no = parsed_serial

#     if not device_serial_no or str(device_serial_no).strip() in ["", "None", "N/A"]:
#         device_serial_no = get_thinclient_uid()
#     if not apo_number_id:
#         apo_number_id = cfg.get("default_apo_number_id", "56")
#     if not testing_stage:
#         testing_stage = cfg.get("testingStage", "X_POWER_SUPPLY_4Point3")
#     if not slave_version:
#         slave_version = cfg.get("slaveVersionNo", "4.3")

#     req_id = generate_utc_request_id()
#     table_serial = cfg.get("tableSerialValidation") or cfg.get("tableSerial", "K_ALL_SERIAL_NUMBER")
#     payload = {
#         "CmdType": "SerialNoValidation",
#         "UtcRequest_ID": req_id,
#         "Device_MAC_ID": mac_id,
#         "TableName": table_serial,
#         "TestingStage": testing_stage,
#         "SlaveVersionNo": slave_version,
#         "ColumnsName": [
#             {
#                 "APoNumberId": str(apo_number_id),
#                 "DeviceSerialNo": str(device_serial_no),
#                 "DevicePrintNo": "",
#                 "PowerSupplySerialNo": "",
#                 "PowerSupplyPrintNo": "",
#                 "DisplaySerialNo": "",
#                 "DisplayPrintNo": "",
#                 "LogicSerialNo": "",
#                 "LogicPrintNo": "",
#                 "RowCreationTimeStamp": "",
#                 "RowUpdationTimeStamp": "",
#                 "KAllSerialNumberId": "",
#                 "LineNo": ""
#             }
#         ]
#     }
#     return req_id, payload

# def build_status_validation(device_serial_no=None, apo_number_id=None, mac_id=None):
#     """
#     Builds the StatusValidation payload (Interlocking check).
#     If device_serial_no is not provided, automatically uses the Thinclient UID / MAC.
#     """
#     cfg = load_or_create_config()
#     # status_check = int(cfg.get("status_check", 1))
#     ValidationStatus = int(cfg["ValidationStatus"])
#     if not mac_id:
#         mac_id = get_pc_mac_address()

#     # Auto-parse if a full QR string (e.g. 'Id: ..; Sr: ..;') was passed as device_serial_no
#     if device_serial_no and any(k in str(device_serial_no).lower() for k in ["id:", "sr:"]):
#         parsed_apo, parsed_serial = parse_sticker(device_serial_no, default_apo=apo_number_id)
#         if not apo_number_id:
#             apo_number_id = parsed_apo
#         device_serial_no = parsed_serial

#     if not device_serial_no or str(device_serial_no).strip() in ["", "None", "N/A"]:
#         device_serial_no = get_thinclient_uid()
#     if not apo_number_id:
#         apo_number_id = cfg.get("default_apo_number_id", "56")

#     req_id = generate_utc_request_id()
#     table_status = cfg.get("tableStatusValidation") or cfg.get("tableStatus", "E_DEVICE")
#     payload = {
#         "CmdType": "StatusValidation",
#         "UtcRequest_ID": req_id,
#         "Device_MAC_ID": mac_id,
#         "ValidationStatus": ValidationStatus,
#         "TableName": table_status,
#         "ColumnsName": [
#             {
#                 "APoNumberId": str(apo_number_id),
#                 "EMainId": "",
#                 "DeviceSerialNo": str(device_serial_no),
#                 "RowCreationTimeStamp": "",
#                 "RowUpdationTimeStamp": "",
#                 "PowerSupplyBoardTest": "",
#                 "LogicBoardTest": "",
#                 "DisplayBoardTest": "",
#                 "PowerOnStageTest": "1",
#                 "HVTest": "1",
#                 "HRTTest": "",
#                 "FunctionalTest": "",
#                 "PackingStage": "",
#                 "ViTest": "",
#                 "LinkingStage": ""
#             }
#         ]
#     }
#     return req_id, payload

# def build_report_store(
#     device_serial_no=None,
#     apo_number_id=None,
#     takt_time=0.0,
#     wire_origin_pass=True,
#     vi_test_pass=True,
#     mac_id=None,
#     line_no=None,
#     jig_uid=None,
#     pv_pass=False,
#     coil_pass=False,
#     ac_cam1_pass=False,
#     ac_cam2_pass=False,
#     pv_case_pass=False,
#     coil_case_pass=False,
#     ac_case_pass=False,
#     inspection_epoch_ms=None
#     ):
#     """
#     Builds the ReportStore payload (Final Test Result) to be stored in table Z_VI_TEST.
#     If device_serial_no is not provided, automatically uses the Thinclient UID / MAC.
#     """
#     cfg = load_or_create_config()
#     if not mac_id:
#         mac_id = get_pc_mac_address()

#     # Auto-parse if a full QR string (e.g. 'Id: ..; Sr: ..;') was passed as device_serial_no
#     if device_serial_no and any(k in str(device_serial_no).lower() for k in ["id:", "sr:"]):
#         parsed_apo, parsed_serial = parse_sticker(device_serial_no, default_apo=apo_number_id)
#         if not apo_number_id:
#             apo_number_id = parsed_apo
#         device_serial_no = parsed_serial

#     if not device_serial_no or str(device_serial_no).strip() in ["", "None", "N/A"]:
#         device_serial_no = get_thinclient_uid()
#     if not apo_number_id:
#         apo_number_id = cfg.get("default_apo_number_id", "56")
#     if not line_no:
#         line_no = cfg.get("plcJigProductionLineNo") or cfg.get("productionLineNo", "1")
#     if not jig_uid:
#         jig_uid = cfg.get("jigUid", "CGJIGxxxxxxxxxx00111")

#     # now = datetime.now()
#     # epoch_ms = int(now.timestamp() * 1000)
#     now = datetime.now()

#     # Use the inspection timestamp if provided; otherwise generate one.
#     epoch_ms = (
#         int(inspection_epoch_ms)
#         if inspection_epoch_ms is not None
#         else int(time.time() * 1000)
#     )
#     req_id = generate_utc_request_id()
#     table_report = cfg.get("tableReportStore") or cfg.get("tableReport", "Z_VI_TEST")

#     payload = {
#         "CmdType": "ReportStore",
#         "UtcRequest_ID": req_id,
#         "Device_MAC_ID": mac_id,
#         "TableName": table_report,
#         "ColumnsName": [
#             {
#                 "APoNumberId": str(apo_number_id),
#                 "RowCreationTimeStamp": epoch_ms,
#                 "RowUpdationTimeStamp": epoch_ms,
#                 "WifiMasterMacid": mac_id,
#                 "WifiDate": now.strftime("%d-%B-%Y, %A"),
#                 "WifiTime": now.strftime("%H:%M:%S"),
#                 "PlcJigProductionLineNo": str(line_no),
#                 "DeviceSerialNo": str(device_serial_no),
#                 "TaktTime": round(float(takt_time), 3),
#                 "JigUid": str(jig_uid),

#                 # Inspection results
#                 "Epoch time": epoch_ms,
#                 "Serial No.": str(device_serial_no),
#                 # "Final_result": "PASS" if vi_test_pass else "FAIL",
#                 "ViInspection": 1 if vi_test_pass else 0,
#                 "PV": 1 if pv_pass else 0,
#                 "Coil": 1 if coil_pass else 0,
#                 "AC1": 1 if ac_cam1_pass else 0,
#                 "AC2": 1 if ac_cam2_pass else 0,

#                 "PvCase": 1 if pv_case_pass else 0,
#                 "CoilCase": 1 if coil_case_pass else 0,
#                 "AcCase": 1 if ac_case_pass else 0,

#                 # Existing PMS fields — keep these
#                 "WireOrigin": 1 if wire_origin_pass else 0,
#                 "ViTest": 1 if vi_test_pass else 0
#             }
#         ]
#     }
#     return req_id, payload

# def build_empty_report_store(device_serial_no="", apo_number_id="", mac_id=""):
#     """
#     Builds the ReportStore template with empty test results.
#     Used before inspection is performed.
#     """
#     cfg = load_or_create_config()
#     table_report = cfg.get("tableReportStore") or cfg.get("tableReport", "Z_VI_TEST")
#     line_no = cfg.get("plcJigProductionLineNo") or cfg.get("productionLineNo", "")
#     jig_uid = cfg.get("jigUid", "")

#     return {
#         "CmdType": "ReportStore",
#         "UtcRequest_ID": "",
#         "Device_MAC_ID": str(mac_id) if mac_id else "",
#         "TableName": table_report,
#         "ColumnsName": [
#             {
#                 "APoNumberId": str(apo_number_id) if apo_number_id else "",
#                 "RowCreationTimeStamp": "",
#                 "RowUpdationTimeStamp": "",
#                 "WifiMasterMacid": str(mac_id) if mac_id else "",
#                 "WifiDate": "",
#                 "WifiTime": "",
#                 "PlcJigProductionLineNo": str(line_no) if line_no else "",
#                 "DeviceSerialNo": str(device_serial_no) if device_serial_no else "",
#                 "TaktTime": "",
#                 "JigUid": str(jig_uid) if jig_uid else "",
#                 "WireOrigin": "",
#                 "ViTest": ""
#             }
#         ]
#     }

# def build_empty_payloads():
#     """
#     Returns all 4 PMS JSON templates where all dynamic and data fields are empty.
#     Used before scanning any barcode and before running any inspection.
#     """
#     cfg = load_or_create_config()
#     table_serial = cfg.get("tableSerialValidation") or cfg.get("tableSerial", "K_ALL_SERIAL_NUMBER")
#     table_status = cfg.get("tableStatusValidation") or cfg.get("tableStatus", "E_DEVICE")
#     table_report = cfg.get("tableReportStore") or cfg.get("tableReport", "Z_VI_TEST")

#     return {
#         "DeviceAutoWhitelisting": {
#             "CmdType": "DeviceAutoWhitelisting",
#             "UtcRequest_ID": "",
#             "Device_MAC_ID": "",
#             "TopicToPublish": "",
#             "TopicToSubscribe": ""
#         },
#         "SerialNoValidation": {
#             "CmdType": "SerialNoValidation",
#             "UtcRequest_ID": "",
#             "Device_MAC_ID": "",
#             "TableName": table_serial,
#             "TestingStage": "",
#             "SlaveVersionNo": "",
#             "ColumnsName": [
#                 {
#                     "APoNumberId": "",
#                     "DeviceSerialNo": "",
#                     "DevicePrintNo": "",
#                     "PowerSupplySerialNo": "",
#                     "PowerSupplyPrintNo": "",
#                     "DisplaySerialNo": "",
#                     "DisplayPrintNo": "",
#                     "LogicSerialNo": "",
#                     "LogicPrintNo": "",
#                     "RowCreationTimeStamp": "",
#                     "RowUpdationTimeStamp": "",
#                     "KAllSerialNumberId": "",
#                     "LineNo": ""
#                 }
#             ]
#         },
#         "StatusValidation": {
#             "CmdType": "StatusValidation",
#             "UtcRequest_ID": "",
#             "Device_MAC_ID": "",
#             "TableName": table_status,
#             "ColumnsName": [
#                 {
#                     "APoNumberId": "",
#                     "EMainId": "",
#                     "DeviceSerialNo": "",
#                     "RowCreationTimeStamp": "",
#                     "RowUpdationTimeStamp": "",
#                     "PowerSupplyBoardTest": "",
#                     "LogicBoardTest": "",
#                     "DisplayBoardTest": "",
#                     "PowerOnStageTest": "",
#                     "HVTest": "",
#                     "HRTTest": "",
#                     "FunctionalTest": "",
#                     "PackingStage": "",
#                     "ViTest": "",
#                     "LinkingStage": ""
#                 }
#             ]
#         },
#         "ReportStore": {
#             "CmdType": "ReportStore",
#             "UtcRequest_ID": "",
#             "Device_MAC_ID": "",
#             "TableName": table_report,
#             "ColumnsName": [
#                 {
#                     "APoNumberId": "",
#                     "RowCreationTimeStamp": "",
#                     "RowUpdationTimeStamp": "",
#                     "WifiMasterMacid": "",
#                     "WifiDate": "",
#                     "WifiTime": "",
#                     "PlcJigProductionLineNo": "",
#                     "DeviceSerialNo": "",
#                     "TaktTime": "",
#                     "JigUid": "",
#                     "WireOrigin": "",
#                     "ViTest": ""
#                 }
#             ]
#         }
#     }

# def get_all_payloads(device_serial_no=None, apo_number_id=None, takt_time=0.0, wire_origin_pass=True, vi_test_pass=True, mac_id=None):
#     """
#     Returns all 4 required PMS payloads in one call.
#     """
#     if not mac_id:
#         mac_id = get_pc_mac_address()

#     # Auto-parse if a full QR string (e.g. 'Id: ..; Sr: ..;') was passed as device_serial_no
#     if device_serial_no and any(k in str(device_serial_no).lower() for k in ["id:", "sr:"]):
#         parsed_apo, parsed_serial = parse_sticker(device_serial_no, default_apo=apo_number_id)
#         if not apo_number_id:
#             apo_number_id = parsed_apo
#         device_serial_no = parsed_serial

#     if not device_serial_no or str(device_serial_no).strip() in ["", "None", "N/A"]:
#         device_serial_no = get_thinclient_uid()
#     if not apo_number_id:
#         cfg = load_or_create_config()
#         apo_number_id = cfg.get("default_apo_number_id", "56")
    
#     _, p1 = build_device_autowhitelisting(mac_id)
#     _, p2 = build_serial_no_validation(device_serial_no, apo_number_id, mac_id)
#     _, p3 = build_status_validation(device_serial_no, apo_number_id, mac_id)
#     _, p4 = build_report_store(device_serial_no, apo_number_id, takt_time, wire_origin_pass, vi_test_pass, mac_id)

#     return {
#         "mac_address": mac_id,
#         "device_serial_no": device_serial_no,
#         "apo_number_id": apo_number_id,
#         "DeviceAutoWhitelisting": p1,
#         "SerialNoValidation": p2,
#         "StatusValidation": p3,
#         "ReportStore": p4
#     }

# def save_payload_to_file(payload, name_prefix="payload"):
#     """
#     Saves a payload JSON to Result/PMS_Payloads/<prefix>_<timestamp>.json
#     """
#     os.makedirs(OUTPUT_DIR, exist_ok=True)
#     ts = datetime.now().strftime("%Y%m%d_%H%M%S")
#     filepath = os.path.join(OUTPUT_DIR, f"{name_prefix}_{ts}.json")
#     with open(filepath, "w", encoding="utf-8") as f:
#         json.dump(payload, f, indent=4)
#     return filepath

# if __name__ == "__main__":
#     print("\n" + "="*70)
#     print("SELEC CONTROLS - PMS JSON OUTPUT GENERATOR")
#     print("="*70)
    
#     mac = get_pc_mac_address()
#     print(f"[*] Detected Machine Physical MAC Address: {mac}")
    
#     cfg = load_or_create_config()
#     print(f"[*] Loaded Configuration: {json.dumps(cfg, indent=2)}")
    
#     # Uniform PC Identification: Use MAC Address as Serial No
#     sample_serial = get_thinclient_uid()
#     sample_apo = "56"
#     sample_takt_time = 41.272
#     sample_wire_pass = True
#     sample_vi_pass = True

#     print("\n--- 1. DeviceAutoWhitelisting Payload ---")
#     _, p1 = build_device_autowhitelisting(mac)
#     print(json.dumps(p1, indent=2))
#     save_payload_to_file(p1, "1_DeviceAutoWhitelisting")

#     print("\n--- 2. SerialNoValidation Payload ---")
#     _, p2 = build_serial_no_validation(sample_serial, sample_apo, mac)
#     print(json.dumps(p2, indent=2))
#     save_payload_to_file(p2, "2_SerialNoValidation")

#     print("\n--- 3. StatusValidation Payload ---")
#     _, p3 = build_status_validation(sample_serial, sample_apo, mac)
#     print(json.dumps(p3, indent=2))
#     save_payload_to_file(p3, "3_StatusValidation")

#     print("\n--- 4. ReportStore Payload (Test Result Output) ---")
#     _, p4 = build_report_store(sample_serial, sample_apo, sample_takt_time, sample_wire_pass, sample_vi_pass, mac)
#     print(json.dumps(p4, indent=2))
#     save_payload_to_file(p4, "4_ReportStore")

#     print("\n" + "="*70)
#     print(f"[SUCCESS] All JSON payloads successfully generated and saved to: {OUTPUT_DIR}")
#     print("="*70 + "\n")

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

def validate_config_json():
    """
    Validate the actual pms_config.json file without modifying it.

    Checks:
      1. The file exists and can be read.
      2. It is valid JSON (reports line/column and the offending line).
      3. The top level is a JSON object.
      4. Required settings are present and have usable values.

    Returns:
        (True, None) if everything is fine.
        (False, error_message) otherwise. error_message may span several lines.
    """
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            raw_text = f.read()
    except FileNotFoundError:
        return False, f"pms_config.json was not found.\nExpected location:\n{CONFIG_FILE}"
    except (OSError, UnicodeError) as e:
        return False, f"Could not read pms_config.json: {e}"

    # ---- 1. JSON syntax ----
    try:
        config = json.loads(raw_text)
    except json.JSONDecodeError as e:
        lines = raw_text.splitlines()
        context = ""
        if 1 <= e.lineno <= len(lines):
            bad_line = lines[e.lineno - 1].strip()
            if len(bad_line) > 120:
                bad_line = bad_line[:120] + "..."
            context = f"\nLine {e.lineno}: {bad_line}"
            if e.lineno > 1:
                prev_line = lines[e.lineno - 2].strip()
                if prev_line:
                    if len(prev_line) > 120:
                        prev_line = prev_line[:120] + "..."
                    context += f"\nPrevious line {e.lineno - 1}: {prev_line}"
        return False, (
            f"Invalid JSON at line {e.lineno}, column {e.colno}: {e.msg}"
            f"{context}\n"
            "Tip: check for a missing/extra comma, missing quote or bracket."
        )

    # ---- 2. Must be an object ----
    if not isinstance(config, dict):
        return False, (
            "pms_config.json must contain a JSON object "
            "with key-value pairs, e.g. { \"key\": \"value\" }."
        )

    # ---- 3. Required settings ----
    problems = []

    def _positive_number(key):
        if key not in config:
            problems.append(f"Missing required key: {key}")
            return
        value = config[key]
        if isinstance(value, bool):
            problems.append(f"{key} must be a number greater than 0 (got true/false).")
            return
        try:
            if float(value) <= 0:
                problems.append(f"{key} must be greater than 0 (got {value!r}).")
        except (TypeError, ValueError):
            problems.append(f"{key} must be a number (got {value!r}).")

    _positive_number("pmsConnectionTimeout")
    _positive_number("pmsServerResponseTimeout")

    if "ValidationStatus" not in config:
        problems.append("Missing required key: ValidationStatus")
    else:
        try:
            int(config["ValidationStatus"])
        except (TypeError, ValueError):
            problems.append(
                f"ValidationStatus must be a whole number (got {config['ValidationStatus']!r})."
            )

    for _key in ("pmsPublishTopicPrefix", "pmsSubscribeTopicPrefix"):
        if _key not in config:
            problems.append(f"Missing required key: {_key}")
        elif not isinstance(config[_key], str) or not config[_key].strip():
            problems.append(f"{_key} must be a non-empty text value (got {config[_key]!r}).")

    if "pmsBrokerPort" in config:
        try:
            port = int(config["pmsBrokerPort"])
            if not 1 <= port <= 65535:
                problems.append(f"pmsBrokerPort must be between 1 and 65535 (got {port}).")
        except (TypeError, ValueError):
            problems.append(
                f"pmsBrokerPort must be a whole number (got {config['pmsBrokerPort']!r})."
            )

    if problems:
        return False, "pms_config.json has invalid settings:\n- " + "\n- ".join(problems)

    return True, None

OUTPUT_DIR = os.path.join(APP_DIR, "Result", "PMS_Payloads")

DEFAULT_CONFIG = {
    "use_mac_as_serial": True,
    "production_line_no": "1",
    "jigUid": "CGJIGxxxxxxxxxx00111",
    "testing_stage": "X_POWER_SUPPLY_4Point3",
    "slave_version_no": "4.3",
    "default_apo_number_id": "56",
    "table_report": "Z_VI_TEST",
    "table_serial": "K_ALL_SERIAL_NUMBER",
    "table_status": "E_DEVICE",
    # "pms_broker_ip": "127.0.0.1",
    "pms_broker_port": 1883,
    "pms_connection_timeout": 8,
}

def load_or_create_config():
    """Loads configuration from pms_config.json or creates it with defaults."""
    if not os.path.exists(CONFIG_FILE):
        # READ-ONLY MODE: never create or write pms_config.json.
        print(f"[PMS Config] Warning: {CONFIG_FILE} not found. Using in-memory defaults (file is NOT created).")
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



# Only these keys may be written to pms_config.json. Everything else stays read-only.
WRITABLE_CONFIG_KEYS = {"jigUid", "plcJigProductionLineNo", "slaveVersionNo"}


def update_config_value(key, value):
    """
    Update ONE whitelisted setting in pms_config.json.

    The file is read as-is, only that one key is changed, and it is written
    back. Default values are NOT merged in, so no extra keys get added.
    Keys not in WRITABLE_CONFIG_KEYS are refused (read-only).
    """
    if key not in WRITABLE_CONFIG_KEYS:
        print(f"[PMS Config] Read-only mode: refused to write '{key}' to {CONFIG_FILE}.")
        return False

    temp_file = CONFIG_FILE + ".tmp"

    try:
        # Read the raw file (no DEFAULT_CONFIG merge).
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)

        if not isinstance(config, dict):
            print("[PMS Config] pms_config.json is not a JSON object; not updating.")
            return False

        config[key] = value

        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)

        # Replace the original only after the temporary file is written.
        os.replace(temp_file, CONFIG_FILE)
        return True

    except Exception as e:
        print(f"[PMS Config] Error updating '{key}': {e}")
        try:
            if os.path.exists(temp_file):
                os.remove(temp_file)
        except OSError:
            pass
        return False


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
        if cfg.get("useMacAsSerial", False) or str(cfg.get("serialSource", "")).lower() == "mac":
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

# for production
# def generate_utc_request_id():
#     """
#     Generates UtcRequest_ID as specified in document:
#     13-digit epoch in ms + 19 random digits (e.g. 179101286776517797148103240069120)
#     """
#     epoch_ms = str(int(time.time() * 1000))
#     random_digits = "".join([str(random.randint(0, 9)) for _ in range(19)])
#     return epoch_ms + random_digits

# For testing purpose
def generate_utc_request_id():
    """
    Fixed UtcRequest_ID for testing purposes.
    """
    return "1234"

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
        default_apo = "56"

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
            f"{config['pmsPublishTopicPrefix'].rstrip('/')}/{mac_id}"
        ),
        "TopicToSubscribe": (
            f"{config['pmsSubscribeTopicPrefix'].rstrip('/')}/{mac_id}"
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
        testing_stage = cfg.get("testingStage", "X_POWER_SUPPLY_4Point3")
    if not slave_version:
        slave_version = cfg.get("slaveVersionNo", "4.3")

    req_id = generate_utc_request_id()
    table_serial = cfg.get("tableSerialValidation") or cfg.get("tableSerial", "K_ALL_SERIAL_NUMBER")
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
    # status_check = int(cfg.get("status_check", 1))
    ValidationStatus = int(cfg["ValidationStatus"])
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
    table_status = cfg.get("tableStatusValidation") or cfg.get("tableStatus", "E_DEVICE")
    payload = {
        "CmdType": "StatusValidation",
        "UtcRequest_ID": req_id,
        "Device_MAC_ID": mac_id,
        "ValidationStatus": ValidationStatus,
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

def build_report_store(
    device_serial_no=None,
    apo_number_id=None,
    takt_time=0.0,
    wire_origin_pass=True,
    vi_test_pass=True,
    mac_id=None,
    line_no=None,
    jig_uid=None,
    pv_pass=False,
    coil_pass=False,
    ac_cam1_pass=False,
    ac_cam2_pass=False,
    pv_case_pass=False,
    coil_case_pass=False,
    ac_case_pass=False,
    inspection_epoch_ms=None
    ):
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
        line_no = cfg.get("plcJigProductionLineNo") or cfg.get("productionLineNo", "1")
    if not jig_uid:
        jig_uid = cfg.get("jigUid", "CGJIGxxxxxxxxxx00111")

    # now = datetime.now()
    # epoch_ms = int(now.timestamp() * 1000)
    now = datetime.now()

    # Use the inspection timestamp if provided; otherwise generate one.
    epoch_ms = (
        int(inspection_epoch_ms)
        if inspection_epoch_ms is not None
        else int(time.time() * 1000)
    )
    req_id = generate_utc_request_id()
    table_report = cfg.get("tableReportStore") or cfg.get("tableReport", "Z_VI_TEST")

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

                # Inspection results
                # "Serial No.": str(device_serial_no),
                # "Final_result": "PASS" if vi_test_pass else "FAIL",
                "wiringtInspection": 1 if vi_test_pass else 0,
                "PV": 1 if pv_pass else 0,
                "Coil": 1 if coil_pass else 0,
                "AC1": 1 if ac_cam1_pass else 0,
                "AC2": 1 if ac_cam2_pass else 0,

                "PvCase": 1 if pv_case_pass else 0,
                "CoilCase": 1 if coil_case_pass else 0,
                "AcCase": 1 if ac_case_pass else 0,

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
    table_report = cfg.get("tableReportStore") or cfg.get("tableReport", "Z_VI_TEST")
    line_no = cfg.get("plcJigProductionLineNo") or cfg.get("productionLineNo", "")
    jig_uid = cfg.get("jigUid", "")

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
    table_serial = cfg.get("tableSerialValidation") or cfg.get("tableSerial", "K_ALL_SERIAL_NUMBER")
    table_status = cfg.get("tableStatusValidation") or cfg.get("tableStatus", "E_DEVICE")
    table_report = cfg.get("tableReportStore") or cfg.get("tableReport", "Z_VI_TEST")

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