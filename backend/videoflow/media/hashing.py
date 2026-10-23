"""Content hash of media files (ING-04 duplicate detection, cache keys).

Files up to `FULL_HASH_LIMIT` are hashed in full. Larger rushes are fingerprinted from their
size plus `SAMPLE_COUNT` evenly spaced chunks (first and last included): this reads a fixed
amount of data, and two different camera files of equal size matching on every sampled chunk
is not a practical risk. The hash is a lowercase hex string, safe in file names.
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

FULL_HASH_LIMIT = 64 * 1024 * 1024
SAMPLE_CHUNK = 1024 * 1024
SAMPLE_COUNT = 16
READ_CHUNK = 4 * 1024 * 1024
DIGEST_BYTES = 20
KEY_LENGTH = 16


def content_hash_sync(path: Path | str) -> str:
    p = Path(path)
    size = p.stat().st_size
    h = hashlib.blake2b(digest_size=DIGEST_BYTES)
    h.update(size.to_bytes(8, "little"))
    with p.open("rb") as f:
        if size <= FULL_HASH_LIMIT:
            while chunk := f.read(READ_CHUNK):
                h.update(chunk)
        else:
            span = size - SAMPLE_CHUNK
            for i in range(SAMPLE_COUNT):
                f.seek(span * i // (SAMPLE_COUNT - 1))
                h.update(f.read(SAMPLE_CHUNK))
    return h.hexdigest()


async def content_hash(path: Path | str) -> str:
    return await asyncio.to_thread(content_hash_sync, path)


def cache_key(content_hash_hex: str, *parts: object) -> str:
    """Short file-name-safe key for a cached artefact of `content_hash_hex` and parameters."""
    base = content_hash_hex[:KEY_LENGTH]
    if not parts:
        return base
    tag = hashlib.blake2b("|".join(map(str, parts)).encode(), digest_size=4).hexdigest()
    return f"{base}-{tag}"
