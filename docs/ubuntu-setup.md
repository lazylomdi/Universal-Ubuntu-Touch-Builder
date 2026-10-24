# Ubuntu setup

AndroidBuilder's Python CLI, ADB inspection, and ROM build orchestration are intended to work from a Linux environment. For full Android/AOSP/LineageOS source builds, use a supported Ubuntu release and follow the requirements for the exact ROM branch and device.

## Quick start

From the root of a cloned repository:

```bash
chmod +x setup_ubuntu.sh
./setup_ubuntu.sh
```

The default run is checks-only: it reports whether Git, Python 3, ADB, and curl are available, lists attached ADB devices if possible, prints the readiness CLI help, and runs the unit tests. It does not install packages unless you explicitly pass an installation option.

Install common tools and desktop UI runtime libraries (including D-Bus and Qt/X11 libraries used by PySide6) using Ubuntu's package manager:

```bash
./setup_ubuntu.sh --install-tools
```

Install common Android build packages as well (package availability varies by Ubuntu release and Android branch):

```bash
./setup_ubuntu.sh --install-build-deps
```

Install the Python requirements in a project-local virtual environment:

```bash
./setup_ubuntu.sh --install-python-deps
# Activate it in the current shell if desired:
source .venv/bin/activate
```

You can combine options, for example:

```bash
./setup_ubuntu.sh --install-tools --install-python-deps
```

The `--install-python-deps` option installs both `requirements.txt` and `requirements-ui.txt` into `.venv`, so the PySide6 UI dependencies are included. The `--install-tools` option installs D-Bus and common Qt/X11 runtime libraries as well as Git, Python, ADB, and other utilities. The script uses `sudo apt-get` only when an installation flag is supplied. Review the script before running it if you need to follow organization-specific package policies.

## Manual setup

For CLI-only use, the core pipeline primarily uses Python's standard library. The interactive menu requires the optional `questionary` dependency installed from `requirements.txt`. Useful Ubuntu packages include:

```bash
sudo apt update
sudo apt install git python3 python3-pip python3-venv adb curl rsync tmux
```

For Android source builds, the `requirements.txt` file lists a starting set of packages for Ubuntu 22.04. Newer or older Android branches may require different Java versions, libraries, disk space, and build instructions. The helper's `--install-build-deps` option installs a common baseline, not a guarantee that every ROM branch will build.

## Connect a phone (optional)

1. Enable Developer options and USB debugging on the phone.
2. Connect it using a USB data cable.
3. Run `adb devices -l`.
4. Unlock the phone and accept the USB debugging authorization prompt if it appears.
5. Run the readiness inspection only when you want to inspect the attached device:

   ```bash
   python3 romforge.py ut-check --inspect-device
   # For multiple devices:
   python3 romforge.py ut-check --inspect-device --serial YOUR_ADB_SERIAL
   ```

ADB inspection is opt-in and read-only. The setup script only lists devices; it does not root, unlock, reboot, erase, sideload, or flash a phone. On some Ubuntu installations, USB permissions or udev rules may need to be configured for your device.

## Tests and troubleshooting

```bash
python3 -m unittest discover -s tests -v
```

- **ADB command missing:** install Android SDK Platform-Tools or Ubuntu's `adb` package.
- **Device is unauthorized:** unlock it and accept the prompt on the phone.
- **No device appears:** try a known data cable, another USB port, and check USB debugging.
- **Build packages unavailable:** verify your Ubuntu release and the build instructions for the target Android branch.
- **Python package install errors:** use the included virtual environment rather than installing into system Python.

The setup helper does not clone/sync Android source trees, choose a device-specific manifest, fetch proprietary vendor blobs, or guarantee a successful ROM build. Those steps depend on the target device and ROM.
