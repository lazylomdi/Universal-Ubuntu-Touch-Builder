"""
backends.py — build backends: local, docker, github-actions.

Each backend implements run(config, dry_run) → bool.
The local backend also implements locate_output(workdir, codename) → Path | None.

A cloud VM / QEMU box is not a separate backend: SSH into it and use
the local backend there.
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
