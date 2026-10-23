import json
import queue
import threading
import time

import paho.mqtt.client as mqtt

from pms_json_manager import (
    build_device_autowhitelisting,
    build_serial_no_validation,
    build_status_validation,
    load_or_create_config,
    get_pc_mac_address,
    get_thinclient_uid,
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
PUBLISH_TOPIC_PREFIX = _config.get(
    "pms_publish_topic_prefix", "SELEC/PMS/SUB/G7"
).rstrip("/")

SUBSCRIBE_TOPIC_PREFIX = _config.get(
    "pms_subscribe_topic_prefix", "SELEC/PMS/PUB/G7"
).rstrip("/")

# Build device-specific topics
PUBLISH_TOPIC = f"{PUBLISH_TOPIC_PREFIX}/{DEVICE_MAC}"
RESPONSE_TOPIC = f"{SUBSCRIBE_TOPIC_PREFIX}/{DEVICE_MAC}"

print(f"[PMS MQTT] Broker: {BROKER_IP}:{BROKER_PORT}")
print(f"[PMS MQTT] Device MAC: {DEVICE_MAC}")
print(f"[PMS MQTT] Publish topic: {PUBLISH_TOPIC}")
print(f"[PMS MQTT] Subscribe topic: {RESPONSE_TOPIC}")

CONNECTION_TIMEOUT = 8
VALIDATION_TIMEOUT = 20
REPORT_TIMEOUT = 155


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

        return {
            "connected": is_connected,
            "status": "connected" if is_connected else "disconnected",
            "broker_ip": BROKER_IP,
            "broker_port": BROKER_PORT,
            "device_mac": DEVICE_MAC,
            "subscribed": self.subscribed.is_set(),
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

        result, _ = client.subscribe(RESPONSE_TOPIC, qos=1)

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

    def connect(self):
        if (
            self.connected.is_set()
            and self.subscribed.is_set()
        ):
            return

        self.last_error = None

        try:
            if not self.loop_started:
                self.client.connect(
                    BROKER_IP,
                    BROKER_PORT,
                    keepalive=60,
                )

                self.client.loop_start()
                self.loop_started = True

            if not self.connected.wait(CONNECTION_TIMEOUT):
                error = (
                    self.last_error
                    or f"Connection timed out to "
                    f"{BROKER_IP}:{BROKER_PORT}"
                )
                self.last_error = error
                raise TimeoutError(f"[PMS MQTT] {error}")

            if not self.subscribed.wait(CONNECTION_TIMEOUT):
                error = (
                    self.last_error
                    or "PMS response topic subscription was not confirmed."
                )
                self.last_error = error
                raise TimeoutError(f"[PMS MQTT] {error}")

        except Exception as exc:
            self.last_error = str(exc)
            print(f"[PMS MQTT] Connection failed: {self.last_error}")
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
            PUBLISH_TOPIC,
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
            f"to {PUBLISH_TOPIC}"
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

            deadline = time.monotonic() + VALIDATION_TIMEOUT

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
                    return True

                raise RuntimeError(
                    f"{command_name} failed. "
                    f"Server status: {status or 'Missing status'}"
                )

            raise TimeoutError(
                f"No matching successful response for "
                f"{command_name} within "
                f"{VALIDATION_TIMEOUT} seconds."
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
        _, payload = build_device_autowhitelisting(
            mac_id=mac_id,
        )

        self.validate(
            "DeviceAutoWhitelisting",
            payload,
        )

        print(
            "[PMS MQTT] Step 1 passed. "
            "Proceeding to SerialNoValidation."
        )

        # STEP 2: SerialNoValidation
        _, payload = build_serial_no_validation(
            device_serial_no=device_serial_no,
            apo_number_id=apo_number_id,
            mac_id=mac_id,
        )

        self.validate(
            "SerialNoValidation",
            payload,
        )

        print(
            "[PMS MQTT] Step 2 passed. "
            "Proceeding to StatusValidation."
        )

        # STEP 3: StatusValidation
        _, payload = build_status_validation(
            device_serial_no=device_serial_no,
            apo_number_id=apo_number_id,
            mac_id=mac_id,
        )

        self.validate(
            "StatusValidation",
            payload,
        )

        print("\n")
        print("#" * 60)
        print("[PMS MQTT] ALL THREE VALIDATIONS SUCCESSFUL")
        print("[PMS MQTT] Inspection is authorized to start.")
        print("#" * 60)

        return {
            "success": True,
            "message": "All three PMS validations successful.",
        }

    # --------------------------------------------------
    # PUBLISH FINAL INSPECTION REPORT
    # --------------------------------------------------

    def publish_report(self, payload):
        with self.lock:
            self.connect()
            self._clear_pending_messages()

            self.publish_json(payload)

            print(
                "[PMS MQTT] ReportStore published; "
                "waiting for response..."
            )

            deadline = time.monotonic() + REPORT_TIMEOUT

            while time.monotonic() < deadline:
                try:
                    msg = self.messages.get(
                        timeout=max(
                            0.1,
                            deadline - time.monotonic(),
                        )
                    )
                except queue.Empty:
                    break

                return {
                    "received": True,
                    "topic": msg["topic"],
                    "payload": msg["payload"],
                }

            return {
                "received": False,
                "message": "ReportStore response timed out.",
            }


# One shared client for the Flask process
pms_mqtt = PMSMQTTClient()
