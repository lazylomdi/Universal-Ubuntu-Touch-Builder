# Beginner-friendly cross-platform release roadmap

## Goal

Make AndroidBuilder usable by people with no Linux, Android ROM, command-line, or bootloader knowledge. The first public release targets **Windows and Linux** and aims to guide users from device discovery through compatibility assessment, supported ROM preparation/building, and installation/flashing where a device has a documented, verified procedure.

The UI must explain technical terms in plain language, make safe choices by default, and never imply that every Android device can be modified.

## Product principles

1. **Guide, do not assume expertise.** Use plain-language tasks, explain terms on demand, and show one recommended next step at a time.
2. **Evidence before claims.** Distinguish verified facts, device-reported clues, community candidates, unknowns, and blockers.
3. **Safety by default.** Inspection is read-only. Unlocking, wiping, rebooting to bootloader/recovery, sideloading, and flashing are separate explicit actions with device-specific checks and confirmations.
4. **No silent destructive actions.** Before any operation that can erase data or affect bootability, state the consequence, backup requirement, exact target device, source of instructions, and recovery path. Require a deliberate confirmation. Never bypass Android, OEM, or platform security protections.
5. **Platform clarity.** Support Windows and Linux as desktop platforms. Where Android build tools require Linux, provide a guided WSL2/Ubuntu route on Windows rather than pretending native Windows is equivalent.
6. **Recoverable and transparent.** Show logs in a secondary “Details” view, save a support bundle on request, verify downloaded artifacts where checksums/signatures exist, and explain failures with next steps.
7. **Open-source readiness.** Document dependencies, licenses, privacy/data handling, supported devices and operations, known limitations, contribution workflow, and security reporting before public release.

## Milestone 1 — Beginner Mode foundation (next development milestone)

### Scope

- Add a beginner-oriented landing page with a primary **Check my phone** action and secondary paths for build/install tasks.
- Turn device inspection into a guided wizard: connect phone(s) → authorize USB debugging → identify each device → explicitly select one device → run read-only checks → explain results.
- Make multi-device use a first-class scenario: list every ADB device with model/name, serial, and state; summarize total/ready/unauthorized counts; update the selected-device summary when selection changes; and ensure inspection targets only the selected serial.
- Show manufacturer/model, Android version, device codename, CPU architecture, RAM/storage, and device image when a suitable source is found. Image results must include attribution/license/source and a fallback if no image is available.
- Present a clear compatibility summary using **Supported by evidence**, **Possible but unverified**, **Blocked by a known issue**, and **Not enough information**. Do not use a single score that hides uncertainty.
- Explain bootloader *current state* separately from OEM *unlock eligibility*. Label ADB properties as device-reported clues; never treat a missing or vendor-specific property as proof.
- Add a glossary/tooltips for ADB, ROM, device codename, bootloader, recovery, vendor blobs, kernel, and flashing.
- Keep raw logs and technical details available behind an expandable section for troubleshooting.
- Keep all existing CLI commands and reports working; do not remove advanced mode.

### Acceptance criteria

- A novice can discover a connected, authorized phone without opening a terminal and can understand each status and its next action.
- Missing ADB, unauthorized/offline devices, multiple devices, network errors, and unknown device models produce actionable messages.
- With two or more connected devices, all devices appear independently with their serial and ADB state; changing the selected row updates the selected-device details, and inspection passes only that row's serial to the checker.
- Unauthorized/offline devices remain visible but cannot be inspected until their state is resolved.
- Inspection remains read-only; automated tests verify no unlock/flash/erase command is issued by the inspection path.
- Unknown or conflicting bootloader evidence is displayed as uncertain, not silently converted to locked/unlocked.
- Tests run on supported Python versions, and the UI receives manual smoke tests on Windows and Linux before the milestone is called complete.

## Milestone 2 — Device support and compatibility catalog

- Create a structured, reviewable device catalog with model aliases, codenames, architecture, supported ROM/port status, required Android base, kernel/device-tree/vendor-source links, known limitations, and tested procedure references.
- Track evidence provenance, last-checked date, maintainer/reviewer, and confidence for each claim.
- Prefer upstream project documentation and maintained device repositories. Treat forum posts and unverified repository matches as leads, not proof.
- Support community submissions through a documented schema and review process.
- Provide “not supported yet” guidance instead of inventing a build configuration when evidence is missing.

### Acceptance criteria

- Every recommended build or installation path is tied to a device-specific source and has explicit prerequisites.
- A generic matching model name alone can never mark a device as supported.
- Stale or incomplete entries are visibly downgraded to unverified.

## Milestone 3 — Guided build and artifact management

- Convert the current build form into a step-by-step flow with sensible defaults and explanations.
- Run prerequisite checks before expensive downloads/builds: OS, disk space, memory, required tools, network, and selected target support.
- Explain expected download size, storage use, build duration uncertainty, and where files will be saved.
- Show real phases based on subprocess events where possible; do not fake percentage progress.
- Keep dry-run/review available and clearly separate a successful build from a boot-tested image.
- Record artifact provenance, target, build configuration, checksums, and build logs.

### Acceptance criteria

- Unsupported configurations fail before expensive work starts.
- Cancellation is handled safely and partial outputs are clearly identified.
- “Build succeeded” never implies “boots” or “hardware works” without separate test evidence.

## Milestone 4 — Supported installation and flashing workflows

This milestone is **device-specific**, not a universal flashing button.

- Implement a workflow only when authoritative or maintainer-reviewed instructions exist for the exact device and target.
- Before proceeding, verify the selected device identity, prerequisites, battery/USB guidance, required backup, bootloader state/eligibility where determinable, artifact identity and integrity, and recovery/restore instructions.
- Explain clearly if unlocking wipes user data; require a separate explicit confirmation immediately before that action.
- Separate actions into reviewable steps. Never unlock, erase, reboot, or flash automatically as a side effect of a check or build.
- Use supported platform tools with argument-list process execution, strict target selection, timeouts, captured logs, and safe error handling.
- Verify post-operation results where feasible, but report “not verified” when the app cannot independently confirm boot or hardware functionality.
- If the exact model, unlock status, artifact, or recovery path is uncertain, stop and explain what evidence is missing.

### Acceptance criteria

- No install/flash action can start until the device-specific procedure, exact target, prerequisites, artifact integrity, and consequences have been reviewed.
- Destructive actions require explicit, contextual confirmation and never run from an automatic “fix” or “check” action.
- Tests use mocks/fake executables for command construction and failure paths; real-device validation is limited to explicitly supported test devices.
- Every supported procedure has a recovery note and a clear “stop safely” path.

## Milestone 5 — Windows/Linux packaging and open-source release

- Build and test Windows packaging (installer or portable package) and Linux packaging (AppImage or distribution-appropriate package) from reproducible CI workflows.
- Detect missing platform tools and offer documented installation guidance. Do not silently elevate privileges or change system security settings.
- On Windows, guide users to WSL2/Ubuntu for build tasks that require Linux and clearly explain any USB/device pass-through limitations.
- Add automated unit tests, lint/static checks, dependency/license review, and packaging smoke tests on both platforms.
- Publish beginner documentation, screenshots, FAQ/troubleshooting, supported-device policy, privacy statement, security contact, license, contribution guide, and release notes.
- Do not bundle third-party binaries or device images unless their licensing and redistribution terms permit it.

### Acceptance criteria

- A clean Windows and Linux test environment can install/launch the app using documented steps.
- A user can generate a diagnostic/support report without exposing private identifiers by default.
- Release notes list known limitations and tested platform/device combinations.

## Suggested implementation order

1. **Now:** Milestone 1, while preserving the existing CLI and advanced UI.
2. **Next:** Milestone 2, because safe guided builds and installs depend on reliable device-specific evidence.
3. **Then:** Milestone 3, adding prerequisite checks and clear artifact/report handling.
4. **After verified device procedures exist:** Milestone 4, starting with a small number of well-documented test devices.
5. **Release gate:** Milestone 5 packaging, documentation, and cross-platform validation.

## Explicit non-goals for the first beginner milestone

- Universal support for all Android phones.
- Guessing device codenames or treating similar model names as interchangeable.
- Automatic bootloader unlocking, factory reset, partition changes, or flashing.
- Promising that a ROM will boot or that all hardware features will work based only on source discovery or build completion.
- Scraping copyrighted images or instructions from websites without permission.

## Definition of done for each milestone

A milestone is done only when the acceptance criteria are met, tests are added, user-facing limitations are documented, and manual validation is recorded for each claimed platform. Until then, label the feature experimental and keep destructive operations unavailable for unsupported devices.
