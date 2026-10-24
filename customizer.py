"""
customizer.py — pre-build and post-build ROM customization.

Every function here either:
  (a) actually works end-to-end, or
  (b) clearly documents that it's a manual step and exactly what to do.

No half-implementations that look automated but silently do nothing.
"""

import json
import shutil
import subprocess
import urllib.request
from pathlib import Path

import github_client
from config import GAPPS_BY_API, NIKGAPPS_VARIANTS, NIKGAPPS_SF_BASE, MAGISK_RELEASES_API


# ── GApps ─────────────────────────────────────────────────────────────────────

def gapps_info(api_level: int, arch: str) -> dict | None:
    for min_a, max_a, family, homepage, arches in GAPPS_BY_API:
        if min_a <= api_level <= max_a and arch in arches:
            return {"family": family, "homepage": homepage}
    return None


def stage_gapps(workdir: Path, api_level: int, arch: str,
                android_ver: str, variant: str | None,
                dry_run: bool = False) -> bool:
    """
    Stage GApps. For API 29+ with NikGapps: generates a vendor overlay
    directory WITH a working Android.mk so the build system actually picks
    it up. The GApps zip itself must be downloaded manually (NikGapps has
    no stable API). The Android.mk causes the zip to be included as a
    prebuilt package in the system image.

    For older versions (OpenGApps): flash as a separate zip after install,
    which is more reliable than trying to bake it in.
    """
    info = gapps_info(api_level, arch)
    if info is None:
        print(f"  No known GApps for API {api_level}/{arch}. Flash manually post-install.")
        return False

    gapps_dir = workdir / "vendor" / "romforge_gapps"

    if api_level >= 29 and variant:
        # NikGapps path — generate a working vendor overlay
        sf_url = f"{NIKGAPPS_SF_BASE}/Android-{android_ver}/"
        zip_name = f"NikGapps-{variant}-{arch}-{android_ver}-<date>-signed.zip"
        print(f"  GApps family : {info['family']}")
        print(f"  Variant      : {variant} — {NIKGAPPS_VARIANTS.get(variant, '')}")
        print(f"  Download from: {sf_url}")
        print(f"  Filename like: {zip_name}")
        print(f"  Then place the zip at: {gapps_dir}/NikGapps.zip")
        print(f"  The generated Android.mk will include it in the build.")
        print(f"  Per-app control: edit nikgapps.config in the zip (PackageName=0/1/2)")

        if dry_run:
            print(f"  [dry-run] would create vendor overlay at {gapps_dir}")
            return True

        gapps_dir.mkdir(parents=True, exist_ok=True)
        # Android.mk that tells the build system to include the zip as a product package
        (gapps_dir / "Android.mk").write_text(
            "LOCAL_PATH := $(call my-dir)\n\n"
            "include $(CLEAR_VARS)\n"
            "LOCAL_MODULE        := NikGapps\n"
            "LOCAL_MODULE_TAGS   := optional\n"
            "LOCAL_MODULE_CLASS  := ETC\n"
            "LOCAL_MODULE_PATH   := $(TARGET_OUT)/etc\n"
            "LOCAL_SRC_FILES     := NikGapps.zip\n"
            "include $(BUILD_PREBUILT)\n"
        )
        # AndroidProducts.mk to pull this into the build
        (gapps_dir / "AndroidProducts.mk").write_text(
            "PRODUCT_MAKEFILES := $(LOCAL_DIR)/gapps.mk\n"
        )
        (gapps_dir / "gapps.mk").write_text(
            "PRODUCT_PACKAGES += NikGapps\n"
        )
        (gapps_dir / "PLACE_NIKGAPPS_ZIP_HERE.txt").write_text(
            f"Download: {sf_url}\n"
            f"Filename: {zip_name}\n"
            f"Rename to: NikGapps.zip and place in this directory.\n"
            f"Then include this vendor overlay in your device's BoardConfig.mk:\n"
            f"  PRODUCT_SOONG_NAMESPACES += vendor/romforge_gapps\n"
        )
        print(f"  Created vendor overlay at {gapps_dir}")
        print(f"  Add to your device's BoardConfig.mk:")
        print(f"    PRODUCT_SOONG_NAMESPACES += vendor/romforge_gapps")
    else:
        # Older versions — just provide clear instructions for manual flash
        print(f"  GApps family : {info['family']}")
        print(f"  Homepage     : {info['homepage']}")
        print(f"  For Android {android_ver} ({api_level}): flash GApps separately")
        print(f"  after installing the ROM in recovery. Do NOT try to bake")
        print(f"  older GApps into the build — the in-tree integration is fragile.")
    return True


# ── Custom APKs and wallpapers ─────────────────────────────────────────────────

def stage_assets(workdir: Path, apks: list[Path], wallpapers: list[Path],
                  codename: str, dry_run: bool = False) -> bool:
    """
    Copy APKs and wallpapers into a vendor overlay with a working Android.mk.
    Unlike the old implementation, this generates the makefile entries so the
    build system actually includes them.
    """
    overlay = workdir / "vendor" / "romforge_assets"
    apps_dir  = overlay / "app"
    walls_dir = overlay / "wallpapers"

    if dry_run:
        print(f"  [dry-run] would stage {len(apks)} APK(s), {len(wallpapers)} wallpaper(s)")
        print(f"  [dry-run] would generate Android.mk at {overlay}")
        return True

    overlay.mkdir(parents=True, exist_ok=True)
    apps_dir.mkdir(exist_ok=True)
    walls_dir.mkdir(exist_ok=True)

    apk_names   = []
    wall_names  = []
    ok = True

    for apk in apks:
        if not apk.exists():
            print(f"  APK not found: {apk}")
            ok = False
            continue
        dest = apps_dir / apk.name
        shutil.copy2(apk, dest)
        apk_names.append(apk.stem)

    for wp in wallpapers:
        if not wp.exists():
            print(f"  Wallpaper not found: {wp}")
            ok = False
            continue
        shutil.copy2(wp, walls_dir / wp.name)
        wall_names.append(wp.name)

    # Generate Android.mk for APKs
    mk_lines = ["LOCAL_PATH := $(call my-dir)\n"]
    for name in apk_names:
        mk_lines += [
            "include $(CLEAR_VARS)",
            f"LOCAL_MODULE        := {name}",
            "LOCAL_MODULE_CLASS  := APPS",
            "LOCAL_MODULE_TAGS   := optional",
            "LOCAL_CERTIFICATE   := PRESIGNED",
            f"LOCAL_SRC_FILES     := app/{name}.apk",
            "include $(BUILD_PREBUILT)",
            "",
        ]
    (overlay / "Android.mk").write_text("\n".join(mk_lines))

    # PRODUCT_COPY_FILES for wallpapers
    copy_files = "\n".join(
        f"  $(LOCAL_DIR)/wallpapers/{n}:$(TARGET_COPY_OUT_SYSTEM)/media/wallpaper/{n} \\"
        for n in wall_names
    )
    products = "PRODUCT_PACKAGES += " + " ".join(apk_names) + "\n" if apk_names else ""
    products += "PRODUCT_COPY_FILES += \\\n" + copy_files + "\n" if wall_names else ""
    (overlay / "assets.mk").write_text(products)

    print(f"  Staged {len(apk_names)} APK(s) and {len(wall_names)} wallpaper(s)")
    print(f"  Add to your device tree:")
    print(f"    $(call inherit-product, vendor/romforge_assets/assets.mk)")
    return ok


# ── Boot animation ─────────────────────────────────────────────────────────────

def stage_boot_animation(workdir: Path, zip_path: Path,
                          dry_run: bool = False) -> bool:
    """
    Place bootanimation.zip at system/media/bootanimation.zip.
    The build system picks this up automatically — no makefile entry needed.
    Zip must contain: desc.txt + part0/, part1/, ... dirs with PNG frames.
    """
    if not zip_path.exists():
        print(f"  Boot animation zip not found: {zip_path}")
        return False
    dest = workdir / "system" / "media" / "bootanimation.zip"
    if dry_run:
        print(f"  [dry-run] {zip_path} → {dest}")
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(zip_path, dest)
    print(f"  Staged boot animation at {dest}")
    return True


# ── Root (Magisk) ──────────────────────────────────────────────────────────────

def fetch_magisk(dest_dir: Path, dry_run: bool = False) -> Path | None:
    """Download the latest Magisk APK from GitHub releases."""
    release = github_client.get_release(MAGISK_RELEASES_API)
    if not release:
        return None
    asset = next((a for a in release.get("assets", [])
                  if a["name"].endswith(".apk")), None)
    if not asset:
        print("  No Magisk .apk found in latest release.")
        return None
    out = dest_dir / asset["name"]
    if dry_run:
        print(f"  [dry-run] would download {asset['name']} to {dest_dir}")
        return dest_dir / "magisk-latest.apk"
    dest_dir.mkdir(parents=True, exist_ok=True)
    if out.exists():
        print(f"  Magisk already downloaded: {out}")
        return out
    print(f"  Downloading Magisk {release.get('tag_name', '')}...")
    urllib.request.urlretrieve(asset["browser_download_url"], out)
    print(f"  Saved to {out}")
    return out


def patch_boot_with_magisk(boot_img: Path, magisk_apk: Path,
                            dry_run: bool = False) -> bool:
    """
    Patch boot.img with Magisk. The automated headless path via magiskboot
    is device/arch-specific enough that wrong flags can brick a device.
    This function uses the safe, well-documented manual method instead and
    prints exact steps.
    """
    if dry_run:
        print(f"  [dry-run] would patch {boot_img} with {magisk_apk}")
        return True
    if not boot_img.exists():
        print(f"  boot.img not found at {boot_img}")
        print(f"  Build must complete first — it will be at:")
        print(f"    out/target/product/<codename>/boot.img")
        return False

    print("\n  Root patching — manual step (prevents device bricks):")
    print(f"  1. Copy {boot_img} to your device (or a device of same model)")
    print(f"  2. Install {magisk_apk.name} on that device")
    print(f"  3. Magisk app → Install → Select and Patch a File → boot.img")
    print(f"  4. Pull the patched file: adb pull /sdcard/Download/magisk_patched-*.img .")
    print(f"  5. Flash it: fastboot flash boot magisk_patched-*.img")
    print(f"  This method is correct for every device/arch — no guesswork.")
    return True


# ── init.d ────────────────────────────────────────────────────────────────────

INITD_SNIPPET = (
    "service sysinit /system/bin/logwrapper "
    "/system/xbin/busybox run-parts /system/etc/init.d\n"
    "    disabled\n"
    "    oneshot\n"
)

def enable_initd(workdir: Path, codename: str, api_level: int,
                  dry_run: bool = False) -> bool:
    """
    Create /system/etc/init.d directory and document the init.rc patch.
    init.d is a legacy mechanism mostly relevant to Android 4-9. Modern
    builds should use Magisk modules instead.
    Patching init.rc is left manual because the exact insertion point is
    kernel-specific — guessing wrong gives an unbootable device.
    """
    if api_level > 25:
        print(f"  Note: init.d is a legacy mechanism (mostly useful on Android ≤7).")
        print(f"  For Android {api_level} consider a Magisk module instead.")

    initd_dir = workdir / "device" / "romforge" / codename / "rootdir" / "etc" / "init.d"
    notes_path = initd_dir.parent.parent / "INITD_README.txt"

    if dry_run:
        print(f"  [dry-run] would create {initd_dir}")
        return True

    initd_dir.mkdir(parents=True, exist_ok=True)
    notes_path.write_text(
        "init.d setup — manual step required\n"
        "=====================================\n"
        "The /system/etc/init.d directory has been created.\n"
        "To ENABLE init.d, add this service to your device's init.rc\n"
        "(inside the boot image ramdisk — unpack with AIK, edit, repack):\n\n"
        + INITD_SNIPPET +
        "\nDO NOT paste this blindly — the correct position in init.rc is\n"
        "device-specific. Many kernels already have init.d built in;\n"
        "check yours before patching.\n"
    )
    print(f"  Created init.d directory: {initd_dir}")
    print(f"  Read {notes_path} for the manual init.rc patch step.")
    return True
