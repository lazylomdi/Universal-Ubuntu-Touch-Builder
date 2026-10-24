# Ubuntu Touch porting workflow

AndroidBuilder's current Android ROM build flow is not a universal Halium/Ubuntu Touch build flow. Ubuntu Touch ports combine a root filesystem, device-specific Halium/kernel integration, and the appropriate vendor components. Follow the version-specific upstream instructions rather than assuming a single build command.

References:

- [UBports porting introduction](https://docs.ubports.com/en/latest/porting/introduction/index.html)
- [Halium documentation](https://docs.halium.org/)
- [Halium first steps](https://docs.halium.org/en/latest/porting/first-steps.html)
- [UBports device directory](https://devices.ubuntu-touch.io/)
- [UBports community ports](https://gitlab.com/ubports/community-ports)

Do not flash automatically. Validate sources, exact revisions, license/provenance, build outputs, and device-specific installation steps before any hardware deployment. A physical device is ultimately needed to establish boot and hardware functionality.
