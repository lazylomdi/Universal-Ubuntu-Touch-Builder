"""Read-only Android Debug Bridge inspection for Ubuntu Touch readiness checks.

Only invokes ADB device listing and read-only shell queries. Never changes device state.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from typing import Any

DEFAULT_TIMEOUT = 8


def _run(command: list[str], timeout: int = DEFAULT_TIMEOUT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, capture_output=True, text=True, timeout=timeout, check=False
    )


def _parse_getprop(text: str) -> dict[str, str]:
    props: dict[str, str] = {}
    for line in text.splitlines():
        match = re.match(r"\[([^]]+)\]: \[(.*)\]$", line.strip())
        if match and match.group(2):
            props[match.group(1)] = match.group(2)
    return props


def inspect_device(serial: str | None = None, adb_path: str | None = None,
                   timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """Inspect one authorized ADB device; report failures instead of guessing."""
    executable = adb_path or shutil.which("adb")
    if not executable:
        return {"status": "ERROR", "message": "ADB was not found. Install Android SDK Platform-Tools and add adb.exe to PATH.",
                "serial": None, "device": {}, "devices": []}

    try:
        listed = _run([executable, "devices", "-l"], timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"status": "ERROR", "message": "ADB device listing timed out.", "serial": None, "device": {}, "devices": []}
    except OSError as exc:
        return {"status": "ERROR", "message": f"Could not start ADB: {exc}", "serial": None, "device": {}, "devices": []}
    if listed.returncode != 0:
        return {"status": "ERROR", "message": (listed.stderr.strip() or "ADB device listing failed."),
                "serial": None, "device": {}, "devices": []}

    devices: list[dict[str, str]] = []
    for line in listed.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            devices.append({"serial": parts[0], "state": parts[1],
                            "details": " ".join(parts[2:])})
    if serial:
        selected = next((d for d in devices if d["serial"] == serial), None)
        if selected is None:
            return {"status": "ERROR", "message": f"Serial '{serial}' was not listed by ADB.",
                    "serial": None, "device": {}, "devices": devices}
        if selected["state"] != "device":
            state_message = {"unauthorized": "Unlock the phone and accept the USB debugging authorization prompt.",
                             "offline": "The selected device is offline. Reconnect the USB cable and retry."}
            return {"status": "ERROR", "message": state_message.get(selected["state"], f"Device state is {selected['state']}."),
                    "serial": serial, "device": {}, "devices": devices}
    else:
        ready = [d for d in devices if d["state"] == "device"]
        if not ready:
            if any(d["state"] == "unauthorized" for d in devices):
                message = "Phone detected but not authorized. Unlock it and accept the USB debugging prompt."
            elif devices:
                message = "No authorized online device. Check the USB connection and ADB state."
            else:
                message = "No phone detected. Connect it by USB and enable USB debugging."
            return {"status": "ERROR", "message": message, "serial": None, "device": {}, "devices": devices}
        if len(ready) > 1:
            return {"status": "ERROR", "message": "Multiple authorized devices found; rerun with --serial SERIAL.",
                    "serial": None, "device": {}, "devices": devices}
        selected = ready[0]
        serial = selected["serial"]

    try:
        props_result = _run([executable, "-s", serial, "shell", "getprop"], timeout=timeout)
        mem_result = _run([executable, "-s", serial, "shell", "cat", "/proc/meminfo"], timeout=timeout)
        kernel_result = _run([executable, "-s", serial, "shell", "uname", "-r"], timeout=timeout)
        # Read Android Settings only; never write/change these settings.
        dev_options_result = _run([executable, "-s", serial, "shell", "settings", "get", "global", "development_settings_enabled"], timeout=timeout)
        oem_unlock_results = {
            "global.oem_unlock_enabled": _run([executable, "-s", serial, "shell", "settings", "get", "global", "oem_unlock_enabled"], timeout=timeout),
            "global.oem_unlock_allowed": _run([executable, "-s", serial, "shell", "settings", "get", "global", "oem_unlock_allowed"], timeout=timeout),
            "secure.oem_unlock_enabled": _run([executable, "-s", serial, "shell", "settings", "get", "secure", "oem_unlock_enabled"], timeout=timeout),
        }
    except subprocess.TimeoutExpired:
        return {"status": "ERROR", "message": "An ADB read-only query timed out.", "serial": serial, "device": {}, "devices": devices}
    except OSError as exc:
        return {"status": "ERROR", "message": f"Could not run an ADB read-only query: {exc}",
                "serial": serial, "device": {}, "devices": devices}

    if props_result.returncode != 0:
        return {"status": "ERROR", "message": props_result.stderr.strip() or "Could not read Android properties.",
                "serial": serial, "device": {}, "devices": devices}

    props = _parse_getprop(props_result.stdout)
    def parse_setting(result: subprocess.CompletedProcess[str]) -> str | None:
        if result.returncode != 0:
            return None
        value = result.stdout.strip().lower()
        return value if value in {"0", "1"} else None
    developer_options = parse_setting(dev_options_result)
    oem_unlock_raw = {name: (result.stdout.strip() if result.returncode == 0 else None)
                      for name, result in oem_unlock_results.items()}
    oem_unlock_toggle = next((parse_setting(result) for result in oem_unlock_results.values()
                              if parse_setting(result) is not None), None)
    mem_match = re.search(r"^MemTotal:\s+(\d+)\s+kB", mem_result.stdout, re.MULTILINE) if mem_result.returncode == 0 else None
    ram_gb = round(int(mem_match.group(1)) / 1024 / 1024, 2) if mem_match else None
    model = (props.get("ro.product.model") or props.get("ro.product.system.model")
             or props.get("ro.product.vendor.model"))
    manufacturer = (props.get("ro.product.manufacturer") or props.get("ro.product.system.manufacturer")
                    or props.get("ro.product.vendor.manufacturer"))
    # Keep raw compatibility indicators visible; absent properties remain unknown.
    extra_properties = {
        "treble_enabled": props.get("ro.treble.enabled") or None,
        "slot_suffix": props.get("ro.boot.slot_suffix") or None,
        "first_api_level": props.get("ro.product.first_api_level") or None,
        "oem_unlock_supported": props.get("ro.oem_unlock_supported") or None,
        "oem_unlock_allowed": props.get("sys.oem_unlock_allowed") or None,
        "flash_locked": props.get("ro.boot.flash.locked") or None,
        "product_name": props.get("ro.product.name") or None,
        "product_board": props.get("ro.product.board") or None,
        "board_platform": props.get("ro.board.platform") or None,
        "build_incremental": props.get("ro.build.version.incremental") or None,
        "verified_boot_state": props.get("ro.boot.verifiedbootstate") or None,
        "vbmeta_device_state": props.get("ro.boot.vbmeta.device_state") or None,
    }
    try:
        storage_result = _run([executable, "-s", serial, "shell", "df", "-h", "/data"], timeout=timeout)
        storage_text = storage_result.stdout.strip() if storage_result.returncode == 0 else ""
    except (subprocess.TimeoutExpired, OSError):
        storage_text = ""
    storage_lines = storage_text.splitlines()
    storage_data = {"raw": storage_text or None, "filesystem": None, "size": None,
                    "used": None, "available": None, "use_percent": None}
    if len(storage_lines) >= 2:
        columns = storage_lines[-1].split()
        if len(columns) >= 5:
            storage_data.update({"filesystem": columns[0], "size": columns[1],
                                 "used": columns[2], "available": columns[3],
                                 "use_percent": columns[4]})
    device = {
        "manufacturer": manufacturer,
        "model": model,
        "codename": props.get("ro.product.device") or props.get("ro.build.product"),
        "android_version": props.get("ro.build.version.release"),
        "kernel_version": kernel_result.stdout.strip() if kernel_result.returncode == 0 else None,
        "ram_gb": ram_gb,
        "build_fingerprint": props.get("ro.build.fingerprint"),
        "cpu_abi": props.get("ro.product.cpu.abi"),
        "developer_options_enabled": developer_options,
        "oem_unlock_toggle_enabled": oem_unlock_toggle,
        "oem_unlock_setting_raw": oem_unlock_raw,
        "oem_unlock_allowed_property": extra_properties.get("oem_unlock_allowed"),
        "developer_settings_evidence": {
            "source": "read-only `adb shell settings get global` queries",
            "note": "1 means enabled, 0 means disabled, and missing/unsupported values remain unknown. OEM toggle detection checks several read-only settings namespaces/keys. These settings do not prove bootloader unlock eligibility."
        },
        "bootloader_unlock": None,
        "bootloader_assessment": {
            "current_state": (
                "LOCKED (device-reported)" if extra_properties.get("flash_locked") == "1"
                else "UNLOCKED (device-reported)" if extra_properties.get("flash_locked") == "0"
                else "UNKNOWN"
            ),
            "oem_unlock_supported": extra_properties.get("oem_unlock_supported"),
            "verified_boot_state": extra_properties.get("verified_boot_state"),
            "vbmeta_device_state": extra_properties.get("vbmeta_device_state"),
            "evidence": "Read-only Android properties; may be absent or vendor-specific and are not definitive on every device."
        },
        "extra_properties": extra_properties,
        "data_storage": storage_data,
    }
    return {
        "status": "OK",
        "message": "Collected available properties using read-only ADB commands.",
        "serial": serial,
        "device": device,
        "devices": devices,
        "limitations": [
            "ADB properties may be absent, vendor-specific, or inaccurate.",
            "Bootloader unlock eligibility is separate from current lock state; ADB properties are clues only and may be absent or vendor-specific.",
            "No kernel/device-tree source validation, build, boot, or hardware test was performed.",
            "No device files or settings were changed."
        ]
    }
