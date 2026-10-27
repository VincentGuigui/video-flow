"""Model manifest: pinned revisions, licence policy, gated-model refusal, local download."""

from __future__ import annotations

import re
import tomllib
from functools import cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

MANIFEST_PATH = Path(__file__).with_name("manifest.toml")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class ModelRefusedError(RuntimeError):
    """The model is gated, has a non-permitted licence or an unpinned revision."""


class ModelSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    purpose: str
    goal: str = ""
    """What the model does for the user, shown in Settings."""
    repo: str
    revision: str
    license: str
    gated: bool = False
    files: list[str] = Field(min_length=1)
    dim: int | None = None
    query_prefix: str = ""
    passage_prefix: str = ""
    max_length: int = 128


class Manifest(BaseModel):
    allowed_licenses: list[str]
    models: dict[str, ModelSpec]

    def check(self, spec: ModelSpec) -> None:
        """Raise :class:`ModelRefusedError` unless ``spec`` is pinned, open and permissive."""
        if spec.gated:
            raise ModelRefusedError(f"{spec.key}: gated model refused ({spec.repo})")
        if spec.license.lower() not in {x.lower() for x in self.allowed_licenses}:
            raise ModelRefusedError(f"{spec.key}: licence {spec.license!r} is not permitted")
        if not _SHA_RE.match(spec.revision):
            raise ModelRefusedError(f"{spec.key}: revision must be a 40-hex commit, not a branch")

    def get(self, key: str) -> ModelSpec:
        try:
            spec = self.models[key]
        except KeyError:
            raise KeyError(f"unknown model {key!r}; known: {sorted(self.models)}") from None
        self.check(spec)
        return spec


def parse_manifest(text: str) -> Manifest:
    raw = tomllib.loads(text)
    models = {k: ModelSpec(key=k, **v) for k, v in raw.get("models", {}).items()}
    allowed = raw.get("policy", {}).get("allowed_licenses", [])
    return Manifest(allowed_licenses=allowed, models=models)


@cache
def load_manifest(path: Path = MANIFEST_PATH) -> Manifest:
    return parse_manifest(Path(path).read_text(encoding="utf-8"))


def models_dir() -> Path:
    """Always the models subdirectory of this application."""
    from videoflow.runtime import model_directory

    return model_directory()


def fetch(key: str, manifest: Manifest | None = None) -> dict[str, Path]:
    """Download (or reuse) the pinned files of model ``key``; returns ``{file: local path}``."""
    man = manifest or load_manifest()
    spec = man.get(key)  # refuses gated / unpinned / non-permissive before any network call
    models_dir()
    from huggingface_hub import hf_hub_download
    from huggingface_hub.errors import GatedRepoError

    out: dict[str, Path] = {}
    try:
        for name in spec.files:
            out[name] = Path(
                hf_hub_download(
                    spec.repo, name, revision=spec.revision, cache_dir=models_dir() / "hf"
                )
            )
    except GatedRepoError as exc:
        raise ModelRefusedError(f"{key}: repository is gated ({spec.repo})") from exc
    return out
