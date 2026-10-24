"""Artifact inventory and provenance helpers for ROM build outputs."""
from __future__ import annotations

import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    """Return a streaming SHA-256 digest without loading the whole artifact."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def describe_artifact(path: str | Path, *, codename: str | None = None,
                      android_version: str | None = None,
                      backend: str | None = None,
                      configuration: dict[str, Any] | None = None,
                      build_succeeded: bool | None = None) -> dict[str, Any]:
    """Create a provenance record for an existing artifact.

    The record explicitly does not claim the image boots or has been hardware
    tested. Hashing is performed only when the file is a regular file.
    """
    artifact = Path(path).expanduser().resolve()
    if not artifact.exists() or not artifact.is_file():
        raise FileNotFoundError(f"Artifact is not an existing file: {artifact}")
    stat = artifact.stat()
    return {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "artifact": {
            "path": str(artifact),
            "filename": artifact.name,
            "size_bytes": stat.st_size,
            "sha256": sha256_file(artifact),
        },
        "build": {
            "device_codename": codename,
            "android_version": android_version,
            "backend": backend,
            "configuration": configuration or {},
            "reported_success": build_succeeded,
        },
        "validation": {
            "boot_tested": False,
            "hardware_tested": False,
            "signature_verified": False,
            "notes": [
                "A SHA-256 digest detects changes relative to a trusted copy; it does not prove publisher authenticity.",
                "Build success does not prove the image boots or that device hardware works.",
                "Signature verification is not claimed unless a separate verification step is performed."
            ]
        },
        "environment": {"platform": platform.platform(), "python": platform.python_version()},
    }


def write_artifact_manifest(path: str | Path, output: str | Path | None = None,
                            **metadata: Any) -> Path:
    """Write a JSON manifest beside the artifact by default."""
    record = describe_artifact(path, **metadata)
    artifact = Path(path).expanduser().resolve()
    manifest = Path(output).expanduser().resolve() if output else artifact.with_name(artifact.name + ".manifest.json")
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest
