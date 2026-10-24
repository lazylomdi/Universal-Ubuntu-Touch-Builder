import json
import unittest
from urllib.error import URLError
import source_discovery

class Response:
    def __init__(self, payload):
        self.payload = payload
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self):
        return json.dumps(self.payload).encode("utf-8")

class SourceDiscoveryTests(unittest.TestCase):
    def test_results_are_candidates_not_verified(self):
        response = Response({"items": [{"full_name": "example/device_xperia_r1",
            "html_url": "https://github.com/example/device_xperia_r1",
            "default_branch": "main", "updated_at": "2026-01-01T00:00:00Z",
            "description": "possible match"}]})
        result = source_discovery.discover_github_candidates("Xperia R1", opener=lambda *a, **k: response)
        self.assertEqual(result["status"], "CANDIDATE")
        self.assertEqual(result["candidates"][0]["evidence_status"], "CANDIDATE")
        self.assertIn("not proof", result["candidates"][0]["warning"])

    def test_network_failure_is_reported_not_raised(self):
        def fail(*args, **kwargs):
            raise URLError("offline")
        result = source_discovery.discover_github_candidates("Xperia R1", opener=fail)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertEqual(result["candidates"], [])
        self.assertIn("URLError", result["error"])

    def test_empty_query_is_rejected(self):
        self.assertEqual(source_discovery.discover_github_candidates(" ")["status"], "UNKNOWN")

if __name__ == "__main__":
    unittest.main()
