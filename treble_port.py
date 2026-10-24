"""
treble_port.py — ROM porting configuration generator.

Covers all real Android device configuration axes:

  Partition layout:
    A-only      = single slot, traditional partition table
    A/B         = dual-slot seamless updates (requires bootloader support)
    Virtual A/B = A/B via CoW snapshots, no doubled physical partitions (Android 11+)

  Vendor separation:
    Non-Treble  = vendor blobs in /system/vendor (pre-Oreo layout)
    Treble      = separate /vendor partition with VNDK HALs

  Root method:
    Legacy ramdisk   = separate boot ramdisk, /system mounted at /system
    SAR              = system-as-root, system partition IS the root fs
    Dynamic+ramdisk  = dynamic partitions force ramdisk back (Android 10+)

  Kernel:
    Custom   = device builds its own kernel from source
    Prebuilt = device uses a prebuilt kernel blob
    GKI      = Generic Kernel Image (Android 12+, Pixel-style)

  Architecture:
    armv7    = 32-bit ARM (no 2nd arch)
    arm64    = 64-bit ARM (with 32-bit secondary for app compat)
    x86      = 32-bit x86
    x86_64   = 64-bit x86 (rare outside emulators)

These axes combine into a matrix. The most common real-world configurations:

  Config A: Legacy (Android 4-7, armv7 or arm64)
    A-only, non-Treble, legacy ramdisk, custom kernel
    Examples: Samsung Galaxy S3/S4/S5, Nexus 4/5, OnePlus One

  Config B: Early Treble (Android 8-9, arm64)
    A-only, Treble, SAR or legacy ramdisk, custom kernel
    Examples: Pixel 2, OnePlus 5, most 2017-2018 flagships

  Config C: Modern non-GKI (Android 10-11, arm64)
    A/B or A-only, Treble, dynamic partitions, SAR+ramdisk, custom kernel
    Examples: Pixel 4, OnePlus 8, Samsung S20 (Exynos)

  Config D: GKI (Android 12+, arm64)
    Virtual A/B, Treble, dynamic partitions, GKI, AVB chained
    Examples: Pixel 6+, Samsung S22+ (Snapdragon), most 2022+ devices

  Config E: 32-bit non-Treble (Android 8-11 on armv7)
    A-only, non-Treble, legacy ramdisk, custom kernel
    Examples: Note 4 on LineageOS 15.1, Galaxy S3 on Android 9

Verified sources (July 2026):
  source.android.com/docs/core/architecture/partitions/system-as-root
  source.android.com/docs/core/ota/dynamic_partitions/implement
  source.android.com/docs/core/architecture/partitions/generic-boot
  xdaforums.com/t/guide-how-to-make-a-device-tree-for-your-phone.3698419
  xdaforums.com/t/info-android-device-partitions-and-filesystems.3586565
  android.googlesource.com/platform/external/avb (GKI AVB flags)
"""

from dataclasses import dataclass, field
from pathlib import Path


# ── Device profile dataclass ──────────────────────────────────────────────────

@dataclass
class DeviceProfile:
    # Identity
    codename:       str
    vendor:         str
    arch:           str          # armv7 | arm64 | x86 | x86_64

    # Partition layout
    ab_slots:       str          # "none" | "ab" | "virtual_ab"
    treble:         bool         # separate /vendor partition
    dynamic_parts:  bool         # super partition (Android 10+)
    sar:            bool         # system-as-root

    # Kernel type
    kernel_type:    str          # "custom" | "prebuilt" | "gki"
    kernel_version: str          # e.g. "4.9", "4.14", "5.10", "5.15"
    cpu_variant:    str          # cortex-a9, krait, cortex-a53, kryo, etc.

    # Android API
    android_api:    int          # e.g. 27, 29, 31, 34

    # Optional
    avb:            bool = True  # Android Verified Boot
    f2fs:           bool = False # f2fs userdata (vs ext4)
    bootimg_version: int = 1     # boot image header version (1, 2, or 4 for GKI)

    def config_name(self) -> str:
        """Human-readable configuration summary."""
        parts = [self.arch]
        parts.append("GKI" if self.kernel_type == "gki" else
                      "prebuilt-kernel" if self.kernel_type == "prebuilt" else
                      "custom-kernel")
        parts.append("treble" if self.treble else "non-treble")
        parts.append({"none": "A-only", "ab": "A/B", "virtual_ab": "VAB"}[self.ab_slots])
        if self.dynamic_parts:
            parts.append("dynparts")
        if self.sar:
            parts.append("SAR")
        return ", ".join(parts)


# ── BoardConfig.mk generator ──────────────────────────────────────────────────

def _arch_block(p: DeviceProfile) -> str:
    arch_map = {
        "armv7": (
            "TARGET_BOARD_SUFFIX        := _32\n"
            "TARGET_ARCH                := arm\n"
            "TARGET_ARCH_VARIANT        := armv7-a-neon\n"
            "TARGET_CPU_ABI             := armeabi-v7a\n"
            "TARGET_CPU_ABI2            := armeabi\n"
            f"TARGET_CPU_VARIANT         := {p.cpu_variant}\n"
            "# No secondary arch on pure 32-bit devices.\n"
            "# Remove any TARGET_2ND_* lines from the device tree.\n"
        ),
        "arm64": (
            "TARGET_ARCH                := arm64\n"
            "TARGET_ARCH_VARIANT        := armv8-a\n"
            "TARGET_CPU_ABI             := arm64-v8a\n"
            f"TARGET_CPU_VARIANT         := {p.cpu_variant}\n"
            "\n"
            "# 32-bit secondary arch (needed for 32-bit app compatibility)\n"
            "TARGET_2ND_ARCH            := arm\n"
            "TARGET_2ND_ARCH_VARIANT    := armv8-a\n"
            "TARGET_2ND_CPU_ABI         := armeabi-v7a\n"
            "TARGET_2ND_CPU_ABI2        := armeabi\n"
            f"TARGET_2ND_CPU_VARIANT     := {p.cpu_variant}\n"
        ),
        "x86_64": (
            "TARGET_ARCH                := x86_64\n"
            "TARGET_ARCH_VARIANT        := x86_64\n"
            "TARGET_CPU_ABI             := x86_64\n"
            "TARGET_2ND_ARCH            := x86\n"
            "TARGET_2ND_ARCH_VARIANT    := x86\n"
            "TARGET_2ND_CPU_ABI         := x86\n"
        ),
        "x86": (
            "TARGET_ARCH                := x86\n"
            "TARGET_ARCH_VARIANT        := x86\n"
            "TARGET_CPU_ABI             := x86\n"
        ),
    }
    return "# ── Architecture ──────────────────────────────────────────────────────────────\n" + arch_map.get(p.arch, "")


def _treble_block(p: DeviceProfile) -> str:
    if not p.treble:
        return (
            "# ── Non-Treble vendor layout ───────────────────────────────────────────────────\n"
            "# Vendor blobs stay in /system/vendor. No separate /vendor partition needed.\n"
            "# Do NOT set PRODUCT_FULL_TREBLE_OVERRIDE := true without a real /vendor partition.\n"
            "PRODUCT_FULL_TREBLE_OVERRIDE      := false\n"
            "TARGET_COPY_OUT_VENDOR            := system/vendor\n"
            "PRODUCT_TREBLE_LINKER_NAMESPACES  := false\n"
        )
    else:
        return (
            "# ── Treble vendor layout ────────────────────────────────────────────────────────\n"
            "# Requires a real /vendor partition in your device fstab.\n"
            "PRODUCT_FULL_TREBLE_OVERRIDE      := true\n"
            "TARGET_COPY_OUT_VENDOR            := vendor\n"
            "BOARD_VNDK_VERSION                := current\n"
            "PRODUCT_TREBLE_LINKER_NAMESPACES  := true\n"
        )


def _partition_block(p: DeviceProfile) -> str:
    lines = ["# ── Partition layout ────────────────────────────────────────────────────────────\n"]

    # Filesystem types
    fs = "f2fs" if p.f2fs else "ext4"
    lines.append(f"TARGET_USERIMAGES_USE_EXT4            := true\n")
    if p.f2fs:
        lines.append("TARGET_USERIMAGES_USE_F2FS            := true\n")
    lines.append(f"BOARD_SYSTEMIMAGE_PARTITION_TYPE      := ext4\n")
    if p.treble:
        lines.append(f"BOARD_VENDORIMAGE_FILE_SYSTEM_TYPE    := ext4\n")
    lines.append(f"BOARD_USERDATAIMAGE_FILE_SYSTEM_TYPE  := {fs}\n")
    lines.append("\n")

    # A/B
    if p.ab_slots in ("ab", "virtual_ab"):
        lines.append("# A/B seamless updates\n")
        lines.append("AB_OTA_UPDATER                        := true\n")
        lines.append("AB_OTA_PARTITIONS                    += \\\n")
        lines.append("    boot \\\n")
        if p.android_api >= 31:
            lines.append("    init_boot \\\n")
        lines.append("    system \\\n")
        if p.treble:
            lines.append("    vendor \\\n")
        if p.android_api >= 29:
            lines.append("    product \\\n")
        if p.android_api >= 31:
            lines.append("    system_ext \\\n")
        lines.append("    vbmeta\n\n")

    if p.ab_slots == "virtual_ab":
        lines.append("# Virtual A/B (Android 11+) — CoW snapshots, no doubled physical partitions\n")
        lines.append("ENABLE_VIRTUAL_AB                    := true\n")
        lines.append("BOARD_USES_RECOVERY_AS_BOOT          := true\n\n")

    # Dynamic partitions (Android 10+)
    if p.dynamic_parts:
        lines.append("# Dynamic partitions (super partition)\n")
        lines.append("# Source: source.android.com/docs/core/ota/dynamic_partitions/implement\n")
        lines.append("PRODUCT_USE_DYNAMIC_PARTITIONS       := true\n")
        lines.append("# Set BOARD_SUPER_PARTITION_SIZE to your device's super partition size.\n")
        lines.append("# Find it: adb shell cat /proc/partitions | grep super\n")
        lines.append("BOARD_SUPER_PARTITION_SIZE           := 9126805504  # example: 8.5GB\n")
        lines.append("BOARD_SUPER_PARTITION_GROUPS         := main\n")
        lines.append("BOARD_MAIN_SIZE                      := 9122611200  # SUPER_SIZE - 4MB overhead\n")
        lines.append("BOARD_MAIN_PARTITION_LIST            := system")
        if p.treble:
            lines.append(" vendor")
        if p.android_api >= 29:
            lines.append(" product")
        if p.android_api >= 31:
            lines.append(" system_ext")
        lines.append("\n\n")

    # SAR
    if p.sar and not p.dynamic_parts:
        lines.append("# System-as-root (SAR)\n")
        lines.append("# NOTE: Do NOT set this if PRODUCT_USE_DYNAMIC_PARTITIONS=true.\n")
        lines.append("# Source: source.android.com/docs/core/architecture/partitions/system-as-root\n")
        lines.append("BOARD_BUILD_SYSTEM_ROOT_IMAGE        := true\n\n")
    elif p.dynamic_parts:
        lines.append("# Dynamic partitions: SAR is handled by first-stage init ramdisk.\n")
        lines.append("# Do NOT set BOARD_BUILD_SYSTEM_ROOT_IMAGE — it conflicts with dynamic partitions.\n")
        lines.append("# Source: source.android.com/docs/core/ota/dynamic_partitions/implement\n\n")

    # Metadata partition (required for A/B + dynamic)
    if p.ab_slots != "none" and p.dynamic_parts:
        lines.append("BOARD_USES_METADATA_PARTITION        := true\n\n")

    return "".join(lines)


def _kernel_block(p: DeviceProfile) -> str:
    lines = ["# ── Kernel ───────────────────────────────────────────────────────────────────────\n"]

    if p.kernel_type == "gki":
        lines.append(f"# GKI (Generic Kernel Image) — Android 12+\n")
        lines.append(f"# Source: source.android.com/docs/core/architecture/partitions/generic-boot\n")
        lines.append(f"# System-as-root is NOT supported on GKI devices.\n")
        lines.append(f"# BOARD_BUILD_SYSTEM_ROOT_IMAGE must be empty.\n")
        lines.append(f"TARGET_NO_KERNEL                     := true\n")
        lines.append(f"BOARD_PREBUILT_BOOTIMAGE             := $(DEVICE_PATH)/prebuilt/boot.img\n")
        lines.append(f"BOARD_BOOTIMG_HEADER_VERSION         := {p.bootimg_version}\n")
        lines.append(f"BOARD_MKBOOTIMG_ARGS                += --header_version $(BOARD_BOOTIMG_HEADER_VERSION)\n")
        if p.android_api >= 33:
            lines.append(f"BOARD_PREBUILT_INIT_BOOT_IMAGE       := $(DEVICE_PATH)/prebuilt/init_boot.img\n")
    elif p.kernel_type == "prebuilt":
        lines.append(f"TARGET_PREBUILT_KERNEL               := $(DEVICE_PATH)/prebuilt/kernel\n")
        lines.append(f"BOARD_BOOTIMG_HEADER_VERSION         := {p.bootimg_version}\n")
        lines.append(f"BOARD_MKBOOTIMG_ARGS                += --header_version $(BOARD_BOOTIMG_HEADER_VERSION)\n")
        if p.arch in ("armv7", "arm64"):
            lines.append(f"TARGET_KERNEL_ARCH                   := {'arm' if p.arch == 'armv7' else 'arm64'}\n")
    else:
        # Custom kernel from source
        if p.arch == "armv7":
            lines.append("TARGET_KERNEL_ARCH                   := arm\n")
            lines.append("TARGET_KERNEL_HEADER_ARCH            := arm\n")
            lines.append("# Verify 32-bit kernel:\n")
            lines.append("# grep CONFIG_ARM64 out/.../KERNEL_OBJ/.config → must say: # CONFIG_ARM64 is not set\n")
        lines.append(f"BOARD_BOOTIMG_HEADER_VERSION         := {p.bootimg_version}\n")
        lines.append(f"BOARD_MKBOOTIMG_ARGS                += --header_version $(BOARD_BOOTIMG_HEADER_VERSION)\n")

    lines.append(f"# Set actual kernel version in your device tree:\n")
    lines.append(f"# TARGET_KERNEL_VERSION := {p.kernel_version}\n")
    return "".join(lines)


def _avb_block(p: DeviceProfile) -> str:
    if not p.avb:
        return (
            "# ── AVB disabled ────────────────────────────────────────────────────────────────\n"
            "BOARD_AVB_ENABLE                     := false\n"
        )
    lines = ["# ── Android Verified Boot (AVB) ─────────────────────────────────────────────────\n"]
    lines.append("BOARD_AVB_ENABLE                     := true\n")
    lines.append("BOARD_AVB_MAKE_VBMETA_IMAGE_ARGS     += --flags 3\n")
    lines.append("# --flags 3 disables AVB enforcement (HASHTREE_DISABLED | VERIFICATION_DISABLED).\n")
    lines.append("# Remove this line for production builds where you want AVB enforced.\n")
    if p.kernel_type == "gki" or p.android_api >= 31:
        lines.append("\n# Chained vbmeta for boot — allows independent OTA update of boot.img\n")
        lines.append("# Source: source.android.com/docs/core/architecture/partitions/generic-boot\n")
        lines.append("BOARD_AVB_BOOT_KEY_PATH              := external/avb/test/data/testkey_rsa4096.pem\n")
        lines.append("BOARD_AVB_BOOT_ALGORITHM             := SHA256_RSA4096\n")
        lines.append("BOARD_AVB_BOOT_ROLLBACK_INDEX        := $(PLATFORM_SECURITY_PATCH_TIMESTAMP)\n")
        lines.append("BOARD_AVB_BOOT_ROLLBACK_INDEX_LOCATION := 2\n")
        if p.android_api >= 33:
            lines.append("BOARD_AVB_INIT_BOOT_KEY_PATH         := external/avb/test/data/testkey_rsa2048.pem\n")
            lines.append("BOARD_AVB_INIT_BOOT_ALGORITHM        := SHA256_RSA2048\n")
            lines.append("BOARD_AVB_INIT_BOOT_ROLLBACK_INDEX   := $(PLATFORM_SECURITY_PATCH_TIMESTAMP)\n")
            lines.append("BOARD_AVB_INIT_BOOT_ROLLBACK_INDEX_LOCATION := 3\n")
    return "".join(lines)


def generate_boardconfig(p: DeviceProfile) -> str:
    sections = [
        f"# BoardConfig.mk additions — generated by romforge treble_port\n"
        f"# Profile: {p.config_name()}\n"
        f"# Device: {p.vendor} {p.codename}, Android API {p.android_api}\n\n",
        _arch_block(p) + "\n",
        _treble_block(p) + "\n",
        _partition_block(p),
        _kernel_block(p) + "\n",
        _avb_block(p),
    ]
    return "\n".join(sections)


# ── system.prop generator ─────────────────────────────────────────────────────

def generate_system_prop(p: DeviceProfile) -> str:
    lines = [
        f"# system.prop — generated by romforge treble_port\n"
        f"# Profile: {p.config_name()}\n\n"
    ]

    # Zygote — arch-dependent, not preset
    if p.arch == "armv7":
        lines.append("# 32-bit only device — zygote32 is mandatory. zygote64 will crash.\n")
        lines.append("ro.zygote=zygote32\n\n")
    else:
        lines.append("# 64-bit device with 32-bit secondary for app compat.\n")
        lines.append("ro.zygote=zygote64_32\n\n")

    # Treble flag (informational only)
    lines.append(f"# Informational only — cannot enable Treble via build.prop.\n")
    lines.append(f"ro.treble.enabled={'true' if p.treble else 'false'}\n\n")

    if p.treble:
        lines.append(f"ro.vndk.version=current\n")
        lines.append(f"ro.vendor.build.security_patch=2024-01-01  # update to actual vendor patch\n\n")

    # Dalvik heap — scaled by arch and typical RAM for device era
    if p.arch == "armv7":
        heap_size, heap_limit, heap_start = "256m", "128m", "8m"
    elif p.android_api >= 31:
        heap_size, heap_limit, heap_start = "512m", "256m", "16m"
    else:
        heap_size, heap_limit, heap_start = "384m", "192m", "8m"

    lines.append(f"# Dalvik heap — adjust heapsize/growthlimit based on device RAM\n")
    lines.append(f"dalvik.vm.heapsize={heap_size}\n")
    lines.append(f"dalvik.vm.heapgrowthlimit={heap_limit}\n")
    lines.append(f"dalvik.vm.heapstartsize={heap_start}\n")
    lines.append(f"dalvik.vm.heapminfree=512k\n")
    lines.append(f"dalvik.vm.heapmaxfree=8m\n")
    lines.append(f"dalvik.vm.heaptargetutilization=0.75\n\n")

    # ISA variant — arch-specific
    if p.arch == "armv7":
        lines.append(f"dalvik.vm.isa.arm.variant={p.cpu_variant}\n")
        lines.append(f"dalvik.vm.isa.arm.features=default\n\n")
    else:
        lines.append(f"dalvik.vm.isa.arm64.variant={p.cpu_variant}\n")
        lines.append(f"dalvik.vm.isa.arm64.features=default\n")
        lines.append(f"dalvik.vm.isa.arm.variant={p.cpu_variant}\n")
        lines.append(f"dalvik.vm.isa.arm.features=default\n\n")

    # dex2oat thread scaling
    dex_threads = "2" if p.arch == "armv7" else "4"
    lines.append(f"dalvik.vm.dex2oat-threads={dex_threads}\n")
    lines.append(f"dalvik.vm.boot-dex2oat-threads={dex_threads}\n\n")

    # HWC — older devices use HWC1, modern use HWC2
    if p.android_api < 28:
        lines.append("debug.sf.hw=1\ndebug.egl.hw=1\npersist.sys.ui.hw=1\n\n")
    else:
        lines.append("# HWC2 is default on Android 8+; don't set legacy sf/egl flags.\n\n")

    # Dynamic partitions / VAB
    if p.dynamic_parts:
        lines.append("ro.boot.dynamic_partitions=true\n")
    if p.ab_slots == "virtual_ab":
        lines.append("ro.virtual_ab.enabled=true\n")

    return "".join(lines)


# ── Product makefile fragment ─────────────────────────────────────────────────

def generate_product_mk(p: DeviceProfile) -> str:
    lines = [
        f"# device_port.mk — generated by romforge treble_port\n"
        f"# Profile: {p.config_name()}\n\n"
    ]

    if not p.treble:
        lines.append("PRODUCT_FULL_TREBLE_OVERRIDE := false\n\n")

    if p.android_api >= 29:
        lines.append(f"PRODUCT_SHIPPING_API_LEVEL := {p.android_api}\n")

    if p.dynamic_parts:
        lines.append("PRODUCT_USE_DYNAMIC_PARTITIONS := true\n")

    if p.ab_slots in ("ab", "virtual_ab"):
        lines.append("$(call inherit-product, $(SRC_TARGET_DIR)/product/virtual_ab_ota.mk)\n"
                     if p.ab_slots == "virtual_ab" else
                     "$(call inherit-product, $(SRC_TARGET_DIR)/product/ab_ota_updates.mk)\n")

    if p.arch == "armv7":
        lines.append("# 32-bit only\n")
        lines.append("PRODUCT_PROPERTY_OVERRIDES += ro.zygote=zygote32\n")
        lines.append("$(call inherit-product, $(SRC_TARGET_DIR)/product/core_32.mk)\n")

    return "".join(lines)


# ── README generator ──────────────────────────────────────────────────────────

def generate_readme(p: DeviceProfile) -> str:
    warnings = []

    if p.arch == "armv7" and p.treble:
        warnings.append(
            "⚠ armv7 + Treble: this combination requires a separate /vendor partition "
            "physically on the device. Verify with: adb shell cat /proc/mounts | grep vendor. "
            "If no result, use non-Treble instead."
        )

    if p.sar and p.dynamic_parts:
        warnings.append(
            "⚠ SAR + dynamic partitions: these are mutually exclusive. "
            "BOARD_BUILD_SYSTEM_ROOT_IMAGE must be empty when PRODUCT_USE_DYNAMIC_PARTITIONS=true. "
            "Source: source.android.com/docs/core/ota/dynamic_partitions/implement"
        )

    if p.kernel_type == "gki" and p.sar:
        warnings.append(
            "⚠ GKI + SAR: GKI devices do not support system-as-root. "
            "BOARD_BUILD_SYSTEM_ROOT_IMAGE must be empty on GKI devices. "
            "Source: source.android.com/docs/core/architecture/partitions/generic-boot"
        )

    if p.android_api >= 29 and not p.dynamic_parts and p.ab_slots == "none":
        warnings.append(
            "ℹ Android 10+ without dynamic partitions: valid for devices upgrading "
            "from Android 9, but new devices launching with Android 10 are required "
            "to use dynamic partitions."
        )

    warn_text = "\n".join(f"  {w}" for w in warnings)

    return f"""romforge — porting configuration for {p.vendor} {p.codename}
Profile: {p.config_name()}
Android API: {p.android_api}
{'='*70}

{('WARNINGS:\n' + warn_text + '\n') if warnings else ''}
CRITICAL: ro.treble.enabled in build.prop does NOTHING.
  Treble requires a real /vendor partition — not a property flag.
  Source: xdaforums.com/t/enable-treble-support-for-unsupported-device.4000391

HOW TO INTEGRATE
  1. BoardConfig_additions.mk → merge into device/vendor/codename/BoardConfig.mk
     (do NOT replace the whole file — merge the relevant sections)
  2. system.prop             → merge into device/vendor/codename/system.prop
     or add: TARGET_SYSTEM_PROP := $(DEVICE_PATH)/system.prop
  3. device_port.mk          → add to product makefile:
     $(call inherit-product, $(DEVICE_PATH)/device_port.mk)

ADJUST BEFORE USING
  cpu_variant ({p.cpu_variant}): must match your actual SoC CPU core.
    Run on device: adb shell cat /proc/cpuinfo | grep "CPU part"
    Common values: cortex-a7, cortex-a9, cortex-a15, cortex-a53,
                   cortex-a55, cortex-a57, krait, kryo, kryo385

  Dalvik heap sizes: adjust based on actual device RAM.
    Typical: 2GB RAM → heapsize=256m, 4GB → 384m, 6GB+ → 512m

{'DYNAMIC PARTITIONS' + chr(10) + '  BOARD_SUPER_PARTITION_SIZE: find yours with:' + chr(10) + '    adb shell cat /proc/partitions | grep super' + chr(10) + '  The BOARD_MAIN_SIZE must be SUPER_PARTITION_SIZE minus 4MB overhead.' if p.dynamic_parts else ''}

COMMON BOOTLOOP CAUSES
  - Wrong cpu_variant: illegal instruction crash in native code
  - ro.zygote=zygote64 on armv7: immediate bootloop
  - PRODUCT_FULL_TREBLE_OVERRIDE=true without a /vendor partition: bootloop
  - BOARD_BUILD_SYSTEM_ROOT_IMAGE=true with dynamic partitions: build error
  - Missing blobs in /system/vendor (non-Treble): HAL not found errors
  - Wrong BOARD_SUPER_PARTITION_SIZE: OTA/flash failure on dynamic partition devices
  - SELinux denials: adb logcat | grep avc → add allow rules, don't set permissive

TESTING ORDER
  1. Flash recovery first — confirms kernel + ramdisk are correct
  2. First system boot — expect multiple reboots (dex2oat compiling)
  3. Bootloop: adb logcat -b kernel → look at last line before reboot
  4. "linker: CANNOT LINK EXECUTABLE": blob in wrong path (/system/vendor vs /vendor)
  5. Camera/audio/modem broken but OS boots: vendor blobs missing or mismatched
"""


# ── Profile presets ───────────────────────────────────────────────────────────

PRESETS = {
    "legacy-armv7": DeviceProfile(
        codename="device", vendor="vendor", arch="armv7",
        ab_slots="none", treble=False, dynamic_parts=False, sar=False,
        kernel_type="custom", kernel_version="3.18", cpu_variant="cortex-a9",
        android_api=27, avb=False, bootimg_version=1,
    ),
    "early-treble-arm64": DeviceProfile(
        codename="device", vendor="vendor", arch="arm64",
        ab_slots="none", treble=True, dynamic_parts=False, sar=True,
        kernel_type="custom", kernel_version="4.9", cpu_variant="cortex-a53",
        android_api=28, avb=True, bootimg_version=1,
    ),
    "modern-ab-arm64": DeviceProfile(
        codename="device", vendor="vendor", arch="arm64",
        ab_slots="ab", treble=True, dynamic_parts=True, sar=False,
        kernel_type="custom", kernel_version="4.19", cpu_variant="cortex-a76",
        android_api=30, avb=True, bootimg_version=2,
    ),
    "gki-vab-arm64": DeviceProfile(
        codename="device", vendor="vendor", arch="arm64",
        ab_slots="virtual_ab", treble=True, dynamic_parts=True, sar=False,
        kernel_type="gki", kernel_version="5.15", cpu_variant="kryo",
        android_api=33, avb=True, bootimg_version=4,
    ),
    "32bit-modern": DeviceProfile(
        codename="device", vendor="vendor", arch="armv7",
        ab_slots="none", treble=False, dynamic_parts=False, sar=False,
        kernel_type="custom", kernel_version="4.4", cpu_variant="cortex-a7",
        android_api=30, avb=False, bootimg_version=1,
    ),
}


# ── Detection ─────────────────────────────────────────────────────────────────

def detect_profile(codename: str = "") -> dict:
    """
    Read device configuration from a connected ADB device (read-only).
    Returns a dict suitable for building a DeviceProfile.
    """
    import shutil, subprocess

    empty = {
        "treble": None, "ab_slots": None, "dynamic_parts": None,
        "sar": None, "arch": None, "android_api": None,
        "kernel_version": None, "avb": None, "bootimg_version": None,
        "cpu_variant": None, "error": None,
    }

    if not shutil.which("adb"):
        empty["error"] = "adb not found on PATH"
        return empty

    def prop(k):
        try:
            r = subprocess.run(["adb", "shell", "getprop", k],
                               capture_output=True, text=True, timeout=10)
            return r.stdout.strip()
        except Exception:
            return ""

    def shell(cmd):
        try:
            r = subprocess.run(["adb", "shell"] + cmd.split(),
                               capture_output=True, text=True, timeout=10)
            return r.stdout.strip()
        except Exception:
            return ""

    try:
        subprocess.run(["adb", "start-server"], capture_output=True, timeout=10)
        devices = subprocess.run(["adb", "devices"], capture_output=True,
                                  text=True, timeout=10).stdout
        if "\tdevice" not in devices:
            empty["error"] = "No device connected (USB debugging on?)"
            return empty

        abi         = prop("ro.product.cpu.abi")
        api_str     = prop("ro.build.version.sdk")
        ab_result   = prop("ro.build.ab_update")
        vab_result  = prop("ro.virtual_ab.enabled")
        dyn_result  = prop("ro.boot.dynamic_partitions")
        avb_result  = prop("ro.boot.verifiedbootstate")
        kern        = shell("uname -r")
        mounts      = shell("cat /proc/mounts")

        arch = ("armv7" if "armeabi" in abi and "arm64" not in abi else
                "arm64" if "arm64" in abi else
                "x86_64" if "x86_64" in abi else
                "x86" if "x86" in abi else "unknown")

        ab_slots = ("virtual_ab" if vab_result == "true" else
                    "ab" if ab_result == "true" else "none")

        vendor_separate = any(
            "/vendor" in ln and "/system/vendor" not in ln
            for ln in mounts.splitlines()
        )
        sar = any("/system" not in ln and "/" in ln and "rootfs" in ln
                  for ln in mounts.splitlines())

        # Kernel version major
        kver = ".".join(kern.split(".")[:2]) if kern else "unknown"

        # Boot image header version — infer from Android API
        try:
            api = int(api_str)
        except ValueError:
            api = 0
        bver = (4 if api >= 33 else 2 if api >= 29 else 1)

        return {
            "treble":         vendor_separate,
            "ab_slots":       ab_slots,
            "dynamic_parts":  dyn_result == "true",
            "sar":            sar,
            "arch":           arch,
            "android_api":    api,
            "kernel_version": kver,
            "avb":            avb_result not in ("", "disabled"),
            "bootimg_version": bver,
            "cpu_variant":    None,  # can't read from props reliably
            "error":          None,
        }
    except Exception as e:
        empty["error"] = str(e)
        return empty


def print_detected(d: dict) -> None:
    if d.get("error"):
        print(f"  Detection failed: {d['error']}")
        return
    print(f"  Architecture    : {d['arch']}")
    print(f"  Android API     : {d['android_api']}")
    print(f"  Treble          : {'yes' if d['treble'] else 'NO — blobs in /system/vendor'}")
    print(f"  Slots           : {d['ab_slots']}")
    print(f"  Dynamic parts   : {'yes' if d['dynamic_parts'] else 'no'}")
    print(f"  System-as-root  : {'yes' if d['sar'] else 'no'}")
    print(f"  Kernel version  : {d['kernel_version']}")
    print(f"  AVB             : {'yes' if d['avb'] else 'no'}")
    print(f"  Boot img header : v{d['bootimg_version']}")


# ── Main public API ───────────────────────────────────────────────────────────

def generate_all(p: DeviceProfile, workdir: Path, dry_run: bool = False) -> dict:
    """
    Generate all port files. Returns {filename: content}.
    Writes to workdir/treble_port/ unless dry_run.
    """
    files = {
        "BoardConfig_additions.mk": generate_boardconfig(p),
        "system.prop":              generate_system_prop(p),
        "device_port.mk":          generate_product_mk(p),
        "PORTING_README.txt":       generate_readme(p),
    }

    if dry_run:
        print(f"\n  Profile : {p.config_name()}")
        print(f"  [dry-run] would write to {workdir / 'treble_port'}/")
        for fn, content in files.items():
            print(f"    {fn:<35} ({len(content.splitlines())} lines)")
        return files

    out = workdir / "treble_port"
    out.mkdir(parents=True, exist_ok=True)
    for fn, content in files.items():
        (out / fn).write_text(content)
        print(f"  → {out / fn}")
    print(f"\n  Profile : {p.config_name()}")
    print(f"  Read PORTING_README.txt before editing your device tree.")
    return files


CPU_VARIANT_HINTS = {
    "snapdragon 200": "cortex-a7",  "snapdragon 400": "cortex-a7",
    "snapdragon 600": "krait",       "snapdragon 800": "krait",
    "snapdragon 808": "cortex-a57",  "snapdragon 810": "cortex-a57",
    "snapdragon 820": "kryo",        "snapdragon 821": "kryo",
    "snapdragon 835": "kryo280",     "snapdragon 845": "kryo385",
    "snapdragon 855": "kryo485",     "snapdragon 865": "kryo585",
    "snapdragon 888": "kryo680",     "snapdragon 8 gen": "kryo",
    "exynos 3":       "cortex-a9",   "exynos 4":       "cortex-a9",
    "exynos 5":       "cortex-a15",  "exynos 7580":    "cortex-a53",
    "exynos 7870":    "cortex-a53",  "exynos 9810":    "mongoose",
    "mt6580":         "cortex-a7",   "mt6592":         "cortex-a7",
    "mt6752":         "cortex-a53",  "mt6795":         "cortex-a53",
    "helio p":        "cortex-a53",  "helio g":        "cortex-a75",
    "dimensity":      "cortex-a78",  "kirin 960":      "cortex-a73",
    "kirin 970":      "cortex-a73",  "kirin 980":      "cortex-a76",
}

def suggest_cpu_variant(soc: str) -> str:
    s = soc.lower()
    for key, val in CPU_VARIANT_HINTS.items():
        if key in s:
            return val
    return "cortex-a53"
