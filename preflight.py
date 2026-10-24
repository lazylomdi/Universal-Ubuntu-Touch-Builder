"""Pre-build environment checks for AndroidBuilder.

Checks are advisory unless a required executable for the chosen backend is
missing. They do not claim that a device/ROM combination is supported.
"""
from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path
from typing import Any


MIN_DISK_GB = 150
MIN_RAM_GB = 16


def _available_ram_gb() -> float | None:
    """Return a best-effort estimate using only the Python standard library."""
    try:
        if hasattr(os, "sysconf"):
            page_size = os.sysconf("SC_PAGE_SIZE")
            pages = os.sysconf("SC_PHYS_PAGES")
            if page_size > 0 and pages > 0:
                return page_size * pages / (1024 ** 3)
    except (OSError, ValueError, TypeError):
        pass
    # Windows fallback: GlobalMemoryStatusEx via ctypes.
    if platform.system() == "Windows":
        try:
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.dwLength = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return status.ullTotalPhys / (1024 ** 3)
        except (AttributeError, OSError, TypeError):
            pass
    return None


def run_preflight(workdir: str | Path, backend: str = "local") -> dict[str, Any]:
    """Check host resources and backend tools without modifying the system."""
    path = Path(workdir).expanduser().resolve()
    checks: list[dict[str, str]] = []

    def add(name: str, status: str, detail: str) -> None:
        checks.append({"name": name, "status": status, "detail": detail})

    system = platform.system()
    if system == "Linux":
        add("Operating system", "OK", f"Linux ({platform.release()})")
    elif system == "Windows" and backend == "local":
        add("Operating system", "WARNING",
            "Native Windows is not the recommended environment for full Android ROM compilation; use Ubuntu/WSL2.")
    else:
        add("Operating system", "INFO", f"{system}; confirm the selected backend supports this environment.")

    try:
        path.mkdir(parents=True, exist_ok=True)
        free_gb = shutil.disk_usage(path).free / (1024 ** 3)
        if free_gb >= MIN_DISK_GB:
            add("Free disk space", "OK", f"{free_gb:.1f} GiB available.")
        else:
            add("Free disk space", "WARNING",
                f"{free_gb:.1f} GiB available; full Android builds commonly need about {MIN_DISK_GB} GiB or more.")
    except OSError as exc:
        add("Free disk space", "BLOCKED", f"Cannot access work directory {path}: {exc}")

    ram_gb = _available_ram_gb()
    if ram_gb is None:
        add("System memory", "UNKNOWN", "Could not determine installed RAM automatically.")
    elif ram_gb >= MIN_RAM_GB:
        add("System memory", "OK", f"{ram_gb:.1f} GiB RAM detected.")
    else:
        add("System memory", "WARNING",
            f"{ram_gb:.1f} GiB RAM detected; full Android builds commonly need about {MIN_RAM_GB} GiB or more.")

    required = {"local": ["bash", "git", "repo", "java"],
                "docker": ["docker"],
                "github-actions": ["git"]}.get(backend)
    if required is None:
        add("Build backend", "BLOCKED", f"Unknown backend: {backend}")
    else:
        for executable in required:
            found = shutil.which(executable)
            optional = backend == "github-actions" and executable == "git"
            if found:
                add(f"Tool: {executable}", "OK", found)
            elif executable == "repo":
                add(f"Tool: {executable}", "WARNING",
                    "Not found on PATH; repo sync cannot run until Google's repo tool is installed.")
            elif executable == "java":
                add(f"Tool: {executable}", "WARNING",
                    "Not found on PATH; install the JDK required by the selected Android branch.")
            elif optional:
                add(f"Tool: {executable}", "WARNING", "Not found on PATH.")
            else:
                add(f"Tool: {executable}", "BLOCKED", f"Required for the {backend} backend but not found on PATH.")

    blocked = any(item["status"] == "BLOCKED" for item in checks)
    warnings = sum(item["status"] in {"WARNING", "UNKNOWN"} for item in checks)
    return {
        "schema_version": 1,
        "workdir": str(path),
        "backend": backend,
        "platform": system,
        "ready": not blocked,
        "summary": "Required checks passed; review warnings before building." if not blocked else "One or more required checks failed.",
        "warning_count": warnings,
        "checks": checks,
        "limitations": [
            "Resource thresholds are general guidance and vary by Android version and device tree.",
            "Passing preflight does not verify ROM source compatibility, device support, build success, bootability, or hardware functionality.",
            "This check does not install tools, elevate privileges, download sources, or modify system settings."
        ]
    }
