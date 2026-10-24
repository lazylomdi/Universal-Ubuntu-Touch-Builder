import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from artifact_manifest import describe_artifact, write_artifact_manifest


class ArtifactManifestTests(unittest.TestCase):
    def test_manifest_records_hash_metadata_and_no_boot_claim(self):
        with tempfile.TemporaryDirectory() as temp:
            artifact = Path(temp) / "rom.zip"
            artifact.write_bytes(b"sample-rom-artifact")
            record = describe_artifact(
                artifact, codename="demo", android_version="14",
                backend="local", configuration={"jobs": 4}, build_succeeded=True,
            )
            self.assertEqual(record["artifact"]["sha256"], hashlib.sha256(b"sample-rom-artifact").hexdigest())
            self.assertEqual(record["build"]["device_codename"], "demo")
            self.assertTrue(record["build"]["reported_success"])
            self.assertFalse(record["validation"]["boot_tested"])
            self.assertFalse(record["validation"]["hardware_tested"])

    def test_write_manifest_is_parseable_json(self):
        with tempfile.TemporaryDirectory() as temp:
            artifact = Path(temp) / "boot.img"
            artifact.write_bytes(b"image")
            output = write_artifact_manifest(artifact, codename="demo")
            data = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(data["artifact"]["filename"], "boot.img")
            self.assertEqual(data["artifact"]["size_bytes"], 5)

    def test_missing_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(FileNotFoundError):
                describe_artifact(Path(temp) / "missing.zip")


if __name__ == "__main__":
    unittest.main()
