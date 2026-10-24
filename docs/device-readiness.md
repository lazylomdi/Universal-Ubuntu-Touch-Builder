# Device readiness assessment

Run an offline report without a connected phone:

```bash
python3 romforge.py ut-check \
  --manufacturer Sony --model "Xperia R1" --ram-gb 2 \
  --json-out reports/xperia-r1.json \
  --markdown-out reports/xperia-r1.md
```

Add `--online` to search GitHub's repository API for candidate sources. This is optional; the default makes no network request. Results are unverified candidates, not proof of device compatibility. Optional inputs include `--codename`, `--android-version`, `--kernel-version`, and `--bootloader-unlock yes|no|unknown`. Omitted values remain unknown. Reports are preliminary evidence inventories, not compatibility certifications. A candidate source repository is not proof of a successful build; a successful build is not proof of bootability or working radio, graphics, Wi-Fi, camera, audio, sensors, or power management.

Statuses are `VERIFIED`, `CANDIDATE`, `UNKNOWN`, `BLOCKED`, and `NOT_APPLICABLE`. This initial checker uses `CANDIDATE` for user-provided data and `UNKNOWN` for facts without independent evidence. It does not yet mark device-specific facts `VERIFIED`.

## Inspect a connected phone on Windows 10

1. Install Android SDK Platform-Tools and make sure `adb.exe` is on `PATH`.
2. Enable Developer options and USB debugging on the Android phone.
3. Connect the phone by USB and accept the USB debugging authorization prompt.
4. Run:

```powershell
python romforge.py ut-check --inspect-device
```

If multiple authorized phones are connected, first run `adb devices -l` and pass the selected serial with `--inspect-device --serial SERIAL`. Inspection only runs read-only ADB queries and is opt-in. If ADB is missing, the phone is disconnected, unauthorized, offline, or multiple devices make selection ambiguous, the report explains the issue instead of guessing.

Available properties can include manufacturer, model, device codename, Android version, kernel release, RAM, build fingerprint, and CPU ABI. Some properties may be missing or vendor-specific. This does not establish bootloader unlock eligibility, verify source repositories, build Ubuntu Touch, or test hardware. No flashing, rooting, unlocking, or device modifications are performed.
