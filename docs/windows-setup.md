# Windows 10 development setup

AndroidBuilder's Python CLI and ADB-based phone inspection can run on Windows. Full Android ROM source builds are best run inside **WSL2 with Ubuntu**; native Windows is not the supported environment for the usual AOSP/LineageOS Linux build toolchain.

## Quick start

1. Install or update Git for Windows and Python 3.10+ if not already installed.
2. Open PowerShell in the cloned AndroidBuilder repository.
3. Run the checks-only setup:

   ```powershell
   Set-ExecutionPolicy -Scope Process Bypass
   .\setup_windows.ps1
   ```

   The execution-policy command applies only to the current PowerShell process. If your organization manages execution policy, follow its policy instead.

4. To let the script attempt installation of Git, Python 3.12, and Android Platform-Tools via WinGet:

   ```powershell
   .\setup_windows.ps1 -InstallTools
   ```

5. To explicitly request WSL installation with Ubuntu 22.04:

   ```powershell
   .\setup_windows.ps1 -InstallWSL
   ```

   WSL installation may require an elevated PowerShell, a supported Windows 10 build, a restart, or additional steps from Microsoft. The script does not restart the computer automatically.

6. To install the project's optional Python requirements (including the interactive TUI dependency) and run the CLI/tests:

   ```powershell
   .\setup_windows.ps1 -InstallPythonDependencies
   ```

   Or combine switches, for example `-InstallTools -InstallWSL -InstallPythonDependencies`. The script reports install/test failures but does not claim they succeeded when a command returns an error.

## What it checks

- Git, Python, ADB, and WSL availability.
- Python/Git/ADB versions when available.
- Connected ADB devices, if ADB is installed.
- The readiness CLI help output and unit tests when run from the repository folder.

## WSL2 build environment

After WSL2 is installed, complete Ubuntu's first-run setup and use the Linux terminal for ROM builds. Keep source trees inside the WSL Linux filesystem (for example `~/src/AndroidBuilder`), not under `/mnt/c`, for better Linux filesystem performance. Android source builds can require very large disk space and substantial RAM; check the requirements for the exact Android/LineageOS branch before syncing sources.

The Windows setup script does not install every Android build dependency inside Ubuntu automatically, change BIOS virtualization settings, resize disks, or configure a specific ROM source branch. Those steps vary by Windows build, hardware, and target Android version.

## Phone safety

ADB inspection is read-only and opt-in. This setup script only lists devices and never issues unlock, root, reboot, erase, sideload, or flash commands. If the phone shows as `unauthorized`, unlock it and accept the USB debugging prompt.

## Troubleshooting

- **WinGet unavailable:** install Git/Python/Platform-Tools from their official links manually.
- **ADB not recognized:** add the extracted Platform-Tools directory containing `adb.exe` to your user or system `PATH`, then open a new terminal.
- **Phone missing:** use a data-capable cable, choose the phone's file-transfer mode if needed, enable USB debugging, and check the device manufacturer's USB driver for Windows.
- **WSL install fails:** follow Microsoft's current [WSL installation guide](https://learn.microsoft.com/windows/wsl/install) and verify your Windows 10 version supports the requested WSL features.
