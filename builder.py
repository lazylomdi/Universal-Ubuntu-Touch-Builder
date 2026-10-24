"""
romforge.builder
==================
Build backend abstraction + the "local" backend (run repo/lunch/mka
directly on this machine). Docker and GitHub Actions backends live in
backends_remote.py and implement the same BuildBackend interface.

The actual build commands (`source build/envsetup.sh && lunch ... && mka
bacon`) are identical in spirit across Android versions, but the lunch
target naming and final artifact name vary by era -- handled via
config.ANDROID_VERSIONS metadata where possible, otherwise the user passes
an explicit lunch target.
"""

import subprocess
from abc import ABC, abstractmethod
from pathlib import Path


class BuildBackend(ABC):
    name: str

    @abstractmethod
    def run_build(self, workdir: Path, lunch_target: str, jobs: int,
                   dry_run: bool = False) -> bool:
        ...


class LocalBuildBackend(BuildBackend):
    name = "local"

    def run_build(self, workdir: Path, lunch_target: str, jobs: int,
                   dry_run: bool = False) -> bool:
        # envsetup.sh defines shell functions (lunch, mka) that don't exist
        # as standalone binaries, so this must run through bash -c as one
        # sourced session rather than as separate subprocess calls.
        script = (
            f"source build/envsetup.sh && "
            f"lunch {lunch_target} && "
            f"mka bacon -j{jobs}"
        )
        print(f"  [local backend] lunch target: {lunch_target}, jobs: {jobs}")
        if dry_run:
            print(f"  [dry-run] would run in {workdir}:\n    bash -c \"{script}\"")
            return True
        try:
            subprocess.run(["bash", "-c", script], cwd=workdir, check=True)
        except subprocess.CalledProcessError as e:
            print(f"  Build failed (exit {e.returncode}). Check the build "
                  f"log above for the failing module -- this is almost "
                  f"always a missing dependency, a proprietary blob "
                  f"mismatch, or an incompatible device tree for this "
                  f"branch, not something this tool can auto-repair.")
            return False
        return True

    def locate_output(self, workdir: Path, codename: str) -> Path | None:
        out_dir = workdir / "out" / "target" / "product" / codename
        if not out_dir.exists():
            return None
        for pattern in ("*.zip",):
            matches = sorted(out_dir.glob(pattern), key=lambda p: p.stat().st_mtime,
                              reverse=True)
            if matches:
                return matches[0]
        return None


def get_backend(name: str) -> BuildBackend:
    if name == "local":
        return LocalBuildBackend()
    from backends_remote import DockerBuildBackend, GithubActionsBuildBackend
    if name == "docker":
        return DockerBuildBackend()
    if name == "github-actions":
        return GithubActionsBuildBackend()
    raise ValueError(
        f"Unknown backend '{name}'. Choices: local, docker, github-actions. "
        f"(A cloud VM/QEMU box is just 'local', run over SSH on that box --"
        f" there's no separate backend for it; point this tool at the VM.)")
