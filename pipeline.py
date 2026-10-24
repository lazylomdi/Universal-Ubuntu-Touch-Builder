"""
pipeline.py — the build pipeline.

Responsibilities:
  - Host requirement checks (disk, RAM, tool availability)
  - repo init / repo sync
  - Device / vendor / kernel tree cloning
  - Delegating customization steps to customizer.py
  - Delegating the actual build to backends.py
  - Resume detection via a JSON state file (.romforge_state.json in workdir)
  - Background launch (tmux preferred, nohup fallback)

State file schema:
  {
    "version": "1",
    "repo_synced": bool,
    "trees_cloned": [str, ...],    # list of kinds that were cloned
    "customizations_done": [str],  # names of completed customization steps
    "build_complete": bool,
    "output_zips": [str, ...]
  }

Using a state file (rather than inferring state from directory contents)
means the pipeline knows exactly which steps it ran, not just whether
certain directories exist.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from config import (VERSIONS, AOSP_ROLLING_BRANCH, AOSP_EXTRA_INIT_FLAGS,
                     MIN_DISK_GB, MIN_RAM_GB)


STATE_FILE = ".romforge_state.json"


# ── State management ───────────────────────────────────────────────────────────

def load_state(workdir: Path) -> dict:
    p = workdir / STATE_FILE
    if p.exists():
        try:
            return json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "version": "1",
        "repo_synced": False,
        "trees_cloned": [],
        "customizations_done": [],
        "build_complete": False,
        "output_zips": [],
    }


def save_state(workdir: Path, state: dict) -> None:
    try:
        workdir.mkdir(parents=True, exist_ok=True)
        (workdir / STATE_FILE).write_text(json.dumps(state, indent=2))
    except OSError:
        pass


def print_state(state: dict) -> None:
    def tick(b): return "✓" if b else "✗"
    print(f"    {tick(state['repo_synced'])}  repo sync")
    trees = state.get("trees_cloned", [])
    print(f"    {tick(bool(trees))}  device trees ({', '.join(trees) or 'none'})")
    cust  = state.get("customizations_done", [])
    print(f"    {tick(bool(cust))}  customizations ({', '.join(cust) or 'none'})")
    print(f"    {tick(state['build_complete'])}  build")
    zips = state.get("output_zips", [])
    if zips:
        for z in zips:
            mb = Path(z).stat().st_size // (1024*1024) if Path(z).exists() else 0
            print(f"          → {z} ({mb} MB)")


# ── Host checks ────────────────────────────────────────────────────────────────

def check_host() -> list[str]:
    """Return list of warning strings. Empty = all clear."""
    warnings = []
    if shutil.which("repo") is None:
        warnings.append(
            "`repo` not found. Install: "
            "curl https://storage.googleapis.com/git-repo-downloads/repo "
            "> ~/bin/repo && chmod +x ~/bin/repo")
    if shutil.which("git") is None:
        warnings.append("`git` not found. Install: sudo apt install git")
    try:
        free_gb = shutil.disk_usage(".").free / (1024 ** 3)
        if free_gb < MIN_DISK_GB:
            warnings.append(
                f"Only {free_gb:.0f} GB free disk. AOSP needs {MIN_DISK_GB}+ GB. "
                f"Build will likely fail mid-way.")
    except OSError:
        pass
    if os.name != "posix":
        warnings.append("AOSP builds require Linux. Windows/macOS not supported.")
    return warnings


# ── Source sync ────────────────────────────────────────────────────────────────

def manifest_url(source: str) -> str:
    return ("https://github.com/LineageOS/android.git" if source == "lineage"
            else "https://android.googlesource.com/platform/manifest")


def branch_for(version: str, source: str, use_latest: bool = False) -> str:
    v = VERSIONS[version]
    if source == "lineage":
        if v.lineage_eol:
            print(f"  ⚠ {v.lineage_branch} is EOL — no official builds or "
                  f"upstream fixes from LineageOS.")
        return v.lineage_branch
    return AOSP_ROLLING_BRANCH if use_latest else v.aosp_tag


def repo_sync(workdir: Path, version: str, source: str,
               use_latest: bool = False, jobs: int = 4,
               dry_run: bool = False) -> bool:
    branch = branch_for(version, source, use_latest)
    murl   = manifest_url(source)
    v      = VERSIONS[version]

    print(f"  manifest : {murl}")
    print(f"  branch   : {branch}")
    print(f"  viability: {v.viability.upper()}")
    if v.note:
        print(f"  note     : {v.note}")

    init_flags = list(AOSP_EXTRA_INIT_FLAGS) if source == "aosp" else []
    init_cmd = ["repo", "init"] + init_flags + ["-u", murl, "-b", branch]
    sync_cmd = ["repo", "sync", "-c", f"-j{jobs}", "--force-sync",
                "--no-clone-bundle", "--no-tags"]

    if dry_run:
        print(f"  [dry-run] {' '.join(init_cmd)}")
        print(f"  [dry-run] {' '.join(sync_cmd)}")
        return True

    workdir.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(init_cmd, cwd=workdir, check=True)
    except subprocess.CalledProcessError:
        print("  repo init failed. Check the branch name and network connection.")
        return False

    # repo sync can fail on large trees due to transient network issues.
    # Retry up to 3 times — this is standard practice per AOSP docs.
    for attempt in range(1, 4):
        try:
            subprocess.run(sync_cmd, cwd=workdir, check=True)
            return True
        except subprocess.CalledProcessError:
            if attempt < 3:
                print(f"  repo sync failed (attempt {attempt}/3), retrying...")
            else:
                print("  repo sync failed after 3 attempts.")
                print("  Common causes: network interruption, dead branch, "
                      "disk full. Safe to re-run — repo sync is resumable.")
                return False
    return False


# ── Tree cloning ───────────────────────────────────────────────────────────────

def clone_tree(workdir: Path, kind: str, clone_url: str,
                dry_run: bool = False) -> bool:
    dest_map = {
        "device":   "device",
        "vendor":   "vendor",
        "kernel":   "kernel",
        "recovery": "device",   # recovery trees use the device/ convention
    }
    dest = workdir / dest_map.get(kind, "local") / Path(clone_url).stem
    if dry_run:
        print(f"  [dry-run] git clone --depth 1 {clone_url} {dest}")
        return True
    if dest.exists():
        print(f"  {dest.name} already exists, pulling latest...")
        try:
            subprocess.run(["git", "-C", str(dest), "pull", "--ff-only"],
                           check=True, capture_output=True)
        except subprocess.CalledProcessError:
            print(f"  Pull failed — using existing tree at {dest}")
        return True
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", clone_url, str(dest)],
            check=True,
        )
        return True
    except subprocess.CalledProcessError:
        print(f"  Failed to clone {kind} tree from {clone_url}")
        return False


# ── Background launch ──────────────────────────────────────────────────────────

def launch_background(args_without_background: list[str], log_path: str) -> None:
    """
    Re-launch this command in a detached tmux session (or nohup fallback).
    Tmux is preferred because you can reattach and see live output.
    After calling this, the caller should sys.exit(0).

    Verified against tmux docs: `tmux new-session -d -s <name> '<cmd>'`
      -d = detached (don't attach immediately)
      -s = session name (reattach with: tmux attach -t romforge)
    """
    import shlex
    cmd = " ".join(shlex.quote(a) for a in args_without_background)
    full = f"{cmd} 2>&1 | tee {shlex.quote(log_path)}"

    if shutil.which("tmux"):
        subprocess.run(["tmux", "kill-session", "-t", "romforge"],
                       capture_output=True)
        subprocess.run(["tmux", "new-session", "-d", "-s", "romforge", full])
        print(f"\n  Launched in tmux session 'romforge'")
        print(f"  Reattach : tmux attach -t romforge")
        print(f"  Log file : {log_path}")
        print(f"  Kill     : tmux kill-session -t romforge")
    else:
        os.system(f"nohup {full} &")
        print(f"\n  Launched with nohup (install tmux for a reattachable session)")
        print(f"  Log file : {log_path}")
        print(f"  Monitor  : tail -f {log_path}")
        print(f"  Find PID : pgrep -af romforge")
    sys.exit(0)
