#!/usr/bin/env bash
# AndroidBuilder Ubuntu host setup. Defaults to checks only; installs require explicit flags.
set -u

INSTALL_TOOLS=0
INSTALL_BUILD_DEPS=0
INSTALL_PYTHON_DEPS=0
SKIP_TESTS=0

usage() {
  cat <<'EOF'
Usage: ./setup_ubuntu.sh [options]

Default behavior only checks prerequisites and runs lightweight project checks.
Options:
  --install-tools        Install Git, Python, ADB, D-Bus and Qt/X11 runtime libraries via apt
  --install-build-deps   Also install common Android 13/14-era build packages via apt
  --install-python-deps  Create .venv and install requirements.txt
  --skip-tests           Skip unit tests
  -h, --help             Show this help

Run with sudo only if you understand the apt packages being installed.
The script never changes or flashes a connected phone.
EOF
}

while (($#)); do
  case "$1" in
    --install-tools) INSTALL_TOOLS=1 ;;
    --install-build-deps) INSTALL_BUILD_DEPS=1; INSTALL_TOOLS=1 ;;
    --install-python-deps) INSTALL_PYTHON_DEPS=1 ;;
    --skip-tests) SKIP_TESTS=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

section() { printf '\n== %s ==\n' "$1"; }
has() { command -v "$1" >/dev/null 2>&1; }

if [[ -r /etc/os-release ]]; then
  . /etc/os-release
  section "Ubuntu host"
  echo "Detected: ${PRETTY_NAME:-Linux}"
  if [[ "${ID:-}" != ubuntu ]]; then
    echo "Warning: this setup helper is intended for Ubuntu; package names may differ."
  fi
else
  echo "Warning: /etc/os-release is unavailable; cannot identify the Linux distribution."
fi

if (( INSTALL_TOOLS )); then
  section "Installing common tools"
  if ! has apt-get; then
    echo "apt-get not found; install these packages using your distribution's package manager." >&2
    exit 1
  fi
  sudo apt-get update
  sudo apt-get install -y git python3 python3-pip python3-venv adb curl rsync tmux ca-certificates \\
    dbus dbus-x11 libdbus-1-3 libxcb-cursor0 libxcb-icccm4 libxcb-image0 \\
    libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-xinerama0 \\
    libxcb-xkb1 libxkbcommon-x11-0 libegl1 libgl1
fi

if (( INSTALL_BUILD_DEPS )); then
  section "Installing common Android build dependencies"
  echo "Package availability varies by Ubuntu release and Android branch."
  sudo apt-get install -y \
    git-core gnupg flex bison build-essential zip curl \
    zlib1g-dev libc6-dev-i386 lib32ncurses-dev lib32z1-dev \
    libx11-dev libgl1-mesa-dev libxml2-utils xsltproc unzip fontconfig \
    openjdk-17-jdk-headless rsync bc python3
fi

section "Prerequisite check"
for cmd in git python3 adb curl; do
  if has "$cmd"; then
    printf '[OK]   %s: ' "$cmd"
    case "$cmd" in
      git) git --version ;;
      python3) python3 --version ;;
      adb) adb version | head -n 1 ;;
      curl) curl --version | head -n 1 ;;
    esac
  else
    echo "[MISS] $cmd (install with apt or rerun using --install-tools)"
  fi
done

if has adb; then
  section "Connected Android devices (read-only listing)"
  adb devices -l || echo "Warning: adb could not list devices."
  echo "If a device is unauthorized, unlock it and accept the USB debugging prompt."
fi

if (( INSTALL_PYTHON_DEPS )); then
  section "Installing Python requirements in a virtual environment"
  if ! has python3; then
    echo "python3 is required; install it first." >&2
    exit 1
  fi
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  if [[ -f requirements.txt ]]; then
    .venv/bin/python -m pip install -r requirements.txt
  else
    echo "requirements.txt not found in the current directory." >&2
    exit 1
  fi
fi

if [[ -f romforge.py ]]; then
  section "Project CLI check"
  if has python3; then
    PYTHON=python3
    [[ -x .venv/bin/python ]] && PYTHON=.venv/bin/python
    "$PYTHON" romforge.py ut-check --help
    if (( ! SKIP_TESTS )) && [[ -d tests ]]; then
      section "Unit tests"
      "$PYTHON" -m unittest discover -s tests -v
    fi
  else
    echo "python3 unavailable; skipping CLI and test checks."
  fi
else
  echo "romforge.py not found in current directory; run this script from the repository root."
fi

section "Finished"
echo "This script does not sync ROM sources, install every target-specific dependency, or modify a phone."
