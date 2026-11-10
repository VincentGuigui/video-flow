# AI models and components

Transcription, summaries and retake grouping run on your computer. They need model files, downloaded once, and Python components that are part of the app. Nothing is downloaded without your request.

## Manage AI models

Open **Settings → AI models → Manage AI models…**. The window also opens by itself at start when a model needed for analysis is missing, and when an import waits for one.

For each model it shows what it is for, its licence, whether your current settings need it, its state (**Missing**, **Obsolete** when the app supports a newer version, **Up to date**), its download size and its size on disk. Per model:

- **Download** (or **Update** for an obsolete one), and **Cancel** while it downloads;
- **Remove** deletes its files; it can be downloaded again later. Removing is refused while an import runs or the model downloads.

When required models are missing, a notice offers to download them all and gives their total size. Models are stored in the `models/` folder of the application. Analysis files that already exist next to your media are reused without any model.

## Install components

At start, the **Install components** window also checks the components the chosen engines need (for example the Qwen runtime or Whisper), and whether the GPU really works:

- In a version run from the source code, missing components can be installed from the window, with progress and cancel; restart the app afterwards.
- In a downloaded release the components are included; if one is missing, reinstall the release.
- When the GPU (CUDA) is advertised but does not work, choose **Install CUDA libraries** or **Use CPU**. CPU always works, only slower. NVIDIA drivers must be installed on the system.

## Settings

| Setting | Choices |
|---------|---------|
| Summary engine | Simple built-in method, or Qwen (local model, downloaded on request) |
| Transcription engine | Parakeet TDT 0.6B v3, or Whisper |
| Inference device | Automatic (NPU, then GPU, then CPU), CPU, GPU preferred, NPU preferred |
| Render quality | Full resolution, or draft preview |
| Analyse new imports by default | On or off |

Settings are saved in `settings.json` next to the application.

## Technical notes

Models are pinned in `backend/videoflow/engines/manifest.toml` and stored in `models/` (`VIDEOFLOW_MODELS_DIR` points there). Download sizes are read from the Hugging Face Hub metadata of the pinned revision, then cached in `models/download-sizes.json`; sizes on disk follow the shared blob store and count each file once. Installing components and packaging are described in [desktop runtime](../../reference/desktop-runtime.md#inference-dependencies).
