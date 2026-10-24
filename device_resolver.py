"""
device_resolver.py — find device/kernel/recovery trees and detect connected devices.

All GitHub calls go through github_client, which handles auth, caching, and
rate-limit reporting. This module is purely search logic.

Match quality:
  exact    = codename appears as a whole _ or - delimited token in repo name
  partial  = codename is a substring but not a token (e.g. "hello" in "ac50hello")
Partial matches are shown but flagged — the tool never auto-selects one.
"""

import re
import shutil
import subprocess
from dataclasses import dataclass

import github_client
from config import DEVICE_ORGS, RECOVERY_ORGS


@dataclass
class Repo:
    full_name:   str
    clone_url:   str
    html_url:    str
    stars:       int
    pushed:      str   # ISO date string
    kind:        str   # "device" | "vendor" | "kernel" | "recovery" | "tweak" | "unknown"
    exact_match: bool  # codename is a whole token in the repo name
    vendor_match: bool # vendor hint appears as a token (True when no hint given)


def _tokens(name: str) -> list[str]:
    """Split a repo name into lowercase tokens on _ and -."""
    return [t for t in re.split(r"[_\-]+", name.lower()) if t]


def _kind_from_name(name: str) -> str:
    n = name.lower()
    if any(k in n for k in ("vendor", "proprietary")):  return "vendor"
    if "kernel" in n:                                     return "kernel"
    if "device" in n:                                     return "device"
    if any(k in n for k in ("recovery", "twrp", "fox", "shrp")): return "recovery"
    return "unknown"


def _make_repo(item: dict, codename: str, vendor: str | None) -> Repo:
    tokens = _tokens(item["name"])
    return Repo(
        full_name    = item["full_name"],
        clone_url    = item["clone_url"],
        html_url     = item["html_url"],
        stars        = item.get("stargazers_count", 0),
        pushed       = (item.get("pushed_at") or "")[:10],
        kind         = _kind_from_name(item["name"]),
        exact_match  = codename.lower() in tokens,
        vendor_match = (not vendor) or (vendor.lower() in tokens),
    )


def _dedupe(repos: list[Repo]) -> list[Repo]:
    seen = set()
    out  = []
    for r in repos:
        if r.full_name not in seen:
            seen.add(r.full_name)
            out.append(r)
    return out


def search(codename: str, vendor: str | None = None,
           kind: str = "device") -> list[Repo]:
    """
    Search GitHub for repos of the given kind for a device codename.
    Returns a deduplicated list ranked by (exact_match, vendor_match, stars, recency).

    Uses a consolidated query strategy: one broad query per org to avoid
    burning 8+ API calls per search (old behavior). With disk caching,
    repeated searches for the same codename are free.
    """
    results: list[dict] = []
    seen_queries: set[str] = set()

    def _search(q: str) -> None:
        if q in seen_queries:
            return
        seen_queries.add(q)
        results.extend(github_client.search_repos(q, max_results=8))

    # Org-scoped queries (higher-trust sources first)
    orgs = DEVICE_ORGS if kind != "recovery" else []
    for org in orgs:
        _search(f"org:{org} {codename} in:name")

    # General queries — consolidated to 2-3 rather than 8
    vendor_str = vendor or ""
    if kind == "device":
        _search(f"android_device_{vendor_str}_{codename}")
        _search(f"{codename} android device tree")
    elif kind == "kernel":
        _search(f"android_kernel_{vendor_str}_{codename}")
        _search(f"{codename} android kernel")
    elif kind == "recovery":
        for rec_orgs in RECOVERY_ORGS.values():
            for org in rec_orgs:
                _search(f"org:{org} {codename} in:name")
        _search(f"{codename} twrp recovery android")
    elif kind == "tweak":
        _search(f"{codename} magisk module")
        _search(f"{codename} kernelsu module")

    repos = [_make_repo(i, codename, vendor) for i in results]
    repos = _dedupe(repos)
    repos.sort(key=lambda r: (r.exact_match, r.vendor_match, r.stars, r.pushed),
               reverse=True)
    return repos


def detect_device() -> dict | None:
    """
    Read-only ADB probe. Returns device info dict or None.
    Never writes to or installs anything on the device.
    """
    if not shutil.which("adb"):
        return None
    try:
        subprocess.run(["adb", "start-server"], capture_output=True, timeout=10)
        out = subprocess.run(["adb", "devices"], capture_output=True,
                              text=True, timeout=10).stdout
        if "\tdevice" not in out:
            return None

        def prop(p: str) -> str:
            r = subprocess.run(["adb", "shell", "getprop", p],
                                capture_output=True, text=True, timeout=10)
            return r.stdout.strip()

        codename = prop("ro.product.device") or prop("ro.build.product")
        if not codename:
            return None
        abi = prop("ro.product.cpu.abi")
        arch = ("arm64"  if "arm64"   in abi else
                "armv7"  if "armeabi" in abi else
                "x86_64" if "x86_64"  in abi else
                "x86"    if "x86"     in abi else "unknown")
        return {
            "codename": codename,
            "vendor":   prop("ro.product.manufacturer").lower(),
            "arch":     arch,
            "android":  prop("ro.build.version.release"),
        }
    except (subprocess.SubprocessError, OSError):
        return None


def print_repos(repos: list[Repo]) -> None:
    if not repos:
        print("  No results found. Check your GitHub token or codename spelling.")
        return
    for i, r in enumerate(repos, 1):
        match_tag = "[exact]" if r.exact_match else "[PARTIAL — verify before using]"
        print(f"  [{i:>2}] ({r.kind:<8}) {r.full_name:<55} ★{r.stars:<5} {r.pushed}  {match_tag}")
        print(f"         {r.html_url}")
