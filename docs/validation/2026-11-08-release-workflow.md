# Release workflow validation — 2026-11-08

Version 0.33.0. This record covers local workflow validation; GitHub-hosted builds and publication have not been triggered.

- actionlint 1.7.12 accepts .github/workflows/release.yml. All run blocks pass Git Bash syntax parsing.
- Three release-helper tests pass: mismatched versions rejected, complete ZIP structure and checksum verification, corrupted archives rejected, incomplete runtime rejected. Unix executable permission assertions run on Unix hosts.
- Backend Ruff lint/format checks pass (188 files). Frontend 93 tests and typecheck pass. uv lock --check and git diff --check pass.
- Metadata helper returns version 0.33.0, tag v0.33.0 and release name Video-Flow 0.33.0.
- Publication waits for Windows and Linux packaging and validates both SHA-256 files. Existing tag conflicts are checked before builds and again before tagging. Only publication has repository write permissions.
- Linux selects the locked CPU PyTorch wheel without unused Torch CUDA dependencies. Windows restores DirectML after installing Whisper, then verifies its provider is present before packaging.

The first GitHub run must validate the hosted runner environments, CPU wheel availability, platform package sizes and successful release upload. Runtime hardware qualification remains separate. No tag or GitHub release was created during this local validation.
