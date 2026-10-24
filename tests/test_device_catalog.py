"""Guardrails for the reviewed device compatibility catalog."""
import json
import unittest
from pathlib import Path

CATALOG = Path(__file__).resolve().parents[1] / "data" / "device_catalog.json"


class DeviceCatalogTests(unittest.TestCase):
    def test_known_user_devices_are_unverified_not_supported(self):
        data = json.loads(CATALOG.read_text(encoding="utf-8"))
        devices = data["devices"]
        self.assertGreaterEqual(len(devices), 2)
        by_model = {model: entry for entry in devices for model in entry["model_ids"]}
        for model in ("G2199", "SM-A042F"):
            self.assertIn(model, by_model)
            self.assertEqual(by_model[model]["status"], "INVESTIGATING")
            self.assertEqual(by_model[model]["ubuntu_touch_port"], "UNKNOWN")
            self.assertIsNone(by_model[model]["installation_procedure"])
            self.assertIsNone(by_model[model]["recovery_procedure"])

    def test_catalog_entries_follow_evidence_schema(self):
        data = json.loads(CATALOG.read_text(encoding="utf-8"))
        for device in data["devices"]:
            self.assertIn("architecture", device)
            self.assertIn("required_android_base", device)
            self.assertIn("evidence", device)
            for evidence in device["evidence"]:
                for key in ("claim", "source_url", "source_type", "review_status", "checked_at", "notes"):
                    self.assertIn(key, evidence)
                self.assertIn(evidence["review_status"], {"UNREVIEWED", "REVIEWED", "REJECTED"})
            if device["status"] == "SUPPORTED":
                self.assertIsNotNone(device["installation_procedure"])
                self.assertIsNotNone(device["recovery_procedure"])
                self.assertTrue(any(e["review_status"] == "REVIEWED" for e in device["evidence"]))

    def test_catalog_does_not_claim_support_without_evidence(self):
        data = json.loads(CATALOG.read_text(encoding="utf-8"))
        for device in data["devices"]:
            if device["status"] != "SUPPORTED":
                self.assertIsNone(device["installation_procedure"])


if __name__ == "__main__":
    unittest.main()
