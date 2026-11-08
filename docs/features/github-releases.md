# Automated GitHub releases

Open **Actions → Release → Run workflow**, select the branch containing the desired app version, and run it. The workflow builds Windows x64 (DirectML with CPU fallback) and Linux x64 (CPU) from the same commit. It reads the version from backend/pyproject.toml and checks backend/videoflow/__init__.py, frontend/package.json and the npm lock, and requires matching release notes. It does not invent or increment versions.

After both builds succeed, it verifies their checksums, creates the annotated tag `v<version>` at the built commit, then publishes **Video-Flow <version>**. For version 0.33.0 the assets are:

- `Video-Flow-0.33.0-windows-x64.zip`
- `Video-Flow-0.33.0-linux-x64.zip`
- A `.zip.sha256` checksum file for each ZIP.

Each ZIP contains the complete generated `releases/Video-Flow/` folder under the top-level `Video-Flow/` directory, including the executable, `_internal/` and shortcut script. These are clean runner builds, so local models, projects, caches and preferences are not collected. FFmpeg and models are downloaded through the app on request. Linux ZIP entries preserve executable permissions when extracted with a compatible tool such as unzip.

An existing tag pointing to another commit is rejected before building and checked again before publishing. Rerunning the same tagged commit can update its release assets. Pushing a matching `v<version>` tag is also supported. Build jobs have read-only repository permissions; only publication receives contents:write. No extra repository secret is needed beyond the standard GITHUB_TOKEN. Repository tag rules must allow the release workflow to create version tags.

This workflow publishes only after successful packaging of both platforms; it does not replace the editor's test/qualification suite. SHA verification catches transfer damage, not platform runtime faults. CUDA is not included in these standard DirectML/CPU releases. Windows ARM64 is not part of the matrix. Linux uses the locked PyTorch version from the official CPU wheel index, omitting unused Torch CUDA dependencies to keep the CPU build within runner disk and release-asset limits. A failed build creates no automatic tag or release; a publishing failure after tagging can be retried from that tag.

Implementation: .github/workflows/release.yml, scripts/package_release.py and scripts/release_artifacts.py. Archives are checked for required runtime files, ZIP CRC integrity and the GitHub per-asset size limit before upload.
