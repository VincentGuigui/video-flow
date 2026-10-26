# PyInstaller one-folder desktop build. Run after `npm run build` in frontend/.
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, copy_metadata
import PySide6
import sys

root = Path(SPECPATH).parent
a = Analysis(
    [str(root / "backend" / "videoflow" / "desktop_entry.py")],
    pathex=[str(root / "backend")],
    binaries=[],
    datas=[
        (str(root / "frontend" / "dist"), "frontend/dist"),
        (str(root / "backend" / "videoflow" / "engines" / "manifest.toml"), "videoflow/engines"),
        (str(root / "docs" / "desktop-runtime.md"), "notices"),
    ] + collect_data_files("opentimelineio") + copy_metadata("opentimelineio"),
    hiddenimports=["videoflow.editor.analysis", "videoflow.engines.asr.parakeet_onnx",
                   "videoflow.engines.vad.silero_onnx", "videoflow.engines.downloads",
                   "videoflow.engines.summary", "transformers.models.qwen2.modeling_qwen2",
                   "transformers.models.qwen2.tokenization_qwen2_fast", "opentimelineio.adapters.otio_json",
                   "opentimelineio.adapters.otioz", "opentimelineio.adapters.file_bundle_utils"],
    hookspath=[], runtime_hooks=[], excludes=["tkinter"], noarchive=False,
)
# Pin the MSVC family to the working Qt wheel. Ambient PATH entries can otherwise
# inject a newer, mismatched runtime (for example an unrelated image-codec SDK).
qt_dir = Path(PySide6.__file__).parent
runtime = {p.name.lower(): str(p) for pattern in ("msvcp140*.dll", "vcruntime140*.dll", "concrt140.dll")
           for p in qt_dir.glob(pattern)}
if runtime:
    a.binaries = [(destination, runtime.get(Path(destination).name.lower(), source), kind)
                  for destination, source, kind in a.binaries]
    existing = {name.lower() for name, _, _ in a.binaries}
    a.binaries += [(name, source, "BINARY") for name, source in runtime.items() if name not in existing]
if sys.platform == "win32":
    # Qt 6.12 uses Windows' system ICU (unsuffixed entry points). An unrelated
    # Poppler/Conda ICU found on PATH is ABI-incompatible and must not be bundled.
    system_icu = {"icuuc.dll", "icuin.dll", "icudt.dll"}
    a.binaries = [entry for entry in a.binaries if Path(entry[0]).name.lower() not in system_icu]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Video-Flow", debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Video-Flow")
