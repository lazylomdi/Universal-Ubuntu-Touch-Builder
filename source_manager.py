"""
romforge.source_manager
=========================
Wraps Google's `repo` tool to fetch AOSP/LineageOS source for a chosen
Android version, and clones resolved device/vendor/kernel trees into the
right place in the source tree.

This module does NOT try to patch every possible toolchain/dependency
issue for old branches -- that's an open-ended, device-specific problem.
It surfaces the version's viability rating up front (see config.py) so
the user knows what they're getting into, and fails loudly rather than
silently when a step errors.
"""

import os
import shutil
import subprocess
from pathlib import Path

from config import ANDROID_VERSIONS, MIN_FREE_DISK_GB, AOSP_LATEST_BRANCH, AOSP_REPO_INIT_EXTRA_FLAGS


class SourceManager:
    def __init__(self, workdir: Path, source: str = "lineage", use_latest_aosp: bool = False):
        """
        source: "aosp" or "lineage" -- which manifest/branch family to use.
        LineageOS is offered alongside raw AOSP because most public device
        trees target Lineage branches, not bare AOSP.

        use_latest_aosp: when source="aosp", use Google's current
        documented rolling branch (android-latest-release) instead of the
        historical per-version numbered tag. This matches AOSP's 2026
        twice-a-year trunk-stable release model -- see config.py header
        for sourcing. Numbered tags still exist in git history and remain
        selectable (use_latest_aosp=False) for reproducing an exact old
        release, but they are not what Google's docs currently point to
        for a fresh build.
        """
        self.workdir = workdir
        self.source = source
        self.use_latest_aosp = use_latest_aosp

    def check_host_requirements(self) -> list[str]:
        """Returns a list of human-readable warnings; empty list = all clear."""
        warnings = []
        if shutil.which("repo") is None:
            warnings.append(
                "`repo` tool not found on PATH. Install it: "
                "https://source.android.com/setup/develop#installing-repo")
        free_gb = shutil.disk_usage(self.workdir.parent if self.workdir.exists()
                                     else Path.cwd()).free / (1024 ** 3)
        if free_gb < MIN_FREE_DISK_GB:
            warnings.append(
                f"Only {free_gb:.0f}GB free disk detected; AOSP builds "
                f"typically need {MIN_FREE_DISK_GB}GB+. Build will likely "
                f"fail partway through, often after hours of work.")
        if os.name != "posix":
            warnings.append(
                "AOSP/LineageOS builds require Linux (or WSL2). Native "
                "Windows/macOS are not supported by the upstream build system.")
        return warnings

    def branch_for(self, version: str) -> str:
        info = ANDROID_VERSIONS[version]
        if self.source == "lineage":
            if info.lineage_eol:
                print(f"  Note: {info.lineage_branch} is no longer "
                      f"officially built by LineageOS (2-version support "
                      f"policy). The branch ref may still exist but expect "
                      f"no upstream fixes.")
            return info.lineage_branch
        if self.use_latest_aosp:
            return AOSP_LATEST_BRANCH
        return info.aosp_tag_or_branch

    def manifest_url(self) -> str:
        return ("https://github.com/LineageOS/android.git" if self.source == "lineage"
                else "https://android.googlesource.com/platform/manifest")

    def init_and_sync(self, version: str, jobs: int = 4, dry_run: bool = False) -> bool:
        info = ANDROID_VERSIONS[version]
        branch = self.branch_for(version)
        if branch is None:
            print(f"  No {self.source} branch mapping for Android {version}. "
                  f"Falling back to AOSP tag {info.aosp_tag_or_branch}.")
            branch = info.aosp_tag_or_branch

        print(f"  Android {version} viability: {info.viability.upper()}")
        if info.notes:
            print(f"  Note: {info.notes}")

        init_cmd = ["repo", "init", "-u", self.manifest_url(), "-b", branch]
        self.workdir.mkdir(parents=True, exist_ok=True)
        init_cmd = ["repo", "init", "-u", self.manifest_url(), "-b", branch]
        # The --partial-clone/--no-use-superproject flags are part of
        # Google's currently documented AOSP init command (see config.py
        # header). They're harmless on LineageOS manifests too, but we only
        # apply them for source="aosp" to stay close to each project's own
        # documented instructions rather than mixing conventions.
        if self.source == "aosp":
            init_cmd[2:2] = AOSP_REPO_INIT_EXTRA_FLAGS
        sync_cmd = ["repo", "sync", "-c", "-j", str(jobs), "--force-sync"]

        if dry_run:
            print(f"  [dry-run] would run in {self.workdir}: {' '.join(init_cmd)}")
            print(f"  [dry-run] would run in {self.workdir}: {' '.join(sync_cmd)}")
            return True

        self.workdir.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(init_cmd, cwd=self.workdir, check=True)
            subprocess.run(sync_cmd, cwd=self.workdir, check=True)
        except subprocess.CalledProcessError as e:
            print(f"  repo command failed (exit {e.returncode}). This is "
                  f"commonly a dead branch/manifest for older versions, or "
                  f"a network interruption mid-sync (safe to re-run repo sync).")
            return False
        return True

    def detect_state(self) -> dict:
        """
        Non-destructively scan the workdir to determine what has already
        been completed. Returns a dict with boolean keys so cmd_build can
        skip steps that are already done rather than re-running them from
        scratch -- this is the "resume from existing synced files" path.

        Keys:
          repo_initialized : .repo/manifest.xml exists (repo init ran)
          source_synced    : .repo/ exists + build/envsetup.sh exists
                             (repo sync completed enough to build)
          device_tree      : device/ directory has at least one subdir
          vendor_tree      : vendor/ directory has at least one subdir
          kernel_tree      : kernel/ directory has at least one subdir
          build_complete   : out/target/product/ has at least one .zip
        """
        wd = self.workdir
        repo_dir = wd / ".repo"
        return {
            "repo_initialized": (repo_dir / "manifest.xml").exists(),
            "source_synced": (repo_dir.exists() and (wd / "build" / "envsetup.sh").exists()),
            "device_tree": any((wd / "device").iterdir()) if (wd / "device").exists() else False,
            "vendor_tree": any((wd / "vendor").iterdir()) if (wd / "vendor").exists() else False,
            "kernel_tree": any((wd / "kernel").iterdir()) if (wd / "kernel").exists() else False,
            "build_complete": any((wd / "out" / "target" / "product").rglob("*.zip"))
                              if (wd / "out" / "target" / "product").exists() else False,
        }

    def print_state(self, state: dict) -> None:
        labels = {
            "repo_initialized": "repo init",
            "source_synced": "repo sync (source tree)",
            "device_tree": "device tree",
            "vendor_tree": "vendor tree",
            "kernel_tree": "kernel tree",
            "build_complete": "build artifact (.zip)",
        }
        print("  Current workdir state:")
        for key, label in labels.items():
            mark = "✓" if state[key] else "✗"
            print(f"    {mark}  {label}")

    def clone_device_trees(self, clone_urls: dict[str, str], dry_run: bool = False) -> bool:
        """
        clone_urls: {"device": url, "vendor": url, "kernel": url} (any subset)
        Clones into the conventional AOSP locations under device/<vendor>/<codename>
        etc. Caller is responsible for resolving the right destination path
        per repo since that varies by manifest layout.
        """
        ok = True
        for kind, url in clone_urls.items():
            dest_root = self.workdir / {
                "device": "device", "vendor": "vendor", "kernel": "kernel"
            }.get(kind, "local_manifests")
            dest = dest_root / Path(url).stem
            if dry_run:
                print(f"  [dry-run] would clone {kind} tree {url} -> {dest}")
                continue
            dest_root.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                print(f"  {dest} already exists, skipping clone.")
                continue
            try:
                subprocess.run(["git", "clone", "--depth", "1", url, str(dest)], check=True)
            except subprocess.CalledProcessError:
                print(f"  Failed to clone {kind} tree from {url}")
                ok = False
        return ok
