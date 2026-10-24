#!/usr/bin/env bash
# Fetch the latest Universal Ubuntu Touch Builder develop branch and restart its desktop UI.
# Run from the logged-in graphical desktop session, not with sudo.
set -Eeuo pipefail

REPO_DIR="${UNIVERSAL_UBUNTU_TOUCH_BUILDER_DIR:-/home/ubuntu/Downloads/AndroidBuilder-master}"
BRANCH="${UNIVERSAL_UBUNTU_TOUCH_BUILDER_BRANCH:-develop}"
APP_SCRIPT="${UNIVERSAL_UBUNTU_TOUCH_BUILDER_APP:-run_desktop_ui.py}"
VENV_DIR="${UNIVERSAL_UBUNTU_TOUCH_BUILDER_VENV:-${REPO_DIR}/.venv}"
STATE_DIR="${XDG_STATE_HOME:-${HOME}/.local/state}/UniversalUbuntuTouchBuilder"
LOG_FILE="${STATE_DIR}/desktop-ui.log"
PID_FILE="${STATE_DIR}/desktop-ui.pid"

mkdir -p "$STATE_DIR"
log() { printf '[%s] %s\n' "$(date '+%F %T')" "$*"; }
fail() { log "ERROR: $*"; exit 1; }

[[ -d "$REPO_DIR/.git" ]] || fail "Not a Git repository: $REPO_DIR"
[[ -f "$REPO_DIR/$APP_SCRIPT" ]] || fail "UI entry point not found: $REPO_DIR/$APP_SCRIPT"
command -v git >/dev/null 2>&1 || fail "git is not installed"
cd "$REPO_DIR"

CURRENT_BRANCH="$(git branch --show-current)"
[[ "$CURRENT_BRANCH" == "$BRANCH" ]] ||
  fail "Current branch is '$CURRENT_BRANCH', expected '$BRANCH'. Switch to '$BRANCH' and retry."

if [[ -n "$(git status --porcelain)" ]]; then
  git status --short
  fail "Working tree has local changes/untracked files. Commit or stash them before updating. Nothing was pulled and the UI was not stopped."
fi

log "Fetching origin/$BRANCH..."
git fetch --prune origin "$BRANCH"
OLD_SHA="$(git rev-parse HEAD)"
REMOTE_SHA="$(git rev-parse "origin/$BRANCH")"

if [[ "$OLD_SHA" == "$REMOTE_SHA" ]]; then
  log "Already up to date ($OLD_SHA)."
else
  git merge-base --is-ancestor HEAD "origin/$BRANCH" ||
    fail "Local branch diverged from origin/$BRANCH. Refusing to overwrite local commits."
  git merge --ff-only "origin/$BRANCH"
  log "Updated to $(git rev-parse HEAD)"
fi

PYTHON="${VENV_DIR}/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3 || true)"
fi
[[ -n "$PYTHON" && -x "$PYTHON" ]] || fail "Python 3 not found. Install Python 3 or set UNIVERSAL_UBUNTU_TOUCH_BUILDER_VENV."

# Verify the updated entrypoint before stopping the managed UI.
"$PYTHON" -m py_compile "$REPO_DIR/$APP_SCRIPT" ||
  fail "Python syntax check failed. Existing UI was not stopped."

# Optional dependency update: set UNIVERSAL_UBUNTU_TOUCH_BUILDER_INSTALL_REQUIREMENTS=1.
if [[ "${UNIVERSAL_UBUNTU_TOUCH_BUILDER_INSTALL_REQUIREMENTS:-0}" == "1" ]]; then
  [[ -f "$REPO_DIR/requirements-ui.txt" ]] || fail "requirements-ui.txt not found"
  "$PYTHON" -m pip install -r "$REPO_DIR/requirements-ui.txt"
fi

# Stop only the process started and recorded by this script.
if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ "$OLD_PID" =~ ^[0-9]+$ ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    log "Stopping managed UI process $OLD_PID..."
    kill -TERM "$OLD_PID" 2>/dev/null || true
    for _ in {1..30}; do
      kill -0 "$OLD_PID" 2>/dev/null || break
      sleep 0.2
    done
    if kill -0 "$OLD_PID" 2>/dev/null; then
      log "UI process did not exit after SIGTERM; sending SIGKILL."
      kill -KILL "$OLD_PID" 2>/dev/null || true
    fi
  fi
  rm -f "$PID_FILE"
fi

log "Launching updated desktop UI..."
nohup "$PYTHON" "$REPO_DIR/$APP_SCRIPT" >>"$LOG_FILE" 2>&1 </dev/null &
NEW_PID=$!
printf '%s\n' "$NEW_PID" > "$PID_FILE"
sleep 2

if kill -0 "$NEW_PID" 2>/dev/null; then
  log "UI launched (PID $NEW_PID). Log: $LOG_FILE"
  log "View logs with: tail -f '$LOG_FILE'"
else
  rm -f "$PID_FILE"
  log "UI exited during startup. Recent log:"
  tail -n 80 "$LOG_FILE" || true
  exit 1
fi
