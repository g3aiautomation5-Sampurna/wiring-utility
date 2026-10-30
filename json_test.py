
import json
import os
import tempfile

invalid_json = '''{
    "app_version": "v1",
    "pms_broker_port": 1883,
}'''

temp_path = None

try:
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        encoding="utf-8",
        delete=False
    ) as temp:
        temp.write(invalid_json)
        temp_path = temp.name

    try:
        with open(temp_path, "r", encoding="utf-8") as file:
            json.load(file)

        print("FAIL: Invalid JSON was accepted.")

    except json.JSONDecodeError as error:
        print("PASS: Invalid JSON detected.")
        print(f"Line: {error.lineno}")
        print(f"Column: {error.colno}")
        print(f"Error: {error.msg}")

finally:
    if temp_path and os.path.exists(temp_path):
        os.remove(temp_path)
