import unittest

from desktop_ui.readiness_summary import summarize_readiness_report


REPORT = """# Ubuntu Touch readiness report: Sony Xperia R1

- **Assessment:** UNKNOWN
- **RAM (reported):** 1.83 GB
- **Conclusion:** No functional Ubuntu Touch port is established by this report.

## Findings

| Area | Value | Status | Evidence |
|---|---|---|---|
| existing_ubuntu_touch_port | Unknown | UNKNOWN | No independently verified evidence collected. |

## Compatibility summary

- **Status:** Not enough information
- **Next step:** No independently verified Ubuntu Touch port evidence is recorded for this exact device.
- This is an evidence summary, not a compatibility score or guarantee.

## How to interpret this report

- **UNKNOWN:** evidence is missing.
"""


class ReadinessSummaryTests(unittest.TestCase):
    def test_reads_actual_markdown_summary_section(self):
        summary = summarize_readiness_report(REPORT)
        self.assertIn("Device: Sony Xperia R1.", summary)
        self.assertIn("Compatibility: Not enough information.", summary)
        self.assertIn("Evidence assessment: UNKNOWN.", summary)
        self.assertIn("No independently verified Ubuntu Touch port evidence", summary)
        self.assertIn("do not prove port support", summary)

    def test_candidate_is_not_promoted_to_verified(self):
        report = REPORT.replace("Not enough information", "Possible but unverified")
        summary = summarize_readiness_report(report)
        self.assertIn("Compatibility: Possible but unverified.", summary)
        self.assertNotIn("Compatibility: Verified.", summary)

    def test_missing_summary_does_not_guess(self):
        summary = summarize_readiness_report("# Ubuntu Touch readiness report: Example\n")
        self.assertIn("Compatibility: not established", summary)

    def test_nonzero_exit_is_called_out(self):
        summary = summarize_readiness_report(REPORT, exit_code=2)
        self.assertIn("exit code 2", summary)
        self.assertIn("potentially incomplete", summary)

    def test_empty_report_is_handled(self):
        self.assertIn("no report content", summarize_readiness_report("", exit_code=1))


if __name__ == "__main__":
    unittest.main()
