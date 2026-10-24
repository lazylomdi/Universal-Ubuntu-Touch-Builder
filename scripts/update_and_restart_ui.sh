#!/usr/bin/env bash
# Fetch latest AndroidBuilder changes and restart the PySide6 desktop UI.
# Run from the logged-in graphical desktop session, not with sudo.
set -Eeuo pipefail

REPO_DIR="${ANDROIDBUILDER_DIR:-/mnt/AndroidBuilder-ui}"
BRANCH="${ANDROIDBUILDER_BRANCH:-feature/desktop-ui}"
APP_SCRIPT="${ANDROIDBUILDER_APP:-run_desktop_ui.py}"
VENV_DIR="${ANDROIDBUILDER_VENV:-${REPO_DIR}/.venv}"
STATE_DIR="${XDG_STATE_HOME:-${HOME}/.local/state}/AndroidBuilder"
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
[[ -n "$CURRENT_BRANCH" ]] || fail "Detached HEAD detected. Switch to a branch before updating."
log "Current local branch: $CURRENT_BRANCH; update source: origin/$BRANCH"

if [[ -n "$(git status --porcelain)" ]]; then
  git status --short
  fail "Working tree has local changes/untracked files. Commit or stash them before updating."
fi

log "Fetching origin/$BRANCH..."
git fetch --prune origin "$BRANCH"
OLD_SHA="$(git rev-parse HEAD)"
REMOTE_SHA="$(git rev-parse "origin/$BRANCH")"

if [[ "$OLD_SHA" == "$REMOTE_SHA" ]]; then
  log "Already up to date ($OLD_SHA)."
else
  git merge-base --is-ancestor HEAD "origin/$BRANCH" ||
    fail "Local branch diverged from origin/$BRANCH. Refusing to overwrite history."
  git merge --ff-only "origin/$BRANCH"
  log "Updated to $(git rev-parse HEAD)"
fi

PYTHON="${VENV_DIR}/bin/python"
[[ -x "$PYTHON" ]] || fail "Virtualenv Python not found: $PYTHON"

# Optional dependency update: set ANDROIDBUILDER_INSTALL_REQUIREMENTS=1 to enable.
if [[ "${ANDROIDBUILDER_INSTALL_REQUIREMENTS:-0}" == "1" ]]; then
  [[ -f "$REPO_DIR/requirements-ui.txt" ]] || fail "requirements-ui.txt not found"
  "$PYTHON" -m pip install -r "$REPO_DIR/requirements-ui.txt"
fi

# Stop only the instance previously launched by this script.
if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ "$OLD_PID" =~ ^[0-9]+$ ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    log "Stopping UI process $OLD_PID..."
    kill -TERM "$OLD_PID" 2>/dev/null || true
    for _ in {1..30}; do
      kill -0 "$OLD_PID" 2>/dev/null || break
      sleep 0.2
    done
  fi
  rm -f "$PID_FILE"
fi

log "Launching UI..."
nohup "$PYTHON" "$REPO_DIR/$APP_SCRIPT" >>"$LOG_FILE" 2>&1 &
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
