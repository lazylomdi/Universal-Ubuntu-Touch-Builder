import json
import tempfile
import unittest
from pathlib import Path
import ut_check

class ReadinessTests(unittest.TestCase):
    def test_missing_information_is_unknown(self):
        report = ut_check.assess_device("Sony", "Xperia R1", 2.0)
        self.assertEqual(report["assessment"], "UNKNOWN")
        self.assertIn("codename", report["missing_core_information"])
        self.assertTrue(all(x["status"] in ut_check.STATUSES for x in report["findings"]))

    def test_user_input_is_not_misrepresented_as_verified(self):
        report = ut_check.assess_device("Sony", "Xperia R1", 2.0, codename="candidate")
        by_key = {x["key"]: x for x in report["findings"]}
        self.assertEqual(by_key["manufacturer"]["status"], "CANDIDATE")
        self.assertIn("not independently verified", by_key["manufacturer"]["evidence"])
        self.assertEqual(by_key["kernel_source"]["status"], "UNKNOWN")

    def test_markdown_disclaims_functional_port(self):
        text = ut_check.render_markdown(ut_check.assess_device("Sony", "Xperia R1", 2.0))
        self.assertIn("No functional Ubuntu Touch port is established", text)
        self.assertIn("Physical device available", text)
        self.assertIn("## Compatibility summary", text)
        self.assertIn("Not enough information", text)
        self.assertIn("No independently verified Ubuntu Touch port evidence", text)

    def test_live_adb_values_are_labeled_device_reported(self):
        live_device = {
            "manufacturer": "Sony",
            "model": "G2199",
            "ram_gb": 1.83,
            "codename": "g2199",
            "android_version": "8.0.0",
            "kernel_version": "3.18.71",
            "bootloader_unlock": None,
            "extra_properties": {},
            "bootloader_assessment": {
                "current_state": "LOCKED (device-reported)",
                "evidence": "Read-only device property; not independently verified."
            },
            "data_storage": {}
        }
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "report.json"
            with patch("ut_check.inspect_device", return_value={
                "status": "OK", "message": "Inspection completed", "serial": "test-serial",
                "device": live_device, "devices": [], "limitations": []
            }):
                result = ut_check.main(["--inspect-device", "--json-out", str(output)])
            self.assertEqual(result, 0)
            report = json.loads(output.read_text(encoding="utf-8"))
        findings = {item["key"]: item for item in report["findings"]}
        self.assertIn("Read-only ADB inspection", findings["manufacturer"]["evidence"])
        self.assertNotIn("User-provided input", findings["manufacturer"]["evidence"])
        self.assertEqual(findings["manufacturer"]["status"], "CANDIDATE")
        self.assertIsNone(report["device"]["bootloader_unlock"])
        self.assertEqual(findings["bootloader_unlock_eligibility"]["status"], "UNKNOWN")
        self.assertEqual(findings["bootloader_current_state"]["status"], "CANDIDATE")

    def test_fastboot_inspection_is_included_in_report(self):
        from unittest.mock import patch
        fastboot = {
            "status": "OK",
            "message": "Read-only Fastboot inspection",
            "serial": "ABC123",
            "device": {
                "product": "QC_REFERENCE_PHONE",
                "unlocked": True,
                "critical_unlocked": True,
                "tampered": False,
                "secure": False,
                "is_userspace": None,
                "current_state": "UNLOCKED (Fastboot-reported)",
                "evidence": "Read-only Fastboot response."
            },
            "devices": [{"serial": "ABC123", "state": "fastboot"}],
            "limitations": ["No device state was changed."]
        }
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "fastboot-report.json"
            with patch("ut_check.inspect_fastboot_device", return_value=fastboot):
                result = ut_check.main(["--inspect-fastboot", "--json-out", str(output)])
            self.assertEqual(result, 0)
            report = json.loads(output.read_text(encoding="utf-8"))
        findings = {item["key"]: item for item in report["findings"]}
        self.assertEqual(findings["fastboot_product"]["value"], "QC_REFERENCE_PHONE")
        self.assertEqual(findings["fastboot_device_unlocked"]["value"], True)
        self.assertEqual(findings["bootloader_current_state"]["value"], "UNLOCKED (Fastboot-reported)")
        self.assertIn("Fastboot inspection", ut_check.render_markdown(report))
        self.assertTrue(report["physical_device_available"])

    def test_cli_writes_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as temp:
            json_path = Path(temp) / "nested" / "report.json"
            md_path = Path(temp) / "report.md"
            result = ut_check.main(["--json-out", str(json_path), "--markdown-out", str(md_path)])
            self.assertEqual(result, 0)
            data = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(data["device"]["ram_gb"], 2.0)
            self.assertTrue(md_path.exists())

    def test_invalid_ram_is_rejected(self):
        with self.assertRaises(SystemExit):
            ut_check.main(["--ram-gb", "0"])

if __name__ == "__main__":
    unittest.main()
