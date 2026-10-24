# Device compatibility catalog schema

The machine-readable catalog lives at `data/device_catalog.json`. Entries are evidence records, not automatic support claims.

## Required device fields

- `manufacturer`, `model`, `model_ids`, `codenames`: exact identifiers and reviewed aliases.
- `status`: `INVESTIGATING`, `CANDIDATE`, `SUPPORTED`, or `BLOCKED`.
- `ubuntu_touch_port`: `UNKNOWN`, `CANDIDATE`, `VERIFIED`, or `BLOCKED`.
- `architecture`, `required_android_base`: use `null` when unknown; do not infer from similar devices.
- `bootloader_unlock`: `UNKNOWN`, `CANDIDATE`, `VERIFIED`, or `BLOCKED`. This refers to evidence about unlock eligibility, not the current lock state.
- `kernel_source`, `device_tree`, `vendor_sources`: URLs only when a source has been identified; source existence alone is not compatibility proof.
- `installation_procedure`, `recovery_procedure`: remain `null` until exact-variant instructions are reviewed and the recovery path is documented.
- `known_limitations`: plain-language caveats.
- `evidence`: list of evidence records, each with `claim`, `source_url`, `source_type`, `review_status`, `checked_at`, and `notes`.
- `last_reviewed`: ISO date or `null`.
- `reviewer`: reviewer handle/name or `null`.

## Evidence rules

1. `source_type` should describe the source (for example `upstream_documentation`, `maintainer_repository`, `manufacturer_documentation`, or `community_lead`).
2. `review_status` is `UNREVIEWED`, `REVIEWED`, or `REJECTED`. An unreviewed source is only a lead.
3. Only evidence reviewed for the exact model/variant can support a verified claim. Record the date and reviewer.
4. A model-name match or repository hit never establishes support by itself.
5. A device may be marked `SUPPORTED` only when device-specific installation and recovery procedures, prerequisites, limitations, and sources have been reviewed. Otherwise keep it unverified and leave procedure fields null.
6. A missing field means unknown, not “no” and not proof of incompatibility.
7. Never store device serial numbers, build fingerprints, or other user-specific inspection data in this shared catalog.
