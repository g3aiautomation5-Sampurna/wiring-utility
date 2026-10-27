"""
================================================================================
SELEC CONTROLS - PMS MQTT SERVER SIMULATOR (STANDALONE)
================================================================================
Simulates the Selec PMS MQTT Broker and Backend Server locally on 127.0.0.1:1883.

Features:
1. Zero External Dependencies: Pure Python socket-based MQTT 3.1.1 broker.
2. Complete PMS Protocol Support:
   - DeviceAutoWhitelisting
   - SerialNoValidation
   - StatusValidation
   - ReportStore (Final Test Result)
3. Dynamic Request/Response Matching:
   - Matches incoming UtcRequest_ID exactly
   - Dispatches matching ResponseFromServer with RequestStatus:
     "CONFIG SUCCESSFUL" (for startup validations)
     "DATA SAVED SUCCESSFULLY" (for ReportStore)
4. Configurable Server Timeout & Response Latency:
   - Reads client timeout setting from pms_config.json ("pms_server_timeout")
   - Supports configurable response delay / latency (CLI --delay or interactive 'd <sec>')
   - Supports simulated timeout mode (drops packets or delays beyond timeout to test client error handling)
5. Automatic Configuration Switch:
   - Temporarily sets pms_broker_ip to 127.0.0.1 in pms_config.json on startup
   - Automatically restores the original broker IP upon shutdown (Ctrl+C / exit)
6. Real-time Terminal Visualizer:
   - Displays all received JSON payloads and sent server responses with full detail.

Usage:
    python mock_pms_server.py
    python mock_pms_server.py --delay 5.0
    python mock_pms_server.py --mode timeout
================================================================================
"""

import sys
import os
import socket
import select
import threading
import json
import time
import struct
import atexit
import signal
from datetime import datetime

# Safe UTF-8 reconfiguration for Windows console
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# Enable ANSI colors on Windows terminals
if os.name == 'nt':
    os.system('')

# ANSI Colors
CLR_RESET   = "\033[0m"
CLR_BOLD    = "\033[1m"
CLR_DIM     = "\033[2m"
CLR_RED     = "\033[91m"
CLR_GREEN   = "\033[92m"
CLR_YELLOW  = "\033[93m"
CLR_BLUE    = "\033[94m"
CLR_MAGENTA = "\033[95m"
CLR_CYAN    = "\033[96m"
CLR_WHITE   = "\033[97m"
BG_BLUE     = "\033[44m"
BG_GREEN    = "\033[42m"
BG_RED      = "\033[41m"

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pms_config.json")
BACKUP_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".pms_config.backup.json")

# Simulation mode state: 'success', 'failure', 'timeout', 'delayed'
SIM_MODE = "success"
SIM_RESPONSE_DELAY = 0.025  # seconds

# Stats
STATS = {
    "connections": 0,
    "requests_received": 0,
    "responses_sent": 0,
    "by_cmd": {}
}


def get_configured_client_timeout() -> float:
    """Reads the active client validation timeout from pms_config.json."""
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                return float(cfg.get("pms_server_timeout", cfg.get("pms_validation_timeout", 10.0)))
    except Exception:
        pass
    return 10.0


# ==============================================================================
# CONFIGURATION SWITCHER & AUTO-RESTORATION
# ==============================================================================

ORIGINAL_BROKER_IP = None

def setup_config_redirection():
    """Temporarily update pms_config.json to 127.0.0.1 so web_wiring connects here."""
    global ORIGINAL_BROKER_IP
    if not os.path.exists(CONFIG_PATH):
        return

    try:
        # If backup file already exists from a prior run, read true original IP from it
        if os.path.exists(BACKUP_CONFIG_PATH):
            try:
                with open(BACKUP_CONFIG_PATH, "r", encoding="utf-8") as bf:
                    b_cfg = json.load(bf)
                ORIGINAL_BROKER_IP = b_cfg.get("pms_broker_ip", "192.168.1.100")
            except Exception:
                pass

        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        current_ip = cfg.get("pms_broker_ip", "192.168.1.100")
        if not ORIGINAL_BROKER_IP and current_ip != "127.0.0.1":
            ORIGINAL_BROKER_IP = current_ip

        if current_ip != "127.0.0.1":
            with open(BACKUP_CONFIG_PATH, "w", encoding="utf-8") as bf:
                json.dump(cfg, bf, indent=4)
            cfg["pms_broker_ip"] = "127.0.0.1"
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=4)
            print(f"{CLR_YELLOW}[CONFIG AUTO-SWITCH]{CLR_RESET} Updated pms_config.json broker IP from {CLR_BOLD}{ORIGINAL_BROKER_IP}{CLR_RESET} -> {CLR_GREEN}{CLR_BOLD}127.0.0.1{CLR_RESET}")
            print(f"{CLR_DIM}                     (Original IP will be restored automatically on shutdown){CLR_RESET}\n")
        else:
            print(f"{CLR_GREEN}[CONFIG]{CLR_RESET} pms_config.json broker IP is set to 127.0.0.1 (Original IP to restore: {ORIGINAL_BROKER_IP or '192.168.1.100'})\n")
    except Exception as e:
        print(f"{CLR_RED}[CONFIG WARNING]{CLR_RESET} Could not auto-switch pms_config.json: {e}")

def restore_config():
    """Restore original pms_broker_ip when mock server shuts down."""
    global ORIGINAL_BROKER_IP
    target_ip = ORIGINAL_BROKER_IP
    if not target_ip and os.path.exists(BACKUP_CONFIG_PATH):
        try:
            with open(BACKUP_CONFIG_PATH, "r", encoding="utf-8") as bf:
                b_cfg = json.load(bf)
            target_ip = b_cfg.get("pms_broker_ip", "192.168.1.100")
        except Exception:
            pass

    if not target_ip or target_ip == "127.0.0.1":
        target_ip = "192.168.1.100"

    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            cfg["pms_broker_ip"] = target_ip
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=4)
            print(f"\n{CLR_GREEN}[CONFIG RESTORED]{CLR_RESET} Restored pms_broker_ip back to {CLR_BOLD}{target_ip}{CLR_RESET}")

        if os.path.exists(BACKUP_CONFIG_PATH):
            os.remove(BACKUP_CONFIG_PATH)
    except Exception as e:
        print(f"\n{CLR_RED}[CONFIG RESTORE ERROR]{CLR_RESET} Failed to restore pms_config.json: {e}")

atexit.register(restore_config)

def handle_signal(sig, frame):
    restore_config()
    print(f"\n{CLR_YELLOW}PMS Simulation Server stopped cleanly.{CLR_RESET}")
    sys.exit(0)

signal.signal(signal.SIGINT, handle_signal)
try:
    signal.signal(signal.SIGTERM, handle_signal)
except Exception:
    pass


# ==============================================================================
# MQTT 3.1.1 PACKET ENCODING / DECODING
# ==============================================================================

def encode_remaining_length(length: int) -> bytearray:
    encoded = bytearray()
    while True:
        digit = length % 128
        length //= 128
        if length > 0:
            digit |= 0x80
        encoded.append(digit)
        if length == 0:
            break
    return encoded

def read_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionResetError("Connection closed while reading packet.")
        buf.extend(chunk)
    return bytes(buf)

def decode_remaining_length(sock: socket.socket) -> int:
    multiplier = 1
    value = 0
    while True:
        b = read_exact(sock, 1)[0]
        value += (b & 127) * multiplier
        if (b & 128) == 0:
            break
        multiplier *= 128
    return value

def build_publish_packet(topic: str, payload_bytes: bytes, qos=0, packet_id=1) -> bytes:
    fixed_header = 0x30
    if qos == 1:
        fixed_header = 0x32
    topic_bytes = topic.encode("utf-8")
    var_header = bytearray()
    var_header.extend(struct.pack("!H", len(topic_bytes)))
    var_header.extend(topic_bytes)
    if qos > 0:
        var_header.extend(struct.pack("!H", packet_id))
    body = var_header + payload_bytes
    return bytes(bytearray([fixed_header]) + encode_remaining_length(len(body)) + body)


# ==============================================================================
# MQTT CLIENT SESSION & DISPATCHER
# ==============================================================================

class ClientSession:
    def __init__(self, sock: socket.socket, addr):
        self.sock = sock
        self.addr = addr
        self.client_id = f"{addr[0]}:{addr[1]}"
        self.subscriptions = set()
        self.packet_id_seq = 1

    def send(self, data: bytes):
        try:
            self.sock.sendall(data)
        except Exception:
            pass

    def next_packet_id(self) -> int:
        self.packet_id_seq = (self.packet_id_seq % 65535) + 1
        return self.packet_id_seq


class MockPMSServer:
    def __init__(self, host="0.0.0.0", port=1883):
        self.host = host
        self.port = port
        self.server_sock = None
        self.clients = []
        self.lock = threading.Lock()
        self.running = False

    def start(self):
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind((self.host, self.port))
        self.server_sock.listen(15)
        self.running = True

        client_timeout = get_configured_client_timeout()

        print(f"{CLR_CYAN}{'=' * 78}{CLR_RESET}")
        print(f"{CLR_BOLD}{CLR_WHITE}   SELEC CONTROLS - PMS MQTT SERVER SIMULATOR (LOCAL 127.0.0.1:1883){CLR_RESET}")
        print(f"{CLR_CYAN}{'=' * 78}{CLR_RESET}")
        print(f" * {CLR_BOLD}Listening on{CLR_RESET}               : {CLR_GREEN}{self.host}:{self.port}{CLR_RESET}")
        print(f" * {CLR_BOLD}Simulated Topics{CLR_RESET}           : Subscribes on {CLR_CYAN}SELEC/PMS/SUB/G7/<MAC>{CLR_RESET}")
        print(f"                                Publishes on  {CLR_GREEN}SELEC/PMS/PUB/G7/<MAC>{CLR_RESET}")
        print(f" * {CLR_BOLD}Configured Client Timeout{CLR_RESET}  : {CLR_YELLOW}{CLR_BOLD}{client_timeout:g} seconds{CLR_RESET} (from pms_config.json: pms_server_timeout)")
        print(f" * {CLR_BOLD}Simulated Response Delay{CLR_RESET}   : {CLR_WHITE}{SIM_RESPONSE_DELAY:g} seconds{CLR_RESET}")
        print(f" * {CLR_BOLD}Current Response Mode{CLR_RESET}      : {CLR_GREEN}{CLR_BOLD}{SIM_MODE.upper()}{CLR_RESET}")
        print(f" * {CLR_BOLD}Interactive Commands{CLR_RESET}       :")
        print(f"     [s]             -> Success Mode (CONFIG SUCCESSFUL)")
        print(f"     [f]             -> Failure Mode (CONFIG REJECTED)")
        print(f"     [t]             -> Timeout Mode (Drop packets, trigger client timeout)")
        print(f"     [t <seconds>]   -> Delay response by N seconds (e.g. 't 12' to trigger 10s timeout)")
        print(f"     [d <seconds>]   -> Set Response Latency (e.g. 'd 1.5' or 'd 12')")
        print(f"     [status]        -> View current settings and statistics")
        print(f"{CLR_CYAN}{'=' * 78}{CLR_RESET}\n")

        # Start keyboard listener in background if interactive terminal
        if sys.stdin and hasattr(sys.stdin, 'isatty') and sys.stdin.isatty():
            t_key = threading.Thread(target=self._interactive_keyboard_loop, daemon=True)
            t_key.start()

        while self.running:
            try:
                sock, addr = self.server_sock.accept()
                session = ClientSession(sock, addr)
                with self.lock:
                    self.clients.append(session)
                STATS["connections"] += 1
                t = threading.Thread(target=self._client_handler, args=(session,), daemon=True)
                t.start()
            except Exception as e:
                if self.running:
                    print(f"{CLR_RED}[SERVER ERROR]{CLR_RESET} accept(): {e}")
                break

    def _interactive_keyboard_loop(self):
        """Allows toggling response mode & setting server response timeout/delay dynamically."""
        global SIM_MODE, SIM_RESPONSE_DELAY
        while self.running:
            try:
                line = sys.stdin.readline()
                if not line:
                    break
                parts = line.strip().split()
                if not parts:
                    continue
                cmd = parts[0].lower()

                if cmd in ('s', 'success'):
                    SIM_MODE = "success"
                    SIM_RESPONSE_DELAY = 0.025
                    print(f"\n{BG_GREEN}{CLR_WHITE} >>> MODE CHANGED: AUTO-RESPOND 'CONFIG SUCCESSFUL' (Latency: 25ms) <<< {CLR_RESET}\n")

                elif cmd in ('f', 'fail', 'failure'):
                    SIM_MODE = "failure"
                    SIM_RESPONSE_DELAY = 0.025
                    print(f"\n{BG_RED}{CLR_WHITE} >>> MODE CHANGED: AUTO-RESPOND 'CONFIG REJECTED' <<< {CLR_RESET}\n")

                elif cmd in ('t', 'timeout'):
                    if len(parts) > 1 and parts[1].replace('.', '', 1).isdigit():
                        delay = float(parts[1])
                        SIM_MODE = "delayed"
                        SIM_RESPONSE_DELAY = delay
                        client_timeout = get_configured_client_timeout()
                        print(f"\n{CLR_YELLOW} >>> SIMULATING RESPONSE DELAY: {delay:g}s <<< {CLR_RESET}")
                        if delay >= client_timeout:
                            print(f"{CLR_YELLOW}     [!] Delay ({delay:g}s) >= client timeout ({client_timeout:g}s): Thinclient WILL time out!{CLR_RESET}\n")
                        else:
                            print(f"{CLR_GREEN}     Delay ({delay:g}s) < client timeout ({client_timeout:g}s): Thinclient will succeed after delay.{CLR_RESET}\n")
                    else:
                        SIM_MODE = "timeout"
                        print(f"\n{CLR_YELLOW} >>> MODE CHANGED: TIMEOUT (Packets dropped, no response sent) <<< {CLR_RESET}\n")

                elif cmd in ('d', 'delay'):
                    if len(parts) > 1 and parts[1].replace('.', '', 1).isdigit():
                        SIM_RESPONSE_DELAY = float(parts[1])
                        SIM_MODE = "delayed" if SIM_RESPONSE_DELAY >= 1.0 else "success"
                        print(f"\n{CLR_YELLOW} >>> RESPONSE DELAY SET TO: {SIM_RESPONSE_DELAY:g}s <<< {CLR_RESET}\n")
                    else:
                        print(f"{CLR_YELLOW}Usage: d <seconds> (e.g. 'd 5' or 'd 12'){CLR_RESET}")

                elif cmd == 'status':
                    self.print_stats()
            except Exception:
                break

    def print_stats(self):
        client_timeout = get_configured_client_timeout()
        print(f"\n{CLR_BOLD}--- SIMULATION SETTINGS & STATISTICS ---{CLR_RESET}")
        print(f" Configured Client Timeout : {client_timeout:g} seconds (from pms_config.json: pms_server_timeout)")
        print(f" Simulated Response Delay  : {SIM_RESPONSE_DELAY:g} seconds")
        print(f" Current Response Mode     : {SIM_MODE.upper()}")
        print(f" Total Connections         : {STATS['connections']}")
        print(f" Payloads Received         : {STATS['requests_received']}")
        print(f" Responses Sent            : {STATS['responses_sent']}")
        print(f" Breakdown by Command      : {json.dumps(STATS['by_cmd'], indent=2)}\n")

    def _client_handler(self, session: ClientSession):
        sock = session.sock
        addr = session.addr
        try:
            while self.running:
                first_byte = sock.recv(1)
                if not first_byte:
                    break
                packet_type = (first_byte[0] >> 4) & 0x0F
                flags = first_byte[0] & 0x0F
                rem_len = decode_remaining_length(sock)
                payload = read_exact(sock, rem_len)

                # 1. CONNECT (Type 1)
                if packet_type == 1:
                    try:
                        proto_len = struct.unpack("!H", payload[0:2])[0]
                        offset = 2 + proto_len + 1 + 1 + 2 # proto + level + flags + keepalive
                        cid_len = struct.unpack("!H", payload[offset:offset+2])[0]
                        session.client_id = payload[offset+2:offset+2+cid_len].decode('utf-8', errors='ignore')
                    except Exception:
                        pass

                    print(f"{CLR_GREEN}[+] [CONNECT]{CLR_RESET} Client connected: {CLR_BOLD}{session.client_id}{CLR_RESET} ({addr[0]}:{addr[1]})")
                    session.send(bytes([0x20, 0x02, 0x00, 0x00]))

                # 2. SUBSCRIBE (Type 8)
                elif packet_type == 8:
                    packet_id = struct.unpack("!H", payload[0:2])[0]
                    offset = 2
                    granted_qos = []
                    while offset < len(payload):
                        t_len = struct.unpack("!H", payload[offset:offset+2])[0]
                        offset += 2
                        sub_topic = payload[offset:offset+t_len].decode('utf-8', errors='ignore')
                        offset += t_len
                        req_qos = payload[offset]
                        offset += 1
                        session.subscriptions.add(sub_topic)
                        granted_qos.append(req_qos)
                        print(f"{CLR_CYAN}[+] [SUBSCRIBE]{CLR_RESET} Client {CLR_BOLD}{session.client_id}{CLR_RESET} subscribed to: {CLR_WHITE}{sub_topic}{CLR_RESET} (QoS {req_qos})")

                    suback = bytearray([0x90, 2 + len(granted_qos)])
                    suback.extend(struct.pack("!H", packet_id))
                    suback.extend(granted_qos)
                    session.send(bytes(suback))

                # 3. PUBLISH (Type 3)
                elif packet_type == 3:
                    qos = (flags >> 1) & 0x03
                    offset = 0
                    t_len = struct.unpack("!H", payload[offset:offset+2])[0]
                    offset += 2
                    pub_topic = payload[offset:offset+t_len].decode('utf-8', errors='ignore')
                    offset += t_len

                    pub_packet_id = None
                    if qos > 0:
                        pub_packet_id = struct.unpack("!H", payload[offset:offset+2])[0]
                        offset += 2

                    msg_bytes = payload[offset:]

                    if qos == 1 and pub_packet_id is not None:
                        puback = bytearray([0x40, 0x02])
                        puback.extend(struct.pack("!H", pub_packet_id))
                        session.send(bytes(puback))

                    self._handle_pms_publish(session, pub_topic, msg_bytes)

                # 4. PINGREQ (Type 12)
                elif packet_type == 12:
                    session.send(bytes([0xD0, 0x00]))

                # 5. DISCONNECT (Type 14)
                elif packet_type == 14:
                    print(f"{CLR_YELLOW}[DISCONNECT]{CLR_RESET} Client {session.client_id} sent DISCONNECT.")
                    break

        except (ConnectionResetError, BrokenPipeError):
            pass
        except Exception as e:
            print(f"{CLR_DIM}[CLIENT DISCONNECTED]{CLR_RESET} {session.client_id}: {e}")
        finally:
            with self.lock:
                if session in self.clients:
                    self.clients.remove(session)
            try:
                sock.close()
            except Exception:
                pass
            print(f"{CLR_YELLOW}[-] [CLOSED]{CLR_RESET} Connection ended for {session.client_id}")

    def _handle_pms_publish(self, sender_session: ClientSession, topic: str, msg_bytes: bytes):
        """Processes the received PMS payload and dispatches a matching response."""
        STATS["requests_received"] += 1
        raw_text = msg_bytes.decode('utf-8', errors='ignore')

        try:
            req_data = json.loads(raw_text)
        except Exception:
            print(f"{CLR_RED}[INVALID JSON RECEIVED]{CLR_RESET} on {topic}: {raw_text[:200]}")
            return

        cmd_type = req_data.get("CmdType", "UnknownCommand")
        utc_request_id = str(req_data.get("UtcRequest_ID", "")).strip()
        mac_id = req_data.get("Device_MacID", "")
        serial_no = req_data.get("DeviceSerialNo", "")
        apo_id = req_data.get("APoNumberId", "")

        STATS["by_cmd"][cmd_type] = STATS["by_cmd"].get(cmd_type, 0) + 1

        print(f"\n{CLR_CYAN}{'=' * 78}{CLR_RESET}")
        print(f"{BG_BLUE}{CLR_WHITE} >>> [PMS INCOMING REQUEST #{STATS['requests_received']}] {CLR_RESET} {CLR_BOLD}CmdType: {cmd_type}{CLR_RESET}")
        print(f"{CLR_CYAN}{'-' * 78}{CLR_RESET}")
        print(f" * {CLR_BOLD}Publish Topic{CLR_RESET}   : {CLR_WHITE}{topic}{CLR_RESET}")
        print(f" * {CLR_BOLD}UtcRequest_ID{CLR_RESET}   : {CLR_YELLOW}{utc_request_id}{CLR_RESET}")
        if mac_id:
            print(f" * {CLR_BOLD}Device_MacID{CLR_RESET}    : {mac_id}")
        if serial_no:
            print(f" * {CLR_BOLD}DeviceSerialNo{CLR_RESET}  : {CLR_GREEN}{CLR_BOLD}{serial_no}{CLR_RESET}")
        if apo_id:
            print(f" * {CLR_BOLD}APoNumberId{CLR_RESET}     : {CLR_WHITE}{apo_id}{CLR_RESET}")

        if cmd_type == "ReportStore":
            cols = req_data.get("ColumnsName", [{}])[0]
            print(f" * {CLR_BOLD}Report Result{CLR_RESET}   : OverallStatus={cols.get('OverallStatus')} | FinalJudgement={cols.get('FinalJudgement')}")
            print(f" * {CLR_BOLD}Takt Time{CLR_RESET}       : {cols.get('TaktTime')} sec | Total Tests={cols.get('TotalNumberOfTest')}")

        # Check simulation mode
        if SIM_MODE == "timeout":
            client_timeout = get_configured_client_timeout()
            print(f"{CLR_YELLOW}[SIMULATION: TIMEOUT MODE ACTIVATED] Dropping packet. No response sent.{CLR_RESET}")
            print(f"{CLR_DIM}                                      (Thinclient will time out after {client_timeout:g}s){CLR_RESET}\n")
            return

        # Determine response status
        if SIM_MODE == "failure":
            resp_status = "CONFIG REJECTED"
        elif cmd_type == "ReportStore":
            resp_status = "DATA SAVED SUCCESSFULLY"
        else:
            resp_status = "CONFIG SUCCESSFUL"

        now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        resp_dict = {
            "CmdType": "ResponseFromServer",
            "UtcRequest_ID": utc_request_id,
            "RequestStatus": resp_status,
            "ServerTimeStamp": now_ts
        }
        resp_payload = json.dumps(resp_dict, indent=2).encode('utf-8')

        if "SUB" in topic:
            response_topic = topic.replace("SUB", "PUB")
        else:
            response_topic = f"SELEC/PMS/PUB/G7/{mac_id}" if mac_id else topic

        # Simulated response delay/latency
        if SIM_RESPONSE_DELAY >= 0.5:
            client_timeout = get_configured_client_timeout()
            print(f"{CLR_YELLOW}[SIMULATING DELAY]{CLR_RESET} Waiting {SIM_RESPONSE_DELAY:g}s before sending response...")
            if SIM_RESPONSE_DELAY >= client_timeout:
                print(f"{CLR_YELLOW}                   [!] Delay ({SIM_RESPONSE_DELAY:g}s) >= client timeout ({client_timeout:g}s): Thinclient will time out!{CLR_RESET}")
            time.sleep(SIM_RESPONSE_DELAY)
        elif SIM_RESPONSE_DELAY > 0:
            time.sleep(SIM_RESPONSE_DELAY)

        STATS["responses_sent"] += 1
        print(f"{CLR_CYAN}{'-' * 78}{CLR_RESET}")
        print(f"{BG_GREEN}{CLR_WHITE} <<< [PMS OUTGOING RESPONSE #{STATS['responses_sent']}] {CLR_RESET} {CLR_BOLD}Status: {resp_status}{CLR_RESET}")
        print(f"{CLR_CYAN}{'-' * 78}{CLR_RESET}")
        print(f" * {CLR_BOLD}Response Topic{CLR_RESET}  : {CLR_GREEN}{response_topic}{CLR_RESET}")
        print(f" * {CLR_BOLD}UtcRequest_ID{CLR_RESET}   : {CLR_YELLOW}{utc_request_id}{CLR_RESET}")
        print(f" * {CLR_BOLD}RequestStatus{CLR_RESET}   : {CLR_GREEN if 'SUCCESS' in resp_status else CLR_RED}{CLR_BOLD}{resp_status}{CLR_RESET}")
        print(f" * {CLR_BOLD}ServerTimeStamp{CLR_RESET} : {now_ts}")
        print(f"{CLR_CYAN}{'=' * 78}{CLR_RESET}\n")

        packet_qos1 = build_publish_packet(response_topic, resp_payload, qos=1, packet_id=sender_session.next_packet_id())

        sent_count = 0
        with self.lock:
            for cl in list(self.clients):
                if response_topic in cl.subscriptions or cl == sender_session:
                    cl.send(packet_qos1)
                    sent_count += 1

        if sent_count == 0:
            sender_session.send(packet_qos1)


# ==============================================================================
# MAIN ENTRY POINT
# ==============================================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Selec PMS MQTT Server Simulator")
    parser.add_argument("--port", type=int, default=1883, help="Port to listen on (default: 1883)")
    parser.add_argument("--delay", type=float, default=0.025, help="Simulated server response delay in seconds (default: 0.025)")
    parser.add_argument("--mode", type=str, choices=["success", "failure", "timeout"], default="success", help="Default response mode (default: success)")
    args = parser.parse_args()

    global SIM_MODE, SIM_RESPONSE_DELAY
    SIM_MODE = args.mode
    SIM_RESPONSE_DELAY = args.delay

    setup_config_redirection()

    server = MockPMSServer(host="0.0.0.0", port=args.port)
    try:
        server.start()
    except KeyboardInterrupt:
        pass
    finally:
        restore_config()

if __name__ == "__main__":
    main()
