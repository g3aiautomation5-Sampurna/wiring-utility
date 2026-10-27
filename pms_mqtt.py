import json
import queue
import threading
import time

import paho.mqtt.client as mqtt

from pms_json_manager import (
    build_device_autowhitelisting,
    build_serial_no_validation,
    build_status_validation,
    build_empty_report_store,
    load_or_create_config,
    get_pc_mac_address,
    get_thinclient_uid,
    parse_sticker,
)


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

_config = load_or_create_config()

# Broker settings
BROKER_IP = _config.get("pms_broker_ip", "127.0.0.1")
BROKER_PORT = int(_config.get("pms_broker_port", 1883))

# MQTT credentials from external JSON
MQTT_USERNAME = _config.get("pms_broker_username", "")
MQTT_PASSWORD = _config.get("pms_broker_password", "")

# Device MAC address
DEVICE_MAC = get_pc_mac_address()

# Topic prefixes from external JSON
# PUBLISH_TOPIC_PREFIX = _config.get(
#     "pms_publish_topic_prefix", "SELEC/PMS/SUB/G7"
# ).rstrip("/")

# SUBSCRIBE_TOPIC_PREFIX = _config.get(
#     "pms_subscribe_topic_prefix", "SELEC/PMS/PUB/G7"
# ).rstrip("/")

# # Build device-specific topics
# PUBLISH_TOPIC = f"{PUBLISH_TOPIC_PREFIX}/{DEVICE_MAC}"
# RESPONSE_TOPIC = f"{SUBSCRIBE_TOPIC_PREFIX}/{DEVICE_MAC}"



PUBLISH_TOPIC_PREFIX = _config.get(
    "pms_publish_topic_prefix", "SELEC/PMS/PUB/G7"
).rstrip("/")

SUBSCRIBE_TOPIC_PREFIX = _config.get(
    "pms_subscribe_topic_prefix", "SELEC/PMS/SUB/G7"
).rstrip("/")

# Build device-specific topics
PUBLISH_TOPIC = f"{PUBLISH_TOPIC_PREFIX}/{DEVICE_MAC}"
RESPONSE_TOPIC = f"{SUBSCRIBE_TOPIC_PREFIX}/{DEVICE_MAC}"


# for payloads 
PAYLOAD_PUBLISH_TOPIC = f"{SUBSCRIBE_TOPIC_PREFIX}/{DEVICE_MAC}"
PAYLOAD_RESPONSE_TOPIC = f"{PUBLISH_TOPIC_PREFIX}/{DEVICE_MAC}"


print(f"[PMS MQTT] Broker: {BROKER_IP}:{BROKER_PORT}")
print(f"[PMS MQTT] Device MAC: {DEVICE_MAC}")
print(f"[PMS MQTT] Publish topic: {PUBLISH_TOPIC}")
print(f"[PMS MQTT] Subscribe topic: {RESPONSE_TOPIC}")

def get_pms_timeouts():
    """
    Returns (connection_timeout, server_validation_timeout, report_timeout)
    dynamically loaded from pms_config.json so timeout values are fully configurable.
    """
    cfg = load_or_create_config()
    server_timeout = float(cfg.get("pms_server_timeout", cfg.get("pms_validation_timeout", 10.0)))
    conn_timeout = float(cfg.get("pms_connection_timeout", 8.0))
    report_timeout = float(cfg.get("pms_report_timeout", 15.0))
    return conn_timeout, server_timeout, report_timeout

CONNECTION_TIMEOUT, VALIDATION_TIMEOUT, REPORT_TIMEOUT = get_pms_timeouts()
print(f"[PMS MQTT] Timeouts: Validation/Server={VALIDATION_TIMEOUT}s | Connection={CONNECTION_TIMEOUT}s | Report={REPORT_TIMEOUT}s")


class PMSMQTTClient:

    def __init__(self):
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"SelecInspection-{DEVICE_MAC}",
        )

        # Configure authentication before connecting.
        if MQTT_USERNAME:
            self.client.username_pw_set(
                username=MQTT_USERNAME,
                password=MQTT_PASSWORD,
            )

        self.connected = threading.Event()
        self.subscribed = threading.Event()
        self.messages = queue.Queue()

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_subscribe = self._on_subscribe
        self.client.on_message = self._on_message

        self.loop_started = False
        self.lock = threading.Lock()
        self.last_error = None

    # --------------------------------------------------
    # STATUS FOR FLASK UI
    # --------------------------------------------------

    def get_connection_status(self):
        is_connected = (
            self.connected.is_set()
            and self.subscribed.is_set()
        )
        cfg = load_or_create_config()
        active_broker_ip = cfg.get("pms_broker_ip", BROKER_IP)
        active_broker_port = int(cfg.get("pms_broker_port", BROKER_PORT))
        conn_timeout, server_timeout, report_timeout = get_pms_timeouts()

        return {
            "connected": is_connected,
            "status": "connected" if is_connected else "disconnected",
            "broker_ip": active_broker_ip,
            "broker_port": active_broker_port,
            "device_mac": DEVICE_MAC,
            "subscribed": self.subscribed.is_set(),
            "server_timeout": server_timeout,
            "connection_timeout": conn_timeout,
            "report_timeout": report_timeout,
            "error": self.last_error,
        }

    # --------------------------------------------------
    # MQTT CALLBACKS
    # --------------------------------------------------

    def _on_connect(
        self, client, userdata, flags, reason_code, properties
    ):
        if reason_code.is_failure:
            self.last_error = f"Connection rejected: {reason_code}"
            self.connected.clear()
            self.subscribed.clear()

            print(f"[PMS MQTT] {self.last_error}")
            return

        self.last_error = None
        self.connected.set()

        print(
            f"[PMS MQTT] Connected to {BROKER_IP}:{BROKER_PORT}"
        )

        # result, _ = client.subscribe(RESPONSE_TOPIC, qos=1) check 2
        result, _ = client.subscribe(
            [
                (RESPONSE_TOPIC, 1),
                (PAYLOAD_RESPONSE_TOPIC, 1),
            ]
        )

        if result != mqtt.MQTT_ERR_SUCCESS:
            self.last_error = (
                f"Subscribe request failed with code {result}"
            )
            self.subscribed.clear()
            print(f"[PMS MQTT] {self.last_error}")

    def _on_disconnect(
        self,
        client,
        userdata,
        disconnect_flags,
        reason_code,
        properties,
    ):
        self.connected.clear()
        self.subscribed.clear()

        if reason_code.is_failure:
            self.last_error = f"Unexpected disconnection: {reason_code}"
            print(f"[PMS MQTT] {self.last_error}")
        else:
            print(f"[PMS MQTT] Disconnected: {reason_code}")

    def _on_subscribe(
        self,
        client,
        userdata,
        mid,
        reason_code_list,
        properties,
    ):
        if all(
            not code.is_failure
            for code in reason_code_list
        ):
            self.subscribed.set()
            self.last_error = None

            print(
                f"[PMS MQTT] Subscribed to {RESPONSE_TOPIC}"
            )
        else:
            self.subscribed.clear()
            self.last_error = "PMS response topic subscription rejected."

            print(f"[PMS MQTT] {self.last_error}")

    def _on_message(self, client, userdata, msg):
        text = msg.payload.decode(
            "utf-8",
            errors="replace",
        )

        print(
            f"[PMS MQTT] Received on {msg.topic}: {text}"
        )

        self.messages.put({
            "topic": msg.topic,
            "payload": text,
            "received_at": time.monotonic(),
        })

    # --------------------------------------------------
    # CONNECT TO PMS MQTT BROKER
    # --------------------------------------------------

    # def connect(self):
    #     if (
    #         self.connected.is_set()
    #         and self.subscribed.is_set()
    #     ):
    #         return

    #     self.last_error = None

    #     try:
    #         cfg = load_or_create_config()
    #         active_broker_ip = cfg.get("pms_broker_ip", BROKER_IP)
    #         active_broker_port = int(cfg.get("pms_broker_port", BROKER_PORT))
    #         conn_timeout, _, _ = get_pms_timeouts()

    #         if not self.loop_started:
    #             self.client.connect(
    #                 active_broker_ip,
    #                 active_broker_port,
    #                 keepalive=60,
    #             )

    #             self.client.loop_start()
    #             self.loop_started = True

    #         if not self.connected.wait(conn_timeout):
    #             error = (
    #                 self.last_error
    #                 or f"Connection timed out to "
    #                 f"{active_broker_ip}:{active_broker_port} after {conn_timeout:g}s"
    #             )
    #             self.last_error = error
    #             raise TimeoutError(f"[PMS MQTT] {error}")

    #         if not self.subscribed.wait(conn_timeout):
    #             error = (
    #                 self.last_error
    #                 or f"PMS response topic subscription was not confirmed within {conn_timeout:g}s."
    #             )
    #             self.last_error = error
    #             raise TimeoutError(f"[PMS MQTT] {error}")

    #     except Exception as exc:
    #         self.last_error = str(exc)
    #         print(f"[PMS MQTT] Connection failed: {self.last_error}")
    #         raise

    
    def connect(self):
        if (
            self.connected.is_set()
            and self.subscribed.is_set()
        ):
            print("[CHECKPOINT 1/4] PMS MQTT: Already connected and subscribed.")
            return

        self.last_error = None

        try:
            cfg = load_or_create_config()
            active_broker_ip = cfg.get("pms_broker_ip", BROKER_IP)
            active_broker_port = int(
                cfg.get("pms_broker_port", BROKER_PORT)
            )
            conn_timeout, _, _ = get_pms_timeouts()

            print("\n" + "=" * 65)
            print("[CHECKPOINT 1/4] PMS MQTT CONNECTION STARTED")
            print(f"[PMS MQTT] Broker: {active_broker_ip}:{active_broker_port}")
            print("[PMS MQTT] Starting connection checks...")
            print("=" * 65)

            if not self.loop_started:
                print("[PMS MQTT] Initiating broker connection...")

                self.client.connect(
                    active_broker_ip,
                    active_broker_port,
                    keepalive=60,
                )

                self.client.loop_start()
                self.loop_started = True
                print("[PMS MQTT] MQTT network loop started.")

            print("[PMS MQTT] Waiting for broker connection confirmation...")

            if not self.connected.wait(conn_timeout):
                error = (
                    self.last_error
                    or f"Connection timed out to "
                    f"{active_broker_ip}:{active_broker_port} "
                    f"after {conn_timeout:g}s"
                )
                self.last_error = error
                raise TimeoutError(error)

            print("[CHECKPOINT 2/4] BROKER CONNECTION SUCCESSFUL")

            print(
                f"[PMS MQTT] Waiting for response-topic subscription: "
                # f"{RESPONSE_TOPIC}"  check 3
                f"{RESPONSE_TOPIC} and {PAYLOAD_RESPONSE_TOPIC}" 
            )

            if not self.subscribed.wait(conn_timeout):
                error = (
                    self.last_error
                    or "PMS response-topic subscription was not confirmed "
                    f"within {conn_timeout:g}s."
                )
                self.last_error = error
                raise TimeoutError(error)

            print("[CHECKPOINT 3/4] RESPONSE TOPIC SUBSCRIBED")
            print("[PMS MQTT] Ready to publish payloads and receive responses.")
            print("=" * 65 + "\n")

        except Exception as exc:
            self.last_error = str(exc)
            print("[CHECKPOINT FAILED] PMS MQTT CONNECTION FAILED")
            print(f"[PMS MQTT] Reason: {self.last_error}")
            print("=" * 65)
            raise


    # --------------------------------------------------
    # MESSAGE QUEUE
    # --------------------------------------------------

    def _clear_pending_messages(self):
        while True:
            try:
                self.messages.get_nowait()
            except queue.Empty:
                break

    # --------------------------------------------------
    # PUBLISH JSON PAYLOAD
    # --------------------------------------------------

    def publish_json(self, payload):
        if not (
            self.connected.is_set()
            and self.subscribed.is_set()
        ):
            raise ConnectionError(
                "Cannot publish: MQTT is not connected and subscribed."
            )

        info = self.client.publish(
            PAYLOAD_PUBLISH_TOPIC,    # check 1
            json.dumps(payload),
            qos=1,
        )

        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(
                f"MQTT publish failed with code {info.rc}"
            )

        info.wait_for_publish(timeout=10)

        if not info.is_published():
            raise TimeoutError(
                "MQTT publish was not confirmed by the broker."
            )

        print(
            f"[PMS MQTT] Published {payload.get('CmdType')} "
            f"to {PAYLOAD_PUBLISH_TOPIC}"
        )
        print(
            f"[PMS MQTT] Request ID: "
            f"{payload.get('UtcRequest_ID')}"
        )

    # --------------------------------------------------
    # VALIDATE ONE COMMAND
    # --------------------------------------------------

    def validate(self, command_name, payload):
        """
        Publish one validation command and wait for a
        ResponseFromServer message with the matching
        UtcRequest_ID and CONFIG SUCCESSFUL status.
        """

        with self.lock:
            self.connect()
            self._clear_pending_messages()

            request_id = str(
                payload.get("UtcRequest_ID", "")
            ).strip()

            if not request_id:
                raise ValueError(
                    f"{command_name} payload has no UtcRequest_ID."
                )

            print("\n" + "=" * 55)
            print(f"[PMS MQTT] Starting: {command_name}")
            print(f"[PMS MQTT] Expected ID: {request_id}")
            print("=" * 55)

            self.publish_json(payload)

            _, validation_timeout, _ = get_pms_timeouts()
            deadline = time.monotonic() + validation_timeout

            while time.monotonic() < deadline:
                remaining = deadline - time.monotonic()

                try:
                    msg = self.messages.get(
                        timeout=max(0.1, remaining)
                    )
                except queue.Empty:
                    break

                try:
                    response = json.loads(msg["payload"])
                except (json.JSONDecodeError, TypeError):
                    print(
                        "[PMS MQTT] Ignoring non-JSON response."
                    )
                    continue

                response_type = str(
                    response.get("CmdType", "")
                ).strip()

                if response_type.upper() != "RESPONSEFROMSERVER":
                    print(
                        "[PMS MQTT] Ignoring unexpected "
                        f"CmdType: {response_type}"
                    )
                    continue

                response_id = str(
                    response.get("UtcRequest_ID", "")
                ).strip()

                if response_id != request_id:
                    print(
                        "[PMS MQTT] Ignoring response with "
                        f"mismatched ID: {response_id}"
                    )
                    continue

                status = str(
                    response.get("RequestStatus", "")
                ).strip()

                print(
                    f"[PMS MQTT] Matching response received "
                    f"for {command_name}"
                )
                print(f"[PMS MQTT] RequestStatus: {status}")

                if status.upper() == "CONFIG SUCCESSFUL":
                    print(
                        f"[PMS MQTT] {command_name}: SUCCESS"
                    )
                    return response

                raise RuntimeError(
                    f"{command_name} failed. "
                    f"Server status: {status or 'Missing status'}"
                )

            raise TimeoutError(
                f"No matching response for "
                f"{command_name} within "
                f"{validation_timeout:g} seconds (server timeout reached)."
            )

    # --------------------------------------------------
    # SEQUENTIAL VALIDATION WORKFLOW
    # --------------------------------------------------

    def run_startup_validation(
        self,
        device_serial_no=None,
        apo_number_id=None,
    ):
        """
        Run all three validations in sequence.
        Inspection is authorized only if all succeed.
        """

        # Fail immediately if the broker cannot be reached.
        self.connect()

        config = load_or_create_config()
        mac_id = get_pc_mac_address()

        # Auto-parse if a full QR string (e.g. 'Id: ..; Sr: ..;') was passed as device_serial_no
        if device_serial_no and any(k in str(device_serial_no).lower() for k in ["id:", "sr:"]):
            parsed_apo, parsed_serial = parse_sticker(device_serial_no, default_apo=apo_number_id)
            if not apo_number_id:
                apo_number_id = parsed_apo
            device_serial_no = parsed_serial

        if not device_serial_no:
            device_serial_no = get_thinclient_uid()

        if not apo_number_id:
            apo_number_id = config.get(
                "default_apo_number_id",
                "56",
            )

        print("\n")
        print("#" * 60)
        print("[PMS MQTT] STARTING VALIDATION SEQUENCE")
        print("#" * 60)

        # STEP 1: DeviceAutoWhitelisting
        req_id_1, payload_1 = build_device_autowhitelisting(
            mac_id=mac_id,
        )

        resp_1 = self.validate(
            "DeviceAutoWhitelisting",
            payload_1,
        )

        print(
            "[PMS MQTT] Step 1 passed. "
            "Proceeding to SerialNoValidation."
        )

        # STEP 2: SerialNoValidation
        req_id_2, payload_2 = build_serial_no_validation(
            device_serial_no=device_serial_no,
            apo_number_id=apo_number_id,
            mac_id=mac_id,
        )

        resp_2 = self.validate(
            "SerialNoValidation",
            payload_2,
        )

        print(
            "[PMS MQTT] Step 2 passed. "
            "Proceeding to StatusValidation."
        )

        # STEP 3: StatusValidation
        req_id_3, payload_3 = build_status_validation(
            device_serial_no=device_serial_no,
            apo_number_id=apo_number_id,
            mac_id=mac_id,
        )

        resp_3 = self.validate(
            "StatusValidation",
            payload_3,
        )

        payload_4 = build_empty_report_store(
            device_serial_no=device_serial_no,
            apo_number_id=apo_number_id,
            mac_id=mac_id
        )

        print("\n")
        print("#" * 60)
        print("[PMS MQTT] ALL THREE VALIDATIONS SUCCESSFUL")
        print("[PMS MQTT] Inspection is authorized to start.")
        print("#" * 60)

        return {
            "success": True,
            "message": "All three PMS validations successful.",
            "payloads": {
                "DeviceAutoWhitelisting": payload_1,
                "SerialNoValidation": payload_2,
                "StatusValidation": payload_3,
                "ReportStore": payload_4,
            },
            "server_responses": {
                "DeviceAutoWhitelisting": resp_1,
                "SerialNoValidation": resp_2,
                "StatusValidation": resp_3,
            }
        }

    # --------------------------------------------------
    # PUBLISH FINAL INSPECTION REPORT
    # --------------------------------------------------

    # def publish_report(self, payload):
    #     with self.lock:
    #         self.connect()
    #         self._clear_pending_messages()

    #         self.publish_json(payload)

    #         print(
    #             "[PMS MQTT] ReportStore published; "
    #             "waiting for response..."
    #         )

    #         _, _, report_timeout = get_pms_timeouts()
    #         deadline = time.monotonic() + report_timeout

    #         while time.monotonic() < deadline:
    #             try:
    #                 msg = self.messages.get(
    #                     timeout=max(
    #                         0.1,
    #                         deadline - time.monotonic(),
    #                     )
    #                 )
    #             except queue.Empty:
    #                 break

    #             return {
    #                 "received": True,
    #                 "topic": msg["topic"],
    #                 "payload": msg["payload"],
    #             }

    #         return {
    #             "received": False,
    #             "message": f"ReportStore response timed out after {report_timeout:g} seconds.",
    #         }

    
    def publish_report(self, payload):
        """
        Publish ReportStore and wait for a matching ResponseFromServer.

        Retries up to 3 total publish attempts if no matching response
        is received. A matching rejection is returned immediately.
        """

        MAX_ATTEMPTS = 3

        with self.lock:
            self.connect()
            self._clear_pending_messages()

            request_id = str(
                payload.get("UtcRequest_ID", "")
            ).strip()

            if not request_id:
                raise ValueError(
                    "ReportStore payload has no UtcRequest_ID."
                )

            _, _, report_timeout = get_pms_timeouts()

            for attempt in range(1, MAX_ATTEMPTS + 1):
                print(
                    f"[PMS MQTT] ReportStore attempt "
                    f"{attempt}/{MAX_ATTEMPTS}; "
                    f"Request ID: {request_id}"
                )

                # Republish the same payload with the same request ID.
                self.publish_json(payload)

                deadline = time.monotonic() + report_timeout

                while time.monotonic() < deadline:
                    remaining = deadline - time.monotonic()

                    try:
                        msg = self.messages.get(
                            timeout=max(0.1, remaining)
                        )
                    except queue.Empty:
                        break

                    try:
                        response = json.loads(msg["payload"])
                    except (json.JSONDecodeError, TypeError):
                        print(
                            "[PMS MQTT] Ignoring non-JSON "
                            "ReportStore response."
                        )
                        continue

                    response_type = str(
                        response.get("CmdType", "")
                    ).strip()

                    if response_type.upper() != "RESPONSEFROMSERVER":
                        print(
                            "[PMS MQTT] Ignoring unrelated response "
                            f"CmdType: {response_type}"
                        )
                        continue

                    response_id = str(
                        response.get("UtcRequest_ID", "")
                    ).strip()

                    if response_id != request_id:
                        print(
                            "[PMS MQTT] Ignoring response with "
                            f"mismatched Request ID: {response_id}"
                        )
                        continue

                    status = str(
                        response.get("RequestStatus", "")
                    ).strip()

                    if status.upper() in {
                        "CONFIG SUCCESSFUL",
                        "DATA SAVED SUCCESSFULLY",
                    }:
                        print(
                            "[PMS MQTT] ReportStore accepted by PMS."
                        )
                        return {
                            "received": True,
                            "accepted": True,
                            "request_id": request_id,
                            "request_status": status,
                            "topic": msg["topic"],
                            "payload": response,
                            "attempts": attempt,
                        }

                    # A matching response arrived, but it did not
                    # confirm success. Treat it as a rejection.
                    reason = next(
                        (
                            str(response[key]).strip()
                            for key in (
                                "Reason",
                                "Message",
                                "ErrorMessage",
                                "Error",
                                "Description",
                                "ResponseMessage",
                            )
                            if response.get(key) not in (None, "")
                        ),
                        status or "PMS did not confirm ReportStore success.",
                    )

                    print(
                        "[PMS MQTT] ReportStore was not accepted. "
                        f"Status: {status}; Reason: {reason}"
                    )

                    return {
                        "received": True,
                        "accepted": False,
                        "request_id": request_id,
                        "request_status": status,
                        "reason": reason,
                        "topic": msg["topic"],
                        "payload": response,
                        "attempts": attempt,
                    }

                print(
                    f"[PMS MQTT] No matching ReportStore response "
                    f"during attempt {attempt}/{MAX_ATTEMPTS}."
                )

            return {
                "received": False,
                "accepted": False,
                "request_id": request_id,
                "message": (
                    "No matching ReportStore response received "
                    f"after {MAX_ATTEMPTS} attempts."
                ),
                "attempts": MAX_ATTEMPTS,
            }



# One shared client for the Flask process
pms_mqtt = PMSMQTTClient()
