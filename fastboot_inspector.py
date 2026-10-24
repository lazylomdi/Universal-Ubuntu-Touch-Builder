"""Read-only Fastboot bootloader inspection.

Queries reported Fastboot variables and the read-only OEM device-info command.
Never issues unlock, flash, erase, format, or reboot commands.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from typing import Any

DEFAULT_TIMEOUT = 8


def _run(command: list[str], timeout: int = DEFAULT_TIMEOUT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)


def _combined(result: subprocess.CompletedProcess[str]) -> str:
    return "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())


def _getvar_value(text: str, name: str) -> str | None:
    pattern = re.compile(r"^\s*(?:\(bootloader\)\s*)?" + re.escape(name) + r"\s*:\s*(.*?)\s*$", re.IGNORECASE)
    for line in text.splitlines():
        match = pattern.match(line.strip())
        if match and match.group(1):
            return match.group(1).strip()
    return None


def _device_info_value(text: str, name: str) -> str | None:
    pattern = re.compile(r"^\s*(?:\(bootloader\)\s*)?" + re.escape(name) + r"\s*:\s*(true|false|yes|no|1|0)\s*$", re.IGNORECASE)
    for line in text.splitlines():
        match = pattern.match(line.strip())
        if match:
            return match.group(1).lower()
    return None


def _as_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    if value.lower() in {"true", "yes", "1"}:
        return True
    if value.lower() in {"false", "no", "0"}:
        return False
    return None


def inspect_fastboot_device(serial: str | None = None, fastboot_path: str | None = None,
                            timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """Inspect an already-connected Fastboot device without changing its state."""
    executable = fastboot_path or shutil.which("fastboot")
    if not executable:
        return {"status": "ERROR", "message": "Fastboot was not found. Install Android SDK Platform-Tools and add fastboot to PATH.",
                "serial": None, "device": {}, "devices": []}
    try:
        listed = _run([executable, "devices"], timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"status": "ERROR", "message": "Fastboot device listing timed out.", "serial": None, "device": {}, "devices": []}
    except OSError as exc:
        return {"status": "ERROR", "message": f"Could not start Fastboot: {exc}", "serial": None, "device": {}, "devices": []}
    if listed.returncode != 0:
        return {"status": "ERROR", "message": _combined(listed) or "Fastboot device listing failed.",
                "serial": None, "device": {}, "devices": []}

    devices: list[dict[str, str]] = []
    for line in listed.stdout.splitlines():
        parts = line.split()
        if parts:
            devices.append({"serial": parts[0], "state": parts[1] if len(parts) > 1 else "fastboot"})
    if serial:
        selected = next((item for item in devices if item["serial"] == serial), None)
        if selected is None:
            return {"status": "ERROR", "message": f"Fastboot serial '{serial}' was not listed.",
                    "serial": None, "device": {}, "devices": devices}
    else:
        if not devices:
            return {"status": "ERROR", "message": "No Fastboot device detected. Boot the phone into bootloader/Fastboot mode and reconnect the USB cable.",
                    "serial": None, "device": {}, "devices": []}
        if len(devices) > 1:
            return {"status": "ERROR", "message": "Multiple Fastboot devices found; rerun with --serial SERIAL.",
                    "serial": None, "device": {}, "devices": devices}
        selected = devices[0]
    serial = selected["serial"]

    queries = {
        "product": ["getvar", "product"],
        "unlocked": ["getvar", "unlocked"],
        "secure": ["getvar", "secure"],
        "is_userspace": ["getvar", "is-userspace"],
    }
    raw: dict[str, str | None] = {}
    values: dict[str, str | None] = {}
    for key, args in queries.items():
        try:
            result = _run([executable, "-s", serial, *args], timeout=timeout)
        except subprocess.TimeoutExpired:
            raw[key] = None
            values[key] = None
            continue
        except OSError as exc:
            raw[key] = str(exc)
            values[key] = None
            continue
        output = _combined(result)
        raw[key] = output or None
        values[key] = _getvar_value(output, "is-userspace" if key == "is_userspace" else key)

    try:
        info_result = _run([executable, "-s", serial, "oem", "device-info"], timeout=timeout)
        info_text = _combined(info_result)
    except (subprocess.TimeoutExpired, OSError) as exc:
        info_text = str(exc)
    raw["oem_device_info"] = info_text or None

    unlocked = _as_bool(_device_info_value(info_text, "Device unlocked"))
    if unlocked is None:
        unlocked = _as_bool(values["unlocked"])
    critical_unlocked = _as_bool(_device_info_value(info_text, "Device critical unlocked"))
    tampered = _as_bool(_device_info_value(info_text, "Device tampered"))
    secure = _as_bool(values["secure"])
    is_userspace = _as_bool(values["is_userspace"])
    state = "UNLOCKED (Fastboot-reported)" if unlocked is True else (
        "LOCKED (Fastboot-reported)" if unlocked is False else "UNKNOWN"
    )
    device = {
        "product": values["product"],
        "unlocked": unlocked,
        "critical_unlocked": critical_unlocked,
        "tampered": tampered,
        "secure": secure,
        "is_userspace": is_userspace,
        "raw": raw,
        "current_state": state,
        "evidence": "Read-only Fastboot getvar and oem device-info responses; device-reported and not independent proof of Ubuntu Touch compatibility.",
    }
    return {
        "status": "OK",
        "message": "Collected available bootloader information using read-only Fastboot queries. No unlock or flash commands were run.",
        "serial": serial,
        "device": device,
        "devices": devices,
        "limitations": [
            "Fastboot variables and OEM device-info responses vary by bootloader; unsupported or empty values remain unknown.",
            "The Fastboot product name may be a board/platform name rather than the retail model.",
            "Reported unlocked state does not establish that an Ubuntu Touch port exists or is functional.",
            "No device state, partitions, or data were changed."
        ]
    }
