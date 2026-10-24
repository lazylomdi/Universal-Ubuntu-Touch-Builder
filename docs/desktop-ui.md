# Desktop UI (Windows 10 and Ubuntu)

AndroidBuilder includes an optional PySide6 desktop interface. It reuses the existing `romforge.py` CLI instead of duplicating the build engine.

## Install and launch

Use Python 3.10+ and run these commands from the repository root.

### Ubuntu

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-ui.txt
python run_desktop_ui.py
```

On Ubuntu server/headless environments, a graphical desktop session is required. For actual ROM builds, use native Ubuntu or WSL2 with a supported GUI setup; WSLg availability depends on the Windows/WSL version.

### Windows 10

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-ui.txt
python run_desktop_ui.py
```

Install Git and Android Platform-Tools separately if you want repository operations and device inspection. ROM builds should run in a supported Ubuntu environment; a Windows UI does not make native Windows a supported AOSP build host.

## Included pages

- **Dashboard:** Python, Git, and ADB availability.
- **Build wizard:** Android version, codename, architecture, source, backend, work directory, jobs, optional source URLs, and a review dialog.
- **Build monitor:** asynchronous stdout/stderr display, process status, and a termination request with a warning.
- **Device manager:** ADB device listing and opt-in read-only device inspection through `romforge.py ut-check --inspect-device`.

## Safety and limitations

- The wizard starts in **dry-run** mode by default. Review the configuration and uncheck dry-run only when you're ready to run the actual pipeline.
- Build progress currently reflects process activity, not a precise percentage of Android compilation. The UI does not infer build success from log text; it uses the process exit code.
- Device inspection requires ADB authorization and uses the existing readiness checker. It does not root, unlock, reboot, erase, sideload, or flash a phone.
- The app launches the existing CLI using a process argument list (not a shell command string).
- This first UI implementation has not been executed on a real Windows 10 or Ubuntu desktop in this environment. Validate with the project tests and manually check each page on both operating systems before relying on it for builds.
