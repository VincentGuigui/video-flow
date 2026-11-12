# Automated GitHub releases

Open **Actions → Release → Run workflow**, select the branch containing the desired app version, and run it. The workflow builds Windows x64 (DirectML with CPU fallback) and Linux x64 (CPU) from the same commit. It reads the version from backend/pyproject.toml and checks backend/videoflow/__init__.py, frontend/package.json and the npm lock, and requires matching release notes. It does not invent or increment versions.

## Release notes

The release text follows the fixed template `.github/release-notes-template.md`:

```markdown
# How to install

* Extract the complete Video-Flow zip to a folder before running.


# What's new ?

{whats_new}
```

`{whats_new}` is filled from `docs/release_notes.md` with the entries of **every version since the previous GitHub release** up to the released version: first `FEATURE`, then `IMPROVEMENT`, then `FIX` entries (newest version first within each type), one `* ` line each, without their type. `DEV` entries are technical and left out; a release with only `DEV` entries says “Maintenance release: no visible change.” The previous release is the newest published (non-draft, non-prerelease) GitHub release older than the version, read with `gh release list`; re-running the release of a version gives the same text. Without any earlier release, every version up to it is listed.

`docs/release_notes.md` has one section per version, `## <version> — <date>`, with one line per change: `- <TYPE>: <short sentence for users>`, `TYPE` being `FEATURE`, `IMPROVEMENT`, `FIX` or `DEV` (the change types of conventional changelogs). The workflow refuses to build when a line does not follow this, or when the version has no section. Code: `scripts/release_artifacts.py` (`parse_notes`, `release_notes`), tested by `backend/tests/core/test_release_artifacts.py`.

## Publication

After both builds succeed, it verifies their checksums, creates the annotated tag `v<version>` at the built commit, then publishes **Video-Flow <version>**. For version 0.33.0 the assets are:

- `Video-Flow-0.33.0-windows-x64.zip`
- `Video-Flow-0.33.0-linux-x64.zip`
- A `.zip.sha256` checksum file for each ZIP.

The app's updater reads `releases/latest` and relies on these asset names, on the `.zip.sha256` format (`<hash>  <file name>`), on the top-level `Video-Flow/` folder and on the "What's new" bullets: keep them stable ([updates](../features/getting-started/updates.md)).

Each ZIP contains the complete generated `releases/Video-Flow/` folder under the top-level `Video-Flow/` directory, including the executable, `_internal/` and shortcut script. These are clean runner builds, so local models, projects, caches and preferences are not collected. FFmpeg and models are downloaded through the app on request. Linux ZIP entries preserve executable permissions when extracted with a compatible tool such as unzip.

An existing tag pointing to another commit is rejected before building and checked again before publishing. Rerunning the same tagged commit can update its release assets. Pushing a matching `v<version>` tag is also supported. Build jobs have read-only repository permissions; only publication receives contents:write. No extra repository secret is needed beyond the standard GITHUB_TOKEN. Repository tag rules must allow the release workflow to create version tags.

This workflow publishes only after successful packaging of both platforms; it does not replace the editor's test/qualification suite. SHA verification catches transfer damage, not platform runtime faults. CUDA is not included in these standard DirectML/CPU releases. Windows ARM64 is not part of the matrix. Linux uses the locked PyTorch version from the official CPU wheel index, omitting unused Torch CUDA dependencies to keep the CPU build within runner disk and release-asset limits. A failed build creates no automatic tag or release; a publishing failure after tagging can be retried from that tag.

Implementation: .github/workflows/release.yml, scripts/package_release.py and scripts/release_artifacts.py. Archives are checked for required runtime files, ZIP CRC integrity and the GitHub per-asset size limit before upload.
