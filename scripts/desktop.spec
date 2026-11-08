# PyInstaller one-folder desktop build. Run after `npm run build` in frontend/.
# Output: pyinstaller --distpath releases --workpath .cache/pyinstaller scripts/desktop.spec
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, copy_metadata
import PySide6
import sys

root = Path(SPECPATH).parent
# Missing hidden imports only warn in PyInstaller, producing a broken release.
from importlib.util import find_spec
required = ("torch", "transformers", "safetensors", "faster_whisper", "onnxruntime", "onnx_asr")
missing = [name for name in required if find_spec(name) is None]
if missing:
    raise SystemExit("Missing desktop inference runtimes: " + ", ".join(missing)
                     + ". Install the desktop extra and one accelerator extra before packaging.")
a = Analysis(
    [str(root / "backend" / "videoflow" / "desktop_entry.py")],
    pathex=[str(root / "backend")],
    binaries=[],
    datas=[
        (str(root / "backend" / "videoflow" / "engines" / "manifest.toml"), "videoflow/engines"),
        (str(root / "assets" / "fonts"), "assets/fonts"),
        (str(root / "assets" / "icons"), "assets/icons"),
        (str(root / "docs" / "reference" / "desktop-runtime.md"), "notices"),
    ] + collect_data_files("opentimelineio") + copy_metadata("opentimelineio")
      # onnx_asr reads its own version with importlib.metadata on import.
      + copy_metadata("onnx-asr"),
    hiddenimports=["videoflow.editor.analysis", "videoflow.engines.asr.parakeet_onnx",
                   "videoflow.engines.vad.silero_onnx", "videoflow.engines.downloads",
                   "videoflow.engines.summary", "transformers.models.qwen2.modeling_qwen2",
                   "transformers.models.qwen2.tokenization_qwen2_fast", "opentimelineio.adapters.otio_json",
                   "opentimelineio.adapters.otioz", "opentimelineio.adapters.file_bundle_utils"],
    hookspath=[], runtime_hooks=[], noarchive=False,
    # "__main__" is listed because PyInstaller appends it to this list in place otherwise,
    # which makes every later build see changed excludes and redo the whole analysis.
    excludes=["tkinter", "__main__"],
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
# The built interface is added after Analysis: it changes on every frontend build, and as an
# Analysis input it would force the whole (slow) dependency analysis to run again.
dist = root / "frontend" / "dist"
a.datas += [(str(Path("frontend/dist") / f.relative_to(dist)), str(f), "DATA")
            for f in dist.rglob("*") if f.is_file()]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Video-Flow", debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          icon=str(root / "assets" / "icons" / "video-flow.ico"))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Video-Flow")
