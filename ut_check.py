#!/usr/bin/env python3
"""Offline-first Ubuntu Touch readiness assessment for AndroidBuilder."""
from __future__ import annotations
import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from source_discovery import discover_github_candidates
from device_inspector import inspect_device
from fastboot_inspector import inspect_fastboot_device

STATUSES = {"VERIFIED", "CANDIDATE", "UNKNOWN", "BLOCKED", "NOT_APPLICABLE"}

@dataclass(frozen=True)
class Finding:
    key: str
    value: Any
    status: str
    evidence: str
    next_step: str = ""
    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"invalid status: {self.status}")

def assess_device(manufacturer: str | None, model: str | None, ram_gb: float | None,
                  codename: str | None = None, android_version: str | None = None,
                  kernel_version: str | None = None, bootloader_unlock: str | None = None) -> dict[str, Any]:
    """Build a conservative assessment from user-supplied facts only."""
    findings: list[Finding] = []
    supplied = {"manufacturer": manufacturer, "model": model, "ram_gb": ram_gb,
                "codename": codename, "android_version": android_version,
                "kernel_version": kernel_version, "bootloader_unlock": bootloader_unlock}
    for key, value in supplied.items():
        if value is None or (isinstance(value, str) and not value.strip()):
            findings.append(Finding(key, None, "UNKNOWN", "Not provided.",
                "Research or obtain this device-specific information."))
        else:
            findings.append(Finding(key, value, "CANDIDATE",
                "User-provided input; not independently verified.",
                "Verify against manufacturer documentation or a trustworthy device source."))
    for key in ("kernel_source", "device_tree", "vendor_blobs", "halium_base",
                "bootloader_unlock_eligibility", "existing_ubuntu_touch_port",
                "hardware_functionality", "partition_layout"):
        findings.append(Finding(key, None, "UNKNOWN", "No independently verified evidence collected.",
            "Research authoritative sources; physical testing may be required."))
    missing_core = [f.key for f in findings if f.key in {
        "codename", "android_version", "kernel_version", "bootloader_unlock"
    } and f.status == "UNKNOWN"]
    return {
        "schema_version": 1,
        "assessment": "UNKNOWN" if missing_core else "CANDIDATE",
        "device": supplied,
        "readiness_claim": "No functional Ubuntu Touch port is established by this report.",
        "physical_device_available": False,
        "findings": [asdict(f) for f in findings],
        "missing_core_information": missing_core,
        "limitations": [
            "Evidence sources are labeled per finding: user input, device-reported ADB properties, or independently verified external evidence.",
            "Repository existence does not prove that sources build or support hardware.",
            "Compilation does not prove bootability or working hardware features.",
            "No device was flashed or functionally tested; a connected device may have been queried using read-only ADB commands."
        ]
    }

def render_markdown(report: dict[str, Any]) -> str:
    device = report["device"]
    label = " ".join(str(device[k]) for k in ("manufacturer", "model") if device.get(k)) or "Unspecified device"
    lines = [f"# Ubuntu Touch readiness report: {label}", "",
        f"- **Assessment:** {report['assessment']}",
        f"- **RAM (reported):** {device.get('ram_gb') if device.get('ram_gb') is not None else 'Unknown'} GB",
        f"- **Physical device available:** {report['physical_device_available']}",
        f"- **Conclusion:** {report['readiness_claim']}", "",
        "## Device inspection", ""]
    inspection = report.get("device_inspection", {})
    lines.append(f"- **Inspection status:** {inspection.get('status', 'NOT_RUN')}")
    lines.append(f"- **Message:** {inspection.get('message', 'No live inspection data.')}")
    if inspection.get("serial"):
        lines.append(f"- **ADB serial:** {inspection['serial']}")
    fastboot = report.get("fastboot_inspection", {})
    lines.extend(["", "## Fastboot inspection", ""])
    lines.append(f"- **Inspection status:** {fastboot.get('status', 'NOT_RUN')}")
    lines.append(f"- **Message:** {fastboot.get('message', 'Pass --inspect-fastboot while the phone is in Fastboot mode.')}")
    if fastboot.get("serial"):
        lines.append(f"- **Fastboot serial:** {fastboot['serial']}")
    fastboot_device = fastboot.get("device", {})
    if fastboot_device:
        lines.extend([
            f"- **Bootloader product:** {fastboot_device.get('product') or 'Unknown'}",
            f"- **Current bootloader state:** {fastboot_device.get('current_state', 'UNKNOWN')}",
            f"- **Critical bootloader unlocked:** {fastboot_device.get('critical_unlocked') if fastboot_device.get('critical_unlocked') is not None else 'Unknown'}",
            f"- **Secure mode:** {fastboot_device.get('secure') if fastboot_device.get('secure') is not None else 'Unknown'}",
            f"- **Device tampered:** {fastboot_device.get('tampered') if fastboot_device.get('tampered') is not None else 'Unknown'}",
            f"- **Fastboot userspace mode:** {fastboot_device.get('is_userspace') if fastboot_device.get('is_userspace') is not None else 'Unknown'}",
            "- Fastboot values are device-reported and may be unsupported or vendor-specific."
        ])
    lines.extend(["", "## Findings", "", "| Area | Value | Status | Evidence |", "|---|---|---|---|"])
    def safe(value: Any) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")
    for item in report["findings"]:
        value = "Unknown" if item["value"] is None else str(item["value"])
        lines.append(f"| {safe(item['key'])} | {safe(value)} | {item['status']} | {safe(item['evidence'])} |")
    port_finding = next((item for item in report["findings"] if item["key"] == "existing_ubuntu_touch_port"), None)
    if port_finding and port_finding["status"] == "VERIFIED" and port_finding["value"]:
        compatibility_label = "Supported by evidence"
        compatibility_detail = "A port is marked verified in the report evidence; review the cited device-specific sources before proceeding."
    elif port_finding and port_finding["status"] == "BLOCKED":
        compatibility_label = "Blocked by a known issue"
        compatibility_detail = port_finding.get("next_step") or "Review the recorded blocker before proceeding."
    elif port_finding and port_finding["status"] == "CANDIDATE":
        compatibility_label = "Possible but unverified"
        compatibility_detail = "A candidate port clue exists, but it is not verified for this exact device variant."
    else:
        compatibility_label = "Not enough information"
        compatibility_detail = "No independently verified Ubuntu Touch port evidence is recorded for this exact device."
    lines.extend(["", "## Compatibility summary", "",
        f"- **Status:** {compatibility_label}",
        f"- **Next step:** {compatibility_detail}",
        "- This is an evidence summary, not a compatibility score or guarantee.", "",
        "## How to interpret this report", "",
        "- **CANDIDATE:** a clue or user/device-reported value; not independently verified compatibility evidence.",
        "- **VERIFIED:** supported by cited, reviewed evidence for this exact device and variant.",
        "- **UNKNOWN:** evidence is missing; this is not proof of support or incompatibility.",
        "- **BLOCKED:** a known requirement or blocker prevents the proposed workflow.",
        "", "A connected device being detected only proves ADB communication. It does not prove that Ubuntu Touch is available or functional.",
        "", "## Missing core information", ""])
    lines.extend([f"- `{key}`" for key in report["missing_core_information"]] or ["- None recorded by this rule set."])
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in report["limitations"])
    lines.append("")
    return "\n".join(lines)

def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number greater than zero") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a number greater than zero")
    return parsed

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="romforge.py ut-check",
        description="Assess Ubuntu Touch port readiness without a connected phone.")
    parser.add_argument("--manufacturer", default="Sony")
    parser.add_argument("--model", default="Xperia R1")
    parser.add_argument("--ram-gb", type=_positive_float, default=2.0)
    parser.add_argument("--codename")
    parser.add_argument("--android-version")
    parser.add_argument("--kernel-version")
    parser.add_argument("--bootloader-unlock", choices=["yes", "no", "unknown"], default="unknown")
    parser.add_argument("--inspect-device", action="store_true", help="Read device properties through ADB (read-only; requires USB debugging).")
    parser.add_argument("--inspect-fastboot", action="store_true", help="Read bootloader information from a device already in Fastboot mode; does not reboot, unlock, or flash.")

    parser.add_argument("--serial", help="ADB serial to inspect when multiple devices are connected; requires --inspect-device.")
    parser.add_argument("--online", action="store_true", help="Search GitHub for candidate repositories; results are not compatibility proof.")
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--markdown-out", type=Path)
    return parser

def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.serial and not (args.inspect_device or args.inspect_fastboot):
        build_parser().error("--serial requires --inspect-device or --inspect-fastboot")
    live = inspect_device(args.serial) if args.inspect_device else None
    fastboot_live = inspect_fastboot_device(args.serial) if args.inspect_fastboot else None
    manufacturer, model, ram_gb = args.manufacturer, args.model, args.ram_gb
    codename, android_version, kernel_version = args.codename, args.android_version, args.kernel_version
    bootloader_unlock = None if args.bootloader_unlock == "unknown" else args.bootloader_unlock
    if fastboot_live and fastboot_live.get("status") == "OK" and not (live and live.get("status") == "OK"):
        # Fastboot cannot reliably identify the retail model or Android properties.
        # Do not inherit the offline Xperia defaults for a Fastboot-only inspection.
        manufacturer, model, ram_gb = None, None, None
        codename, android_version, kernel_version = None, None, None
        bootloader_unlock = "yes" if fastboot_live["device"].get("unlocked") is True else (
            "no" if fastboot_live["device"].get("unlocked") is False else None
        )
    if live and live.get("status") == "OK":
        detected = live["device"]
        # In live-inspection mode, absent device properties stay unknown rather
        # than inheriting the offline Sony Xperia R1 defaults.
        manufacturer = detected.get("manufacturer")
        model = detected.get("model")
        ram_gb = detected.get("ram_gb")
        codename = detected.get("codename") or codename
        android_version = detected.get("android_version") or android_version
        kernel_version = detected.get("kernel_version") or kernel_version
        bootloader_unlock = detected.get("bootloader_unlock") or bootloader_unlock
    report = assess_device(manufacturer, model, ram_gb, codename,
        android_version, kernel_version, bootloader_unlock)
    if live and live.get("status") == "OK":
        detected = live.get("device", {})
        # Keep provenance aligned with the source of each value. A live ADB
        # observation remains a candidate, not independently verified evidence.
        observed_fields = {
            "manufacturer": "manufacturer",
            "model": "model",
            "ram_gb": "ram_gb",
            "codename": "codename",
            "android_version": "android_version",
            "kernel_version": "kernel_version",
        }
        findings_by_key = {item["key"]: item for item in report["findings"]}
        for finding_key, device_key in observed_fields.items():
            observed_value = detected.get(device_key)
            finding = findings_by_key.get(finding_key)
            if observed_value is not None and finding is not None and finding["value"] == observed_value:
                finding["evidence"] = "Read-only ADB inspection; device-reported value, not independently verified."
                finding["next_step"] = "Cross-check against authoritative device-specific documentation."
        # Current lock state is not the same as permission or eligibility to unlock.
        eligibility = findings_by_key.get("bootloader_unlock_eligibility")
        if eligibility is not None:
            eligibility["evidence"] = "Unknown: device-reported lock properties do not establish OEM unlock eligibility."
            eligibility["next_step"] = "Verify the exact model/region's official unlock policy; do not infer eligibility from a single property."
        extra = detected.get("extra_properties", {})
        property_labels = {
            "treble_enabled": ("android_treble_enabled", "ro.treble.enabled"),
            "slot_suffix": ("boot_slot_suffix", "ro.boot.slot_suffix"),
            "first_api_level": ("first_api_level", "ro.product.first_api_level"),
            "oem_unlock_supported": ("oem_unlock_supported_property", "ro.oem_unlock_supported"),
            "oem_unlock_allowed": ("oem_unlock_allowed_property", "sys.oem_unlock_allowed"),
            "flash_locked": ("bootloader_flash_locked_property", "ro.boot.flash.locked"),
            "product_name": ("android_product_name", "ro.product.name"),
            "product_board": ("android_product_board", "ro.product.board"),
            "board_platform": ("android_board_platform", "ro.board.platform"),
            "build_incremental": ("android_build_incremental", "ro.build.version.incremental"),
            "verified_boot_state": ("verified_boot_state", "ro.boot.verifiedbootstate"),
            "vbmeta_device_state": ("vbmeta_device_state", "ro.boot.vbmeta.device_state"),
        }
        for key, (label, prop_name) in property_labels.items():
            value = extra.get(key)
            report["findings"].append(asdict(Finding(
                label, value, "UNKNOWN" if value is None else "CANDIDATE",
                f"Read-only ADB property {prop_name}; device-reported, not independently verified.",
                "Use as a compatibility clue; verify against device-specific sources."
            )))
        setting_checks = {
            "developer_options_enabled": "Developer options enabled",
            "oem_unlock_toggle_enabled": "OEM unlocking toggle enabled",
        }
        for device_key, label in setting_checks.items():
            value = detected.get(device_key)
            normalized = {"1": True, "0": False, 1: True, 0: False}.get(value)
            report["findings"].append(asdict(Finding(
                device_key, normalized,
                "UNKNOWN" if normalized is None else "CANDIDATE",
                "Read-only Android Settings query; 1 means enabled and 0 means disabled. This does not establish bootloader unlock eligibility.",
                "If unknown, check the phone Developer options screen. Verify bootloader unlock eligibility separately."
            )))
        boot = detected.get("bootloader_assessment", {})
        report["findings"].append(asdict(Finding(
            "bootloader_current_state",
            boot.get("current_state", "UNKNOWN"),
            "CANDIDATE" if boot.get("current_state", "UNKNOWN") != "UNKNOWN" else "UNKNOWN",
            boot.get("evidence", "No reliable bootloader-state indicator was available."),
            "Treat this as device-reported evidence only. Verify on-device and distinguish current lock state from OEM unlock eligibility."
        )))
        storage = detected.get("data_storage", {})
        report["findings"].append(asdict(Finding(
            "data_partition_storage",
            {k: storage.get(k) for k in ("filesystem", "size", "used", "available", "use_percent")},
            "UNKNOWN" if not storage.get("size") else "CANDIDATE",
            "Read-only output of df -h /data; reports the mounted data filesystem only.",
            "Check available space before any future build or installation steps."
        )))
    if fastboot_live and fastboot_live.get("status") == "OK":
        fd = fastboot_live.get("device", {})
        fastboot_findings = [
            ("fastboot_product", fd.get("product"), "Bootloader-reported Fastboot product; may identify a board rather than retail model."),
            ("fastboot_device_unlocked", fd.get("unlocked"), "Read-only Fastboot getvar / oem device-info response."),
            ("fastboot_critical_unlocked", fd.get("critical_unlocked"), "Read-only Fastboot oem device-info response."),
            ("fastboot_secure", fd.get("secure"), "Read-only Fastboot getvar secure response."),
            ("fastboot_tampered", fd.get("tampered"), "Read-only Fastboot oem device-info response."),
            ("fastboot_is_userspace", fd.get("is_userspace"), "Read-only Fastboot getvar is-userspace response."),
        ]
        for key, value, evidence in fastboot_findings:
            report["findings"].append(asdict(Finding(
                key, value, "UNKNOWN" if value is None else "CANDIDATE", evidence,
                "Treat as device-reported evidence; confirm exact model and compatibility independently."
            )))
        unlock_finding = next((item for item in report["findings"] if item["key"] == "bootloader_unlock"), None)
        if unlock_finding is not None and fd.get("unlocked") is not None:
            unlock_finding["evidence"] = "Read-only Fastboot response; device-reported current lock state, not OEM unlock eligibility."
            unlock_finding["next_step"] = "Verify exact device identity and community/manufacturer support; current unlocked state does not prove Ubuntu Touch compatibility."
        state = fd.get("current_state", "UNKNOWN")
        report["findings"].append(asdict(Finding(
            "bootloader_current_state", state,
            "UNKNOWN" if state == "UNKNOWN" else "CANDIDATE",
            fd.get("evidence", "Read-only Fastboot output; not independently verified."),
            "Current lock state is different from OEM permission/eligibility and Ubuntu Touch compatibility."
        )))
        report["fastboot_inspection"] = fastboot_live
    else:
        report["fastboot_inspection"] = fastboot_live or {
            "status": "NOT_RUN",
            "message": "Pass --inspect-fastboot while the phone is already in Fastboot mode.",
            "serial": None, "device": {}, "devices": []
        }
    report["physical_device_available"] = bool(
        (live and live.get("status") == "OK") or
        (fastboot_live and fastboot_live.get("status") == "OK")
    )
    report["device_inspection"] = live or {"status": "NOT_RUN", "message": "Pass --inspect-device to query a connected phone.", "serial": None, "device": {}, "devices": []}
    if live and live.get("status") != "OK":
        report["limitations"].append("Live device inspection was requested but did not succeed: " + live.get("message", "unknown error"))
    elif live and live.get("status") == "OK":
        report["limitations"] = [x for x in report["limitations"] if x != "No device was connected, flashed, or physically tested."]
        report["limitations"].append("A device was connected for read-only ADB property inspection; it was not flashed or functionally tested.")
    if fastboot_live and fastboot_live.get("status") != "OK":
        report["limitations"].append("Fastboot inspection was requested but did not succeed: " + fastboot_live.get("message", "unknown error"))
    elif fastboot_live and fastboot_live.get("status") == "OK":
        report["limitations"] = [x for x in report["limitations"] if x != "No device was connected, flashed, or physically tested."]
        report["limitations"].append("A device was queried in Fastboot mode using read-only commands; no unlock, reboot, or flash command was issued.")
    if args.online:
        query = "{} {} Android kernel device tree".format(args.manufacturer or "", args.model or "").strip()
        report["source_discovery"] = discover_github_candidates(query)
    else:
        report["source_discovery"] = {"status": "NOT_RUN", "candidates": [], "error": None,
            "note": "Pass --online to search GitHub; no network request was made."}
    json_text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    markdown_text = render_markdown(report)
    try:
        if args.json_out:
            args.json_out.parent.mkdir(parents=True, exist_ok=True)
            args.json_out.write_text(json_text, encoding="utf-8")
        if args.markdown_out:
            args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
            args.markdown_out.write_text(markdown_text, encoding="utf-8")
    except OSError as exc:
        print(f"error: cannot write report: {exc}", file=sys.stderr)
        return 2
    if not args.json_out and not args.markdown_out:
        print(markdown_text, end="")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
