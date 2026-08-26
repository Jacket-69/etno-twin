"""Content addressing for artifacts.

Every file that crosses a stage boundary is fingerprinted, and so is every external
input the experiment consumes — including the survey simulator's demo files, which are
snapshots like any other (`docs/data/provenance.md`).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_CHUNK_BYTES = 1 << 20


def sha256_file(path: Path) -> str:
    """Hex SHA-256 of a file, read in chunks so 780 MB ephemeris kernels are fine."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class FileFingerprint:
    """Identity of one file: what it is called, how big it is, what it contains."""

    role: str
    path: str
    bytes: int
    sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {"role": self.role, "path": self.path, "bytes": self.bytes, "sha256": self.sha256}


def fingerprint(path: Path, role: str) -> FileFingerprint:
    resolved = path.resolve()
    return FileFingerprint(
        role=role,
        path=str(resolved),
        bytes=resolved.stat().st_size,
        sha256=sha256_file(resolved),
    )


def fingerprint_all(items: Iterable[tuple[str, Path]]) -> list[FileFingerprint]:
    return [fingerprint(path, role) for role, path in items]


@dataclass(frozen=True)
class DirectoryFingerprint:
    """Identity of a directory of external data — the ephemeris cache, in practice.

    Files are hashed in full rather than summarised by size and modification time: a
    result depends on which ephemerides produced it, and a reviewer asking "why mtime?"
    is a question with no good answer. Hashing the cache costs a couple of seconds and
    happens once per campaign, outside every timed region.
    """

    path: str
    file_count: int
    total_bytes: int
    digest: str
    files: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "file_count": self.file_count,
            "total_bytes": self.total_bytes,
            "digest": self.digest,
            "files": self.files,
        }


def fingerprint_directory(path: Path) -> DirectoryFingerprint:
    """Hash every regular file in a directory tree and fold them into one digest.

    The folded digest is order-independent of the filesystem: entries are sorted by
    relative path before folding, so the same cache on two machines produces the same
    value.
    """
    resolved = path.expanduser().resolve()
    entries: list[dict[str, Any]] = []
    for candidate in sorted(p for p in resolved.rglob("*") if p.is_file()):
        entries.append(
            {
                "name": str(candidate.relative_to(resolved)),
                "bytes": candidate.stat().st_size,
                "sha256": sha256_file(candidate),
            }
        )
    folded = hashlib.sha256()
    for entry in entries:
        folded.update(f"{entry['name']}:{entry['sha256']}\n".encode())
    return DirectoryFingerprint(
        path=str(resolved),
        file_count=len(entries),
        total_bytes=sum(int(entry["bytes"]) for entry in entries),
        digest=folded.hexdigest(),
        files=entries,
    )
