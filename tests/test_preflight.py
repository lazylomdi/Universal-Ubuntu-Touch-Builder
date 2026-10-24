import tempfile
import unittest
from unittest.mock import patch

from preflight import run_preflight


class PreflightTests(unittest.TestCase):
    def test_preflight_is_read_only_with_respect_to_tool_installation(self):
        with tempfile.TemporaryDirectory() as temp, patch("preflight.shutil.which", return_value="/usr/bin/tool"), patch("preflight._available_ram_gb", return_value=32.0):
            report = run_preflight(temp, "local")
        self.assertTrue(report["ready"])
        self.assertIn("Passing preflight does not verify ROM source compatibility", report["limitations"][1])
        self.assertTrue(any(item["name"] == "Free disk space" for item in report["checks"]))

    def test_missing_docker_is_blocking_for_docker_backend(self):
        with tempfile.TemporaryDirectory() as temp, patch("preflight.shutil.which", return_value=None), patch("preflight._available_ram_gb", return_value=8.0):
            report = run_preflight(temp, "docker")
        self.assertFalse(report["ready"])
        self.assertTrue(any(item["name"] == "Tool: docker" and item["status"] == "BLOCKED" for item in report["checks"]))

    def test_unknown_backend_is_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            report = run_preflight(temp, "unknown")
        self.assertFalse(report["ready"])
        self.assertEqual(report["checks"][-1]["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
