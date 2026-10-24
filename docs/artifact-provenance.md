# Artifact provenance report

After a build produces an output file, create a manifest:

```bash
python romforge.py artifact-report /path/to/rom.zip \
  --codename your_device_codename \
  --android-version 14 \
  --backend local \
  --jobs 4 \
  --build-succeeded
```

By default the JSON manifest is written beside the artifact as `<filename>.manifest.json`. Use `--output` to choose a different location. The command reads the existing file and streams a SHA-256 digest; it does not modify the artifact.

The manifest records file path/name, size, digest, timestamp, supplied build metadata, and environment information. It explicitly records that boot testing, hardware testing, and signature verification have not been performed by this command.

A digest is useful for detecting whether two files differ, but it does not establish who published a file. Only use `--build-succeeded` when the build tool actually reported success. Even then, success does not mean the artifact boots or that hardware functions work.

Avoid sharing manifests publicly without checking their full path fields for private directory names.
