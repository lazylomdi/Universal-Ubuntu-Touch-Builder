# Device compatibility catalog

The machine-readable catalog lives at `data/device_catalog.json`.

## Status policy

- `INVESTIGATING`: identity is recorded but compatibility evidence is incomplete.
- `SUPPORTED`: reserved for an exact device variant with reviewed evidence, prerequisites, an installation procedure, and a recovery procedure.
- `BLOCKED`: a known incompatibility or unmet prerequisite prevents the proposed procedure.

A model match, repository name, Android property, or successful compilation is not sufficient to mark a device supported. Add source URLs, review dates, reviewer identity, and limitations before raising a status. Never add an install procedure without a recovery path.

## Current investigation records

Sony Xperia R1 (G2199) and Samsung Galaxy A04e (SM-A042F, codename reported as a04e) are listed as `INVESTIGATING`. This records the user's devices, not a claim that either can run Ubuntu Touch. No flash/install procedure is enabled for either device.

## Contribution checklist

1. Confirm the exact model/region/variant and codename.
2. Add authoritative upstream or maintainer-reviewed source URLs.
3. Verify bootloader unlock eligibility separately from current lock state.
4. Record kernel, device-tree, vendor source, partition layout, and required Android base.
5. Link a device-specific installation and recovery procedure, reviewed for the exact variant.
6. Record test evidence for boot and individual hardware features separately.
7. Set a reviewer and review date. Re-review stale entries before recommending any procedure.
