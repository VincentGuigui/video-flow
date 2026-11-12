# Video-Flow documentation

Start with the [project README](../README.md) for what Video-Flow does and how to install and run it. The [roadmap](roadmap.md) lists what is built and what comes next; the [release notes](release_notes.md) list the changes per version (FEATURE, IMPROVEMENT, FIX, DEV), from which GitHub release texts are built.

| Folder | Content |
|--------|---------|
| [product/](product/) | What the product is meant to do: [functional specification](product/functional-spec.md) (goals, glossary, requirements with their priority and status) |
| [features/](features/README.md) | The user manual: the end-to-end workflow, then one page per built feature in one subfolder per stage. They describe the current behaviour |
| [architecture/](architecture/) | How it is built: [overview](architecture/overview.md), [desktop shell](architecture/desktop-shell.md), [data model](architecture/data-model.md), [analysis pipeline](architecture/analysis-pipeline.md), [render and export](architecture/render-export.md), [transitions, effects, titles, keyframes and still clips](architecture/effects-and-titles.md), [editor behaviour](architecture/editor-behaviour.md), [projects, cache and FFmpeg](architecture/projects-and-setup.md) |
| [decisions/](decisions/) | Dated decision records, numbered in order. Kept as history |
| [reference/](reference/) | [Dependencies](reference/dependencies.md) (versions, licences, accelerators), [desktop runtime](reference/desktop-runtime.md), [workspace layout](reference/workspace-layout.md), [automated releases](reference/github-releases.md) |
| [validation/](validation/) | Dated validation records: tests and checks, on real hardware where noted |

## User manual

The [user manual](features/README.md) starts with the end-to-end workflow and lists one page per feature, by stage: [getting started](features/getting-started/), [import and analysis](features/import-analysis/), [editing](features/editing/), [finishing](features/finishing/), [output](features/output/). Releases are built as described in [automated releases](reference/github-releases.md).

## Decisions

| Record | Content |
|--------|---------|
| [0000 Initial roadmap](decisions/0000-initial-roadmap.md) | First phase plan, risk register, open questions |
| [0001 Feasibility](decisions/0001-feasibility.md) | Feasibility study and state of the art |
| [0002 Review and plan](decisions/0002-review-and-plan.md) | Stack review, verified hypotheses, NPU → GPU → CPU policy, implementation plan |
| [0003 Camtasia findings](decisions/0003-camtasia-findings.md) | What the user's Camtasia projects use, and the feature backlog drawn from them |
| [0004 Keyframes replace zoom](decisions/0004-keyframes-replace-zoom.md) | Keyframed transforms replace zoom & pan, without migration |

## Writing rules

- A new feature gets a page in the stage subfolder of `features/` (or a section in the closest page) and a row in the [user manual](features/README.md); `README.md`, the [roadmap](roadmap.md) and the [release notes](release_notes.md) (one `- TYPE: text` line per change) are updated in the same change.
- A replaced or removed behaviour is amended everywhere in `docs/`, so no document describes something that no longer exists. Decision records are history and are not rewritten.
- Architecture documents describe the system as built; keep them in step with the code when a change affects them.
