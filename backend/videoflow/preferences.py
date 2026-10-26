"""Validated application preferences, independent of project editing decisions."""

from typing import Literal

from videoflow.core.base import CamelModel
from videoflow.project.store import save_atomic
from videoflow.runtime import application_dir


class Preferences(CamelModel):
    summary_engine: Literal["deterministic", "qwen"] = "deterministic"
    asr_engine: Literal["parakeet", "faster-whisper"] = "parakeet"
    ai_device: Literal["auto", "cpu", "gpu", "npu"] = "auto"
    analyse_imports: bool = True
    render_preset: Literal["draft", "final"] = "final"
    normalize_audio: bool = True


def load_preferences() -> Preferences:
    path = application_dir() / "settings.json"
    if not path.exists():
        return Preferences()
    return Preferences.model_validate_json(path.read_bytes())


def save_preferences(preferences: Preferences) -> None:
    save_atomic(
        application_dir() / "settings.json",
        preferences.model_dump_json(by_alias=True, indent=2).encode(),
    )


def required_models(preferences: Preferences) -> list[str]:
    result = [
        "silero-vad",
        "faster-whisper-tiny"
        if preferences.asr_engine == "faster-whisper"
        else "parakeet-tdt-0.6b-v3-int8",
    ]
    if preferences.summary_engine == "qwen":
        result.append("qwen2.5-0.5b-instruct")
    return result
