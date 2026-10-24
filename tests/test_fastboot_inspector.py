import subprocess
import unittest
from unittest.mock import patch

import fastboot_inspector


class FastbootInspectorTests(unittest.TestCase):
    @patch("fastboot_inspector.shutil.which", return_value="fastboot")
    @patch("fastboot_inspector._run")
    def test_reads_device_info_without_mutating_device(self, run, _which):
        run.side_effect = [
            subprocess.CompletedProcess(["fastboot", "devices"], 0, "ABC123\tfastboot\n", ""),
            subprocess.CompletedProcess(["fastboot", "getvar", "product"], 0, "", "product: QC_REFERENCE_PHONE\nFinished. Total time: 0.01s"),
            subprocess.CompletedProcess(["fastboot", "getvar", "unlocked"], 0, "", "unlocked: yes\nFinished. Total time: 0.01s"),
            subprocess.CompletedProcess(["fastboot", "getvar", "secure"], 0, "", "secure: no\nFinished. Total time: 0.01s"),
            subprocess.CompletedProcess(["fastboot", "getvar", "is-userspace"], 0, "", ""),
            subprocess.CompletedProcess(["fastboot", "oem", "device-info"], 0,
                "(bootloader) Device tampered: false\n(bootloader) Device unlocked: true\n(bootloader) Device critical unlocked: true\nOKAY", ""),
        ]
        result = fastboot_inspector.inspect_fastboot_device()
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["device"]["product"], "QC_REFERENCE_PHONE")
        self.assertIs(result["device"]["unlocked"], True)
        self.assertIs(result["device"]["critical_unlocked"], True)
        self.assertIs(result["device"]["tampered"], False)
        self.assertEqual(result["device"]["current_state"], "UNLOCKED (Fastboot-reported)")
        commands = [call.args[0] for call in run.call_args_list]
        self.assertTrue(all(not any(token in command for token in ("flash", "unlock", "erase", "format", "reboot")) for command in commands))

    @patch("fastboot_inspector.shutil.which", return_value="fastboot")
    @patch("fastboot_inspector._run")
    def test_no_fastboot_device_is_reported(self, run, _which):
        run.return_value = subprocess.CompletedProcess(["fastboot", "devices"], 0, "", "")
        result = fastboot_inspector.inspect_fastboot_device()
        self.assertEqual(result["status"], "ERROR")
        self.assertIn("No Fastboot device detected", result["message"])

    @patch("fastboot_inspector.shutil.which", return_value="fastboot")
    @patch("fastboot_inspector._run")
    def test_multiple_devices_require_serial(self, run, _which):
        run.return_value = subprocess.CompletedProcess(["fastboot", "devices"], 0, "A fastboot\nB fastboot\n", "")
        result = fastboot_inspector.inspect_fastboot_device()
        self.assertEqual(result["status"], "ERROR")
        self.assertIn("--serial SERIAL", result["message"])


if __name__ == "__main__":
    unittest.main()
