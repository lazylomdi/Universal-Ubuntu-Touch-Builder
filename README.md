# Universal Ubuntu Touch Builder

**A toolkit for investigating Android devices and preparing the work needed to build Ubuntu Touch ports.**

Universal Ubuntu Touch Builder (also called **AndroidBuilder / ROMForge** in parts of the codebase) aims to make the complex process of exploring Android device compatibility and preparing ROM-porting work easier to understand and repeat. It combines command-line tools and a desktop interface for device inspection, readiness reports, repository discovery, and existing ROM-building workflows.

> **Project status: experimental / under development.** This project does not guarantee that Ubuntu Touch can be built or run on any particular phone. Detecting a device or finding a kernel/device-tree repository is not proof of compatibility. Support must be established with device-specific evidence and testing.

## Why this project exists

Ubuntu Touch ports require device-specific information, compatible kernel and hardware support, source code, build tools, and careful testing. That information can be difficult to collect, especially for people new to Android ROM development.

This project is intended to bring useful checks and workflows into one place so users can:

- identify an Android device and collect information it exposes;
- assess what is known, unknown, or still needs research before attempting a port;
- produce readable Markdown and JSON reports for later review;
- discover candidate source repositories when online search is enabled;
- use a desktop UI or CLI, depending on their preference;
- run existing ROMForge build-related workflows and setup checks;
- approach device modification cautiously, without confusing research results with proof that a port works.

The long-term goal is a reusable, multi-device toolkit. Each device still needs its own verified profile, sources, compatibility analysis, and testing.

## Main features

### 1. Device inspection and readiness reports

The readiness checker can run without a phone connected when you supply basic device details. With Android Debug Bridge (ADB) configured, it can optionally inspect a connected device and collect information available through read-only queries.

Reports can distinguish candidate information from unknown or unverified properties. An online search can find possible GitHub repositories, but repository metadata is treated as a lead to investigate—not as compatibility proof.

### 2. Desktop application

The PySide6 desktop UI provides a device-first workflow:

- view Android devices visible to ADB;
- select a device to inspect it;
- read a plain-language summary and detailed report;
- copy or export a report;
- view connection help and dependency availability.

The UI is a front end to the project's existing commands. It does not itself guarantee a successful ROM build.

### 3. Command-line tools

ROMForge exposes CLI commands for readiness checks and existing ROM-builder workflows. Run `python3 romforge.py --help` to see the commands and options available in your checkout.

### 4. Setup and validation helpers

The repository includes setup helpers and project tests. These can help check prerequisites and install selected dependencies, but a successful setup check is not the same as having a complete Android build environment or a working device port.

## Quick start

### Requirements

- Python 3
- Git, if you are cloning the repository
- For connected-phone inspection: Android SDK Platform-Tools (ADB), a USB data cable, and USB debugging enabled on the phone
- For the desktop interface: the dependencies listed in `requirements-ui.txt`
- For full Android ROM builds: a suitably configured Linux environment and the external tools and source trees required by the chosen build workflow. Ubuntu or Ubuntu under WSL2 is recommended for Windows users.

### Run a readiness check without a connected phone

From the project root:

~~~bash
python3 romforge.py ut-check \
  --manufacturer Sony --model "Xperia R1" --ram-gb 2 \
  --json-out reports/xperia-r1.json \
  --markdown-out reports/xperia-r1.md
~~~

Replace the example device details with the device you want to investigate. Supplied details are inputs to the assessment; they do not prove port compatibility.

### Inspect a connected Android phone

1. Install Android SDK Platform-Tools and make sure `adb` is on your `PATH`.
2. Enable Developer options and USB debugging on the phone.
3. Connect the phone, unlock it, and accept the USB debugging prompt only if you trust the computer.
4. Run:

~~~bash
python3 romforge.py ut-check --inspect-device
~~~

If more than one device is connected:

~~~bash
python3 romforge.py ut-check --inspect-device --serial YOUR_ADB_SERIAL
~~~

Device inspection is intended to be **opt-in and read-only**. It queries device information exposed through ADB; it does not root, unlock, erase, or flash the phone. Review the command and its options before running it.

### Launch the desktop UI

Install the UI requirements and start the application:

~~~bash
python3 -m pip install -r requirements-ui.txt
python3 run_desktop_ui.py
~~~

If you use a virtual environment, activate it first and install dependencies inside that environment. You can also launch with:

~~~bash
python3 -m desktop_ui.app
~~~

### Ubuntu setup checks

~~~bash
chmod +x setup_ubuntu.sh
./setup_ubuntu.sh
~~~

Optional installation steps are explicit:

~~~bash
./setup_ubuntu.sh --install-tools
./setup_ubuntu.sh --install-build-deps
./setup_ubuntu.sh --install-python-deps
~~~

Review the setup documentation before using installation options.

### Windows

Run the prerequisite checks from PowerShell:

~~~powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup_windows.ps1
~~~

See the Windows setup documentation before using switches that install tools or request WSL2. WSL2 Ubuntu is recommended for actual Android ROM build workflows.

## Safety and compatibility

Please read this section before working with a physical device:

- **A detected phone is not a supported port.** Device identification only establishes what the device reports.
- **A candidate source repository is not proof.** Kernel, device-tree, vendor, firmware, and porting sources must be checked for the exact device variant and Android base.
- **Unknown means unknown.** Treat incomplete evidence as a reason to investigate further, not as a positive compatibility result.
- **Do not flash based on a readiness report.** Bootloader unlocking, repartitioning, recovery installation, and flashing can erase data or make a device unusable. Follow verified, device-specific instructions and maintain a recovery plan.
- **Keep claims evidence-based.** A build artifact is not necessarily bootable, and a booting system is not necessarily a functional port. Hardware features require testing on the actual device.

## Documentation

The repository's docs directory contains additional guidance. Start with the documents relevant to your workflow, including:

- [Device readiness](docs/device-readiness.md)
- [Ubuntu Touch porting notes](docs/ubuntu-touch-porting.md)
- [Desktop UI instructions](docs/desktop-ui.md)
- [Ubuntu setup](docs/ubuntu-setup.md)
- [Windows setup](docs/windows-setup.md)
- [Repository audit](docs/repository-audit.md)

If a referenced document is not present in your checkout, consult the available files in docs for the corresponding guidance.

## Run the tests

From the project root:

~~~bash
python3 -m unittest discover -s tests -v
~~~

Run tests before relying on changes or reporting a workflow as working. Results may vary by operating system, installed dependencies, and connected hardware.

## Contributing

Issues, reproducible bug reports, documentation improvements, and carefully evidenced device research are useful contributions. When reporting a device, include the exact manufacturer/model/device identifiers, Android version and build fingerprint where available, relevant logs, source links, and what has or has not been tested. Remove personal information and secrets from logs before sharing them.

Please distinguish observed facts from assumptions, and do not describe a device as supported unless there is evidence for the relevant build and hardware functionality.

## Project direction

The long-term direction is to make porting research and preparation more consistent across devices through reusable device profiles, evidence-based readiness checks, source discovery, repeatable build workflows, and artifact validation. Universal tooling can organize and automate common work, but it cannot eliminate the device-specific engineering and testing required for each Ubuntu Touch port.

---

**In short:** this project helps you investigate an Android device and organize the work toward an Ubuntu Touch port. It is a development toolkit—not a one-click guarantee of a working Ubuntu Touch ROM.
