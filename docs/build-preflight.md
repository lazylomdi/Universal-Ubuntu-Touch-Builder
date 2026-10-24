# Build preflight

Before starting a build, run a host-readiness check:

```bash
python romforge.py preflight --workdir ./romforge-src --backend local
```

Choose `--backend docker` or `--backend github-actions` to check that backend instead.

The check reports OS guidance, available disk space, best-effort installed RAM, and the executable tools needed by the selected backend. It does not install dependencies, change permissions, start a build, inspect device compatibility, or prove that a ROM will compile or boot.

## Interpreting results

- `OK`: the check found the expected resource/tool.
- `INFO`: informational platform detail.
- `WARNING`: review the recommendation before spending time or disk on a build.
- `UNKNOWN`: the check could not measure a value.
- `BLOCKED`: a required backend tool is missing or the work directory cannot be accessed. The command exits with status 2.

The 150 GiB disk and 16 GiB RAM figures are general planning guidance, not guarantees. Requirements vary by Android version, build configuration, and device tree. Passing preflight is not a device support claim.
