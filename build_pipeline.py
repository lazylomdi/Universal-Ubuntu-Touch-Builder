"""
build_pipeline.py — build backends (local, docker, github-actions) and
pipeline utilities (host checks, repo sync, tree cloning, background launch,
state management) merged into one file.
"""

import shutil
import subprocess
from pathlib import Path


# ── Dockerfile template for the docker backend ────────────────────────────────
DOCKERFILE = """\
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y \\
    git-core gnupg flex bison build-essential zip curl zlib1g-dev \\
    libc6-dev-i386 lib32ncurses5-dev x11proto-core-dev libx11-dev \\
    lib32z1-dev libgl1-mesa-dev libxml2-utils xsltproc unzip fontconfig \\
    python3 python-is-python3 openjdk-17-jdk-headless rsync bc \\
    && rm -rf /var/lib/apt/lists/*
RUN curl -s https://storage.googleapis.com/git-repo-downloads/repo \\
    > /usr/local/bin/repo && chmod +x /usr/local/bin/repo
WORKDIR /workspace
CMD ["bash"]
"""

# ── GitHub Actions workflow template ──────────────────────────────────────────
GH_ACTIONS_WORKFLOW = """\
name: romforge-build
on:
  workflow_dispatch:
jobs:
  build:
    runs-on: ubuntu-latest
    # NOTE: Free GitHub-hosted runners have ~14GB disk and a 6hr job limit.
    # This is only realistic for small device trees or partial builds.
    # Use a self-hosted runner with 150GB+ disk for a full AOSP build.
    steps:
      - name: Free up disk space
        run: |
          sudo rm -rf /usr/share/dotnet /usr/local/lib/android /opt/ghc
          df -h

      - name: Install build dependencies
        run: |
          sudo apt-get update
          sudo apt-get install -y git-core gnupg flex bison build-essential \\
            zip curl zlib1g-dev libc6-dev-i386 lib32ncurses5-dev \\
            x11proto-core-dev libx11-dev lib32z1-dev libgl1-mesa-dev \\
            libxml2-utils xsltproc unzip fontconfig openjdk-17-jdk-headless \\
            rsync bc

      - name: Install repo tool
        run: |
          curl -s https://storage.googleapis.com/git-repo-downloads/repo \\
            > /usr/local/bin/repo
          chmod +x /usr/local/bin/repo

      - name: repo init
        run: |
          repo init {init_flags} -u {manifest_url} -b {branch}

      - name: repo sync
        run: repo sync -c -j4 --force-sync

      - name: Build
        run: |
          source build/envsetup.sh
          lunch {lunch_target}
          mka bacon -j4

      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: rom-{codename}-{version}
          path: out/target/product/{codename}/*.zip
          if-no-files-found: warn
"""


class LocalBackend:
    name = "local"

    def run(self, workdir: Path, lunch_target: str, jobs: int,
            dry_run: bool = False) -> bool:
        # lunch and mka are shell functions defined by envsetup.sh, so the
        # entire sequence must run in a single bash -c call.
        script = (
            f"source build/envsetup.sh && "
            f"lunch {lunch_target} && "
            f"mka bacon -j{jobs}"
        )
        print(f"  lunch target : {lunch_target}")
        print(f"  parallel jobs: {jobs}")
        if dry_run:
            print(f"  [dry-run] bash -c \"{script}\"")
            return True
        try:
            result = subprocess.run(
                ["bash", "-c", script],
                cwd=workdir,
                check=True,
            )
            return result.returncode == 0
        except subprocess.CalledProcessError as e:
            print(
                f"\n  Build failed (exit {e.returncode}).\n"
                f"  Common causes:\n"
                f"    • Missing proprietary blobs — run extract-utils on a stock dump\n"
                f"    • Device tree incompatible with this branch — check tree README\n"
                f"    • SELinux policy errors — adb logcat | grep avc, then audit2allow\n"
                f"    • Missing dependency — check the first error in the log above\n"
                f"  This tool cannot auto-repair build failures."
            )
            return False

    def locate_output(self, workdir: Path, codename: str) -> list[Path]:
        """Find all output zips for this device, newest first."""
        product_dir = workdir / "out" / "target" / "product" / codename
        if not product_dir.exists():
            return []
        zips = sorted(product_dir.glob("*.zip"),
                      key=lambda p: p.stat().st_mtime, reverse=True)
        return zips


class DockerBackend:
    name = "docker"

    def run(self, workdir: Path, lunch_target: str, jobs: int,
            dry_run: bool = False) -> bool:
        dockerfile = workdir / "Dockerfile.romforge"
        image_tag  = "romforge-builder:latest"

        build_cmd = ["docker", "build", "-t", image_tag,
                     "-f", str(dockerfile), str(workdir)]
        run_cmd   = [
            "docker", "run", "--rm",
            "-v", f"{workdir}:/workspace",
            image_tag,
            "bash", "-c",
            f"source build/envsetup.sh && lunch {lunch_target} && mka bacon -j{jobs}",
        ]

        if dry_run:
            print(f"  [dry-run] would write {dockerfile}")
            print(f"  [dry-run] {' '.join(build_cmd)}")
            print(f"  [dry-run] {' '.join(run_cmd)}")
            return True

        dockerfile.write_text(DOCKERFILE)
        try:
            subprocess.run(build_cmd, check=True)
            subprocess.run(run_cmd, check=True)
            return True
        except subprocess.CalledProcessError as e:
            print(f"  Docker backend failed (exit {e.returncode}). "
                  f"Ensure Docker has 150GB+ disk and 16GB+ RAM allocated.")
            return False


class GithubActionsBackend:
    name = "github-actions"

    def run(self, workdir: Path, lunch_target: str, jobs: int,
            dry_run: bool = False,
            manifest_url: str = "",
            branch: str = "",
            codename: str = "",
            version: str = "",
            init_flags: str = "") -> bool:
        wf_dir  = workdir / ".github" / "workflows"
        wf_path = wf_dir / "romforge-build.yml"
        content = GH_ACTIONS_WORKFLOW.format(
            manifest_url=manifest_url,
            branch=branch,
            lunch_target=lunch_target,
            codename=codename,
            version=version,
            init_flags=init_flags,
        )
        if dry_run:
            print(f"  [dry-run] would write {wf_path}")
            print(f"  Workflow would use branch: {branch}, target: {lunch_target}")
            return True
        wf_dir.mkdir(parents=True, exist_ok=True)
        wf_path.write_text(content)
        print(f"  Wrote workflow: {wf_path}")
        print(f"  Commit and push this file, then trigger from the Actions tab")
        print(f"  or: gh workflow run romforge-build.yml")
        return True


def get_backend(name: str) -> LocalBackend | DockerBackend | GithubActionsBackend:
    return {"local": LocalBackend, "docker": DockerBackend,
            "github-actions": GithubActionsBackend}[name]()


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
        "gerrit_patches_applied": [],
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

def manifest_url(source: str, version: str | None = None) -> str:
    """
    Return the correct manifest URL. For source="lineage" this depends on
    the SPECIFIC version: Android 4-6 use CyanogenMod's manifest org,
    Android 7+ use LineageOS's. These are two different GitHub orgs with
    incompatible branch sets — pointing a cm-* branch at LineageOS/android
    (or vice versa) causes widespread "cannot initialize work tree" sync
    errors because the branch doesn't exist there.

    Verified: github.com/CyanogenMod/android (cm-11.0 through cm-14.1),
              github.com/LineageOS/android (lineage-14.1 onward, current).
    """
    if source != "lineage":
        return "https://android.googlesource.com/platform/manifest"
    if version is not None and version in VERSIONS:
        org = VERSIONS[version].manifest_org
        return f"https://github.com/{org}/android.git"
    return "https://github.com/LineageOS/android.git"  # fallback


def branch_for(version: str, source: str, use_latest: bool = False) -> str:
    v = VERSIONS[version]
    if source == "lineage":
        if v.lineage_eol:
            project = "CyanogenMod" if v.manifest_org == "CyanogenMod" else "LineageOS"
            print(f"  ⚠ {v.lineage_branch} is EOL — no official builds or "
                  f"upstream fixes from {project}.")
        return v.lineage_branch
    return AOSP_ROLLING_BRANCH if use_latest else v.aosp_tag


def repo_sync(workdir: Path, version: str, source: str,
               use_latest: bool = False, jobs: int = 4,
               dry_run: bool = False) -> bool:
    branch = branch_for(version, source, use_latest)
    murl   = manifest_url(source, version)
    v      = VERSIONS[version]

    if source == "aosp":
        print(f"  ⚠ Raw AOSP source selected. This only works cleanly for "
              f"devices with an OFFICIAL Google AOSP device tree (Pixel-line\n"
              f"    devices). Community device trees (from LineageOS, "
              f"TheMuppets, etc.) define '{v.product_prefix}_<codename>'\n"
              f"    products, NOT 'aosp_<codename>' — lunch will fail with "
              f"an unknown/invalid combo if you clone one into an AOSP tree.\n"
              f"    Use --source lineage unless you specifically have an "
              f"AOSP-native device tree.\n"
              f"    Want specific LineageOS features on top of pure AOSP? "
              f"There's no bulk 'apply all Lineage patches' operation —\n"
              f"    that's what the lineage manifest already is. But you can "
              f"cherry-pick INDIVIDUAL LineageOS Gerrit changes with:\n"
              f"      --gerrit-patch <change-number>   (repeatable)\n"
              f"    Find change numbers at review.lineageos.org. Patches "
              f"written against Lineage's own history may conflict when\n"
              f"    applied to vanilla AOSP — this is expected and the tool "
              f"will tell you exactly where if it happens.")

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

def _parse_tree_path(clone_url: str, kind: str) -> tuple[str, str] | None:
    """
    Parse a device/vendor/kernel repo URL into (vendor, codename) so we
    can place the clone at the correct AOSP convention path.

    Conventions seen in the wild:
      android_device_{vendor}_{codename}   (LineageOS, most orgs)
      device_{vendor}_{codename}           (AOKP, older trees)
      android_kernel_{vendor}_{codename}
      kernel_{vendor}_{soc}
      proprietary_vendor_{vendor}          (TheMuppets)
      proprietary_vendor_{vendor}_{codename}

    Returns (vendor, name) where name is the codename for device trees
    or the repo stem for everything else.
    Returns None if parsing fails.
    """
    import re
    name = Path(clone_url).stem  # strip .git and path
    # Device and recovery trees
    m = re.search(r'(?:android_)?device_([A-Za-z0-9]+)_(.+)$', name)
    if m and kind in ("device", "recovery"):
        return m.group(1), m.group(2)
    # Vendor blobs
    m = re.search(r'(?:android_|proprietary_)?vendor_([A-Za-z0-9]+)(?:_(.+))?$', name)
    if m and kind == "vendor":
        vendor = m.group(1)
        subdir = m.group(2) or ""
        return vendor, subdir
    # Kernel trees
    m = re.search(r'(?:android_)?kernel_([A-Za-z0-9]+)_(.+)$', name)
    if m and kind == "kernel":
        return m.group(1), m.group(2)
    return None


def build_lunch_target(rom_prefix: str, codename: str, variant: str,
                        version: str, source: str) -> str:
    """
    Build the correct lunch target string for any Android version.

    Product prefix depends on the ERA, not just source="lineage"/"aosp":
      Android 4-6  (CyanogenMod era) → cm_d2att-userdebug
      Android 7+   (LineageOS era)   → lineage_d2att-userdebug
      Raw AOSP                        → aosp_<codename>-... (only valid for
                                         devices with an official Google
                                         AOSP device tree — see repo_sync's
                                         warning for community trees)

    Format also depends on era:
      Old format (Android ≤13 / lineage-20 and below):
          lineage_d2att-userdebug
      New format (Android 14+ / lineage-21+):
          lineage_d2att-ap4a-userdebug
                            ^^^^ release code

    The release code is determined from config.LUNCH_RELEASE_CODES (for
    LineageOS) or config.AOSP_RELEASE_CODES (for raw AOSP builds) keyed
    by the branch/API level. Using the wrong format causes:
        "Invalid lunch combo: ... must be of the form <product>-<release>-<variant>"
    Using the wrong PREFIX (e.g. lineage_ for a CyanogenMod-era build)
    causes "Invalid lunch combo" too, since no such product is defined.

    Verified: github.com/itsfragilecode/android (lineage-21, ap2a example)
              groups.google.com/g/android-building/c/z7gYowDYQfk (Android 15)
              XDA CM guides confirming "lunch cm_<codename>-userdebug"
    """
    from config import (LUNCH_RELEASE_CODES, AOSP_RELEASE_CODES, VERSIONS)

    release_code: str | None = None
    vinfo = VERSIONS.get(version)

    if source == "lineage" and vinfo:
        # rom_prefix is derived here, not trusted from the caller — the
        # caller previously always passed "lineage" even for CM-era builds,
        # producing lineage_<codename> targets that don't exist pre-Android-7.
        rom_prefix = vinfo.product_prefix   # "cm" or "lineage"
        release_code = LUNCH_RELEASE_CODES.get(vinfo.lineage_branch)
    elif source == "aosp" and vinfo:
        rom_prefix = "aosp"
        release_code = AOSP_RELEASE_CODES.get(vinfo.api)

    product = f"{rom_prefix}_{codename}"
    if release_code:
        return f"{product}-{release_code}-{variant}"
    else:
        return f"{product}-{variant}"


def clone_tree(workdir: Path, kind: str, clone_url: str,
               dry_run: bool = False) -> bool:
    """
    Clone a device/vendor/kernel/recovery tree into the correct AOSP path.

    Path conventions (verified against LineageOS tree layout):
      device trees  → device/{vendor}/{codename}
      vendor blobs  → vendor/{vendor}/{codename or ''}
      kernel trees  → kernel/{vendor}/{codename}
      recovery      → device/{vendor}/{codename}  (same as device)

    Falls back to workdir/{kind}/{repo-stem} if the URL doesn't match any
    known naming convention.
    """
    parsed = _parse_tree_path(clone_url, kind)
    if parsed:
        vendor, subname = parsed
        base_map = {"device": "device", "vendor": "vendor",
                    "kernel": "kernel", "recovery": "device"}
        base = workdir / base_map.get(kind, kind) / vendor
        dest = base / subname if subname else base
    else:
        # Fallback: workdir/{kind}/{stem}
        stem = Path(clone_url).stem
        dest = workdir / kind / stem
        print(f"  ⚠ Could not parse vendor/codename from URL '{clone_url}'")
        print(f"    Cloning to fallback path: {dest}")
        print(f"    You may need to move it to device/{{vendor}}/{{codename}}/ manually.")

    if dry_run:
        print(f"  [dry-run] git clone --depth 1 {clone_url}")
        print(f"            → {dest}")
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
        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--depth", "1", clone_url, str(dest)],
            check=True,
        )
        print(f"  Cloned {kind} tree → {dest.relative_to(workdir)}")
        return True
    except subprocess.CalledProcessError:
        print(f"  Failed to clone {kind} tree from {clone_url}")
        return False


# ── Gerrit patch picking (AOSP + specific LineageOS patches) ───────────────────
#
# "Sync pure AOSP, then layer on LineageOS's patches" is not a bulk,
# automatable operation — LineageOS's manifest (github.com/LineageOS/android)
# already IS that result, built up repo-by-repo over years. There's no
# smaller "just the patches" artifact to apply in one shot.
#
# What IS real and scriptable: cherry-picking SPECIFIC, individually chosen
# LineageOS Gerrit changes onto whatever tree you have synced. This is
# exactly what LineageOS's own `repopick` tool does:
#   git fetch https://review.lineageos.org/<project> <ref>
#   git cherry-pick FETCH_HEAD
# Verified: wiki entry "How to use Gerrit" (LineageOS Wiki), which documents
# this exact fetch+cherry-pick pattern for applying a single change.
#
# Applying a Lineage-authored patch onto a VANILLA AOSP tree is a gamble —
# the patch was written against Lineage's own diverged history at some
# point in time, not against AOSP directly, so conflicts are common. This
# is much more likely to apply cleanly onto a tree already synced from
# LineageOS's own manifest. The tool says this plainly rather than
# pretending it's reliable either way.

GERRIT_URL = "https://review.lineageos.org"


def _gerrit_change_info(change_id: str) -> dict | None:
    """
    Query LineageOS's Gerrit REST API for a change's project and current
    patchset ref. Gerrit prefixes JSON responses with )]}' to prevent
    XSSI attacks — that prefix must be stripped before parsing.
    """
    import urllib.request, json
    url = f"{GERRIT_URL}/changes/{change_id}/detail?o=CURRENT_REVISION"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode()
        raw = raw.lstrip(")]}'\n")
        data = json.loads(raw)
        project = data["project"]
        current_rev = data["current_revision"]
        ref = data["revisions"][current_rev]["ref"]
        subject = data.get("subject", "")
        return {"project": project, "ref": ref, "subject": subject}
    except Exception as e:
        print(f"  Failed to look up Gerrit change {change_id}: {e}")
        return None


def _project_to_path(project: str) -> str:
    """
    Convert a LineageOS Gerrit project name to its path in the source tree.
      LineageOS/android_frameworks_base          → frameworks/base
      LineageOS/android_packages_apps_Settings   → packages/apps/Settings
    Best-effort convention match — a small number of repos have legitimate
    underscores inside a path segment and may need a manual override via
    --gerrit-patch-path.
    """
    name = project.split("/")[-1]
    if name.startswith("android_"):
        name = name[len("android_"):]
    return name.replace("_", "/")


def apply_gerrit_patches(workdir: Path, change_ids: list[str],
                          dry_run: bool = False) -> bool:
    """
    Cherry-pick specific LineageOS Gerrit changes (by change number, e.g.
    the "65062" in review.lineageos.org/c/.../+/65062) onto an already-
    synced tree. Returns True only if every requested change applied.
    """
    if not change_ids:
        return True
    all_ok = True
    for change_id in change_ids:
        print(f"  Looking up Gerrit change {change_id}...")
        info = _gerrit_change_info(change_id)
        if not info:
            all_ok = False
            continue

        path = _project_to_path(info["project"])
        dest = workdir / path
        fetch_url = f"{GERRIT_URL}/{info['project']}"
        print(f"  Change {change_id}: \"{info['subject']}\" → {path}")

        if dry_run:
            print(f"    [dry-run] git fetch {fetch_url} {info['ref']}")
            print(f"    [dry-run] git cherry-pick FETCH_HEAD")
            continue

        if not dest.exists():
            print(f"    ⚠ {dest} not found in synced tree — skipping.")
            print(f"      Project '{info['project']}' maps to path '{path}', "
                  f"but that directory isn't in this source tree (it may "
                  f"not be part of the manifest you synced, or the "
                  f"project-name→path convention didn't match here).")
            all_ok = False
            continue

        try:
            subprocess.run(["git", "fetch", fetch_url, info["ref"]],
                           cwd=dest, check=True)
            subprocess.run(["git", "cherry-pick", "FETCH_HEAD"],
                           cwd=dest, check=True)
            print(f"    ✓ Applied")
        except subprocess.CalledProcessError:
            print(f"    ✗ Cherry-pick failed — most likely a merge conflict.")
            print(f"      This patch was written against LineageOS's own "
                  f"history; applying it onto a differently-diverged tree "
                  f"(e.g. vanilla AOSP) commonly conflicts.")
            print(f"      Resolve manually: cd {dest} && fix conflicts && "
                  f"git cherry-pick --continue")
            print(f"      Or abandon it: cd {dest} && git cherry-pick --abort")
            all_ok = False
    return all_ok


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

