# AndroidBuilder / romforge

Android ROM build and device-tree discovery tools, with an offline-first Ubuntu Touch readiness assessment.

## Ubuntu Touch readiness check

```bash
python3 romforge.py ut-check \
  --manufacturer Sony --model "Xperia R1" --ram-gb 2 \
  --json-out reports/xperia-r1.json \
  --markdown-out reports/xperia-r1.md
```

The checker does not require a connected phone. On Windows 10, install Android SDK Platform-Tools, add its folder to `PATH`, enable USB debugging on the phone, connect by USB, and accept the authorization prompt. Then run:

```powershell
python romforge.py ut-check --inspect-device
# If more than one phone is connected:
python romforge.py ut-check --inspect-device --serial YOUR_ADB_SERIAL
```

Device inspection is opt-in and read-only: it runs `adb devices -l`, `getprop`, reads `/proc/meminfo`, and queries `uname -r`. It does not root, unlock, flash, or change phone settings. Add `--online` to search GitHub for candidate repositories; network failures are reported and repository metadata is never treated as compatibility proof. User-provided facts are marked as candidates, unknown properties remain unknown, and no report claims that a port builds or boots. See [device readiness](docs/device-readiness.md), [porting notes](docs/ubuntu-touch-porting.md), and the [repository audit](docs/repository-audit.md).

## Desktop UI (Windows 10 and Ubuntu)

AndroidBuilder includes a PySide6 desktop application for a device-first workflow. The dashboard lists Android devices visible to ADB as selectable phone tiles. Select a tile to open its dedicated device page; the app automatically runs a read-only inspection and displays a plain-language summary plus the detailed Markdown report. The device page also provides **Copy report** and **Export report** actions. Use **Home** to return to the dashboard and **Help** for connection instructions and dependency availability checks.

### Launch

Install the UI dependencies and start the application from the repository root:

```bash
python3 -m pip install -r requirements-ui.txt
python3 run_desktop_ui.py
```

For an existing virtual environment, activate it first and use `python -m pip install -r requirements-ui.txt`, then launch with `python -m desktop_ui.app` or `python run_desktop_ui.py`.

On Windows PowerShell:

```powershell
py -3 -m pip install -r requirements-ui.txt
py -3 run_desktop_ui.py
```

### Connect and inspect a phone

1. Install Android SDK Platform-Tools and ensure `adb` is available on `PATH`.
2. On the phone, enable Developer options and USB debugging.
3. Connect using a USB data cable, unlock the phone, and accept the USB debugging authorization prompt only if you trust the computer.
4. Open AndroidBuilder and refresh the dashboard device list.
5. Select the phone tile. The dedicated details page should automatically start the read-only inspection.

The Help dialog lists common dependency availability. A tool marked available is discoverable by the running application; this does not mean every build backend is fully configured. Docker and GitHub CLI are optional and only relevant to corresponding workflows.

### Safety and compatibility limits

Device inspection reads information exposed by ADB. It does **not** unlock, root, reboot, erase, or flash the phone. A detected device and its reported properties are not proof of Ubuntu Touch port support, bootability, or working hardware. Treat `UNKNOWN` and `Not enough information` as incomplete evidence, not as a positive or negative compatibility verdict.

The desktop UI is a front end to existing ROMForge commands; it does not itself guarantee that a ROM can be built. Full Android ROM builds should be performed in a suitably configured Linux environment (Ubuntu/WSL2 is recommended for Windows users). See [desktop UI instructions](docs/desktop-ui.md), [device readiness](docs/device-readiness.md), and [Windows setup](docs/windows-setup.md).

## Ubuntu setup

For a native Ubuntu host, run the checks-only helper from the repository root:

```bash
chmod +x setup_ubuntu.sh
./setup_ubuntu.sh
```

Optional install steps are explicit:

```bash
./setup_ubuntu.sh --install-tools
./setup_ubuntu.sh --install-build-deps
./setup_ubuntu.sh --install-python-deps
```

See [Ubuntu setup instructions](docs/ubuntu-setup.md) for package notes, virtual-environment use, ADB device inspection, and limitations. The helper does not sync ROM sources or modify a connected phone.

## Windows 10 setup automation

From PowerShell in the repository folder, run the prerequisite checks:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup_windows.ps1
```

Optional switches can attempt to install Git/Python/ADB with WinGet, request WSL2 Ubuntu installation, or install Python requirements and run project checks:

```powershell
.\setup_windows.ps1 -InstallTools
.\setup_windows.ps1 -InstallWSL
.\setup_windows.ps1 -InstallPythonDependencies
```

Review [Windows setup instructions](docs/windows-setup.md) before using installation switches. WSL2 Ubuntu is recommended for actual Android ROM builds; the script does not restart the PC and does not modify or flash the phone.

## Existing ROM builder

Run `python3 romforge.py --help` for CLI usage. The interactive menu requires `questionary`; see `requirements.txt` for dependencies and external build tools.

## Tests

```bash
python3 -m unittest discover -s tests -v
```
