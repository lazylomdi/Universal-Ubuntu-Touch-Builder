"""
config.py — static data tables for romforge.

All branch names, API levels, GApps info, and org lists live here.
Nothing in this file makes network calls or touches the filesystem.
Update this file when branches go EOL or new versions release.

Verification sources (checked July 2026):
  - AOSP branch model: source.android.com/docs/setup/download
  - LineageOS branches: lineageos.org/Changelog-31, wiki.lineageos.org/faq
  - NikGapps variants: nikgapps.com/build
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AndroidVersion:
    api: int
    aosp_tag: str           # historical pinned tag, still valid for old builds
    lineage_branch: str     # LineageOS or CyanogenMod branch name
    lineage_eol: bool       # True = no longer officially built upstream
    viability: str          # "good" | "fragile" | "archival"
    manifest_org: str       # GitHub org hosting the manifest for this branch
    product_prefix: str     # lunch product prefix: "cm" or "lineage"
    note: str


# manifest_org / product_prefix verified separately per era:
#   CyanogenMod (Android 4-6, cm-* branches):
#     manifest: github.com/CyanogenMod/android.git
#     lunch prefix: cm_<codename>  (e.g. "lunch cm_d2att-userdebug")
#     Sources: github.com/CyanogenMod/android (still live, branches cm-11.0
#     through cm-14.1 exist in git history), multiple XDA guides confirming
#     "lunch cm_<codename>-userdebug" as the CM lunch syntax.
#   LineageOS (Android 7+, lineage-* branches):
#     manifest: github.com/LineageOS/android.git
#     lunch prefix: lineage_<codename>
#     Source: github.com/LineageOS/android (current official manifest repo)
#
# IMPORTANT: these two manifests are NOT interchangeable. Pointing a cm-*
# branch at the LineageOS manifest repo (or vice versa) causes widespread
# "cannot initialize work tree" sync errors because the branch/revision
# doesn't exist in that org's repos.
_CM_ORG      = "CyanogenMod"
_LINEAGE_ORG = "LineageOS"

VERSIONS = {
    "4":  AndroidVersion(15,  "android-4.4_r1",       "cm-11.0",       True,  "archival",
          _CM_ORG, "cm",
          "CyanogenMod era. GCC toolchains from this period don't build on modern Ubuntu without an old container (14.04/16.04)."),
    "5":  AndroidVersion(22,  "android-5.1.1_r38",    "cm-12.1",       True,  "archival",
          _CM_ORG, "cm",
          "Lollipop, CyanogenMod era. Same toolchain rot as Android 4."),
    "6":  AndroidVersion(23,  "android-6.0.1_r81",    "cm-13.0",       True,  "archival",
          _CM_ORG, "cm",
          "Last major CyanogenMod branch. Some device trees still exist but expect patching."),
    "7":  AndroidVersion(25,  "android-7.1.2_r39",    "lineage-14.1",  True,  "fragile",
          _LINEAGE_ORG, "lineage",
          "First LineageOS-branded branch (LineageOS succeeded CyanogenMod in late 2016). EOL — no upstream fixes."),
    "8":  AndroidVersion(27,  "android-8.1.0_r81",    "lineage-15.1",  True,  "fragile",
          _LINEAGE_ORG, "lineage",
          "Treble introduced here. EOL upstream."),
    "9":  AndroidVersion(28,  "android-9.0.0_r61",    "lineage-16.0",  True,  "fragile",
          _LINEAGE_ORG, "lineage",
          "Last branch where LineageOS in-tree su addon was supported."),
    "10": AndroidVersion(29,  "android-10.0.0_r47",   "lineage-17.1",  True,  "fragile",
          _LINEAGE_ORG, "lineage",
          "EOL upstream."),
    "11": AndroidVersion(30,  "android-11.0.0_r48",   "lineage-18.1",  True,  "fragile",
          _LINEAGE_ORG, "lineage",
          "EOL 2024-03-05, 52 devices dropped from official LineageOS builds."),
    "12": AndroidVersion(32,  "android-12.1.0_r10",   "lineage-19.1",  True,  "fragile",
          _LINEAGE_ORG, "lineage",
          "EOL upstream. GSI/emulator lunch targets split from device targets here."),
    "13": AndroidVersion(33,  "android-13.0.0_r75",   "lineage-20",    True,  "fragile",
          _LINEAGE_ORG, "lineage",
          "EOL'd when lineage-23.x became stable."),
    "14": AndroidVersion(34,  "android-14.0.0_r41",   "lineage-21",    False, "good",
          _LINEAGE_ORG, "lineage",
          "Still receiving device submissions as of Changelog 31."),
    "15": AndroidVersion(35,  "android-15.0.0_r20",   "lineage-23.2",  False, "good",
          _LINEAGE_ORG, "lineage",
          "Current LineageOS stable. Best-supported option."),
}

# For fresh AOSP builds (not LineageOS), Google now recommends a rolling
# branch rather than a pinned tag. Verified: source.android.com/docs/setup/download
AOSP_ROLLING_BRANCH = "android-latest-release"
AOSP_EXTRA_INIT_FLAGS = ["--partial-clone", "--no-use-superproject"]

ARCHS = ["arm64", "armv7", "x86_64", "x86"]

# NikGapps variant → description.
# SourceForge folder: sourceforge.net/projects/nikgapps/files/Releases/Android-{ver}/
# Filename pattern: NikGapps-{variant}-{arch}-{ver}-{date}-signed.zip
# NikGapps has no JSON API; the tool points at the folder and expected pattern.
# Per-app overrides: edit nikgapps.config (PackageName=0/1/2) in the zip.
NIKGAPPS_VARIANTS = {
    "core":  "Play Store + Play Services only. Smallest possible GApps.",
    "basic": "Core + Gmail, Maps, Chrome, Calendar.",
    "omni":  "Basic + most Google apps people expect.",
    "stock": "Closest to a stock Pixel experience.",
    "full":  "Everything NikGapps offers.",
}
NIKGAPPS_SF_BASE = "https://sourceforge.net/projects/nikgapps/files/Releases"

# GApps package families by API range, for older versions where NikGapps
# either doesn't build or only partially supports the arch.
GAPPS_BY_API = [
    # (min_api, max_api, family, homepage, supported_arches)
    (15, 23, "OpenGApps (legacy, mirrors may be offline)",
     "https://opengapps.org", ["armv7", "x86"]),
    (24, 28, "OpenGApps / NikGApps",
     "https://nikgapps.com", ["armv7", "arm64", "x86_64"]),
    (29, 35, "NikGApps / MindTheGapps",
     "https://nikgapps.com", ["arm64", "x86_64"]),
]

# GitHub orgs that host device/vendor/kernel trees.
# Searched in order; results from named orgs are trusted higher than
# general search results.
DEVICE_ORGS = [
    "LineageOS",
    "TheMuppets",       # vendor blobs
    "PixelExperience",
    "crdroidandroid",
]

RECOVERY_ORGS = {
    "twrp":      ["TeamWin"],
    "orangefox": ["OrangeFoxRecovery"],
    "skyhawk":   ["SHRP"],
}

# Magisk — fetched from GitHub releases API.
MAGISK_RELEASES_API = "https://api.github.com/repos/topjohnwu/Magisk/releases/latest"

# Build sanity thresholds.
MIN_DISK_GB  = 150
MIN_RAM_GB   = 16

# ── Lunch release codes ────────────────────────────────────────────────────────
# Starting with Android 14 QPR2 (mid-2024), Google changed the lunch format
# from <product>-<variant> to <product>-<release>-<variant>.
# LineageOS lineage-21+ and AOSP Android 14+ require this three-part form.
# Older branches (lineage-20 and below, AOSP <14) still use the old two-part
# form and will FAIL if given a release code.
#
# Verified sources:
#   groups.google.com/g/android-building/c/TvKKsSLSlPY  (ap1a confirmation)
#   groups.google.com/g/android-building/c/z7gYowDYQfk  (Android 15 ap3a)
#   gist.github.com/eepymeowers/ce62de00da763d87ab03e539161a564f (full table)
#   github.com/itsfragilecode/android (lineage_veux-ap2a-userdebug example)
#
# Format: (lineage_branch or None) → release_code
# None = applies to raw AOSP at that API level
# Use the LATEST release code for each branch as the default.
LUNCH_RELEASE_CODES: dict[str, str | None] = {
    # Old branches — no release code, use legacy <product>-<variant> format
    "cm-11.0":      None,
    "cm-12.1":      None,
    "cm-13.0":      None,
    "lineage-14.1": None,
    "lineage-15.1": None,
    "lineage-16.0": None,
    "lineage-17.1": None,
    "lineage-18.1": None,
    "lineage-19.1": None,
    "lineage-20":   None,
    # Modern branches — three-part format required
    # lineage-21 shipped with Android 14; latest QPR is AP4A
    "lineage-21":   "ap4a",
    # lineage-22 / lineage-22.1 are Android 15 — latest QPR is BP1A
    "lineage-22":   "bp1a",
    "lineage-22.1": "bp1a",
    # lineage-23 / lineage-23.2 are Android 15/16 — BP2A+
    "lineage-23":   "bp2a",
    "lineage-23.2": "bp4a",
}

# AOSP release codes by API level (for --source aosp builds)
# Only needed for API 34+ (Android 14+)
AOSP_RELEASE_CODES: dict[int, str | None] = {
    34: "ap4a",   # Android 14 latest QPR
    35: "bp1a",   # Android 15 QPR2
}

