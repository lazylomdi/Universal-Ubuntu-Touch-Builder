#!/usr/bin/env bash
# Universal Ubuntu Touch Builder - repair/setup/launch helper
# Run from any directory. Uses the location of this script/repository.
set -Eeuo pipefail

APP_NAME="Universal Ubuntu Touch Builder"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
LOG_DIR="${XDG_STATE_HOME:-${HOME}/.local/state}/universal-ubuntu-touch-builder"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/setup-$(date +%Y%m%d-%H%M%S).log"

# Log all output while keeping it visible in the terminal.
exec > >(tee -a "$LOG_FILE") 2>&1

trap 'rc=$?; echo; echo "ERROR: Setup stopped at line ${LINENO} (exit ${rc})."; echo "Log saved to: ${LOG_FILE}"; echo "The terminal should remain open if you ran this from an existing terminal."; exit "$rc"' ERR

echo "============================================================"
echo "$APP_NAME - setup and launcher"
echo "Repository: $SCRIPT_DIR"
echo "User: $(id -un) (uid $(id -u))"
echo "Log: $LOG_FILE"
echo "============================================================"

if [[ ! -f "$SCRIPT_DIR/run_desktop_ui.py" ]]; then
  echo "ERROR: Cannot find run_desktop_ui.py beside this script."
  echo "Put this script in the repository root and run it again."
  exit 2
fi

cd "$SCRIPT_DIR"

# Identify apt and sudo, only installing system packages if needed.
APT=""
if command -v apt-get >/dev/null 2>&1; then APT="apt-get"; fi
SUDO=""
if [[ "$(id -u)" -ne 0 ]] && command -v sudo >/dev/null 2>&1; then SUDO="sudo"; fi

ensure_apt_package() {
  local pkg="$1"
  if dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "install ok installed"; then
    echo "System package already installed: $pkg"
  else
    if [[ -z "$APT" ]]; then
      echo "WARNING: apt-get not available; cannot automatically install system package: $pkg"
      return 1
    fi
    echo "Installing system package: $pkg"
    if [[ "$(id -u)" -eq 0 ]]; then
      apt-get update
      DEBIAN_FRONTEND=noninteractive apt-get install -y "$pkg"
    elif [[ -n "$SUDO" ]]; then
      sudo apt-get update
      sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "$pkg"
    else
      echo "ERROR: Installing $pkg requires root or sudo."
      return 1
    fi
  fi
}

# Ensure Python is available. Don't attempt to replace the system Python.
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is missing."
  ensure_apt_package python3
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERROR: python3 still unavailable after package installation."
  exit 3
fi

# Check and repair venv/pip support.
if ! python3 -m venv --help >/dev/null 2>&1; then
  echo "Python venv support is missing; installing it."
  py_minor="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
  if ! ensure_apt_package "python${py_minor}-venv"; then
    ensure_apt_package python3-venv
  fi
fi

if ! python3 -m venv --help >/dev/null 2>&1; then
  echo "ERROR: Python venv support is still unavailable."
  echo "Install python3-venv for your distribution, then rerun this script."
  exit 4
fi

# Find requirements files without assuming a single filename.
REQ_FILE=""
for candidate in requirements-ui.txt requirements.txt; do
  if [[ -f "$SCRIPT_DIR/$candidate" ]]; then
    REQ_FILE="$SCRIPT_DIR/$candidate"
    break
  fi
done

if [[ -z "$REQ_FILE" ]]; then
  echo "ERROR: No requirements-ui.txt or requirements.txt exists in the repository root."
  echo "I will not guess dependency names. Please add a requirements file or inspect the log."
  exit 5
fi
echo "Using dependency file: $(basename "$REQ_FILE")"

# Recreate only a broken/missing project venv. Never delete user files or system Python.
VENV="$SCRIPT_DIR/.venv"
if [[ -e "$VENV" && ! -x "$VENV/bin/python" ]]; then
  echo "Existing .venv is incomplete. Moving it aside rather than deleting it."
  mv -- "$VENV" "$VENV.broken-$(date +%Y%m%d-%H%M%S)"
fi

if [[ ! -x "$VENV/bin/python" ]]; then
  echo "Creating project virtual environment at $VENV"
  python3 -m venv "$VENV"
fi

VPY="$VENV/bin/python"
if [[ ! -x "$VPY" ]]; then
  echo "ERROR: Could not create $VENV/bin/python"
  exit 6
fi

# Handle common root -> regular-user permission mismatch for the venv only.
if [[ "$(id -u)" -ne 0 && ! -w "$VENV" ]]; then
  echo "ERROR: $VENV is not writable by $(id -un)."
  echo "It may have been created by root. Run this once:"
  echo "  sudo chown -R \"$(id -un):$(id -gn)\" \"$VENV\""
  exit 7
fi

echo "Upgrading pip in the project environment..."
"$VPY" -m ensurepip --upgrade || true
"$VPY" -m pip install --upgrade pip setuptools wheel

echo "Installing project dependencies..."
"$VPY" -m pip install -r "$REQ_FILE"

echo "Checking for unresolved Git merge markers in Python files..."
if grep -nE '^(<<<<<<< |=======|>>>>>>> )' "$SCRIPT_DIR/main.py" 2>/dev/null; then
  echo "WARNING: main.py contains Git conflict markers."
  echo "This script will not edit main.py automatically because choosing a side could destroy code."
fi

echo "Checking Python syntax for GUI entry points..."
"$VPY" -m py_compile "$SCRIPT_DIR/run_desktop_ui.py" "$SCRIPT_DIR/desktop_ui/app.py"

echo
echo "Setup complete."
echo "Environment: $VPY"
echo "Log: $LOG_FILE"
echo

if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
  echo "WARNING: No graphical display variables detected."
  echo "Dependencies are installed, but a desktop GUI may not open from this session."
  echo "Log file: $LOG_FILE"
  exit 0
fi

echo "Launching GUI in the foreground (Ctrl+C to stop)."
echo "If it exits, the error will be recorded in the log."
"$VPY" "$SCRIPT_DIR/run_desktop_ui.py"
rc=$?
echo "GUI exited with status $rc."
echo "Log: $LOG_FILE"
exit "$rc"
