"""Content addressing, manifests and seed derivation."""

from __future__ import annotations

from pathlib import Path

import pytest

from etno_twin.kernel.hashing import fingerprint, fingerprint_directory, sha256_file
from etno_twin.kernel.manifest import (
    MANIFEST_SCHEMA,
    Manifest,
    inputs_by_role,
    manifest_path,
    read_manifest,
)
from etno_twin.kernel.rng import derive_seed, stream


def test_a_manifest_round_trips(tmp_path: Path) -> None:
    artifact = tmp_path / "detections.csv"
    artifact.write_text("ObjID\n", encoding="utf-8")
    path = Manifest(
        stage="campaign",
        experiment={"name": "test", "config_sha256": "0" * 64},
        outputs=[fingerprint(artifact, "detections")],
        seeds={"master": 1, "simulator": {"base": 42}},
    ).write(manifest_path(tmp_path, "campaign"))

    payload = read_manifest(path)
    assert payload["schema"] == MANIFEST_SCHEMA
    assert payload["stage"] == "campaign"
    assert payload["seeds"]["simulator"]["base"] == 42
    assert payload["outputs"][0]["sha256"] == sha256_file(artifact)
    assert "package_version" in payload["code"]


def test_a_foreign_json_file_is_not_read_as_a_manifest(tmp_path: Path) -> None:
    stray = tmp_path / "stray.manifest.json"
    stray.write_text('{"schema": "something/else@1"}', encoding="utf-8")
    with pytest.raises(ValueError, match="not an"):
        read_manifest(stray)


def test_inputs_are_recoverable_by_role(tmp_path: Path) -> None:
    """How a stage cites what an earlier stage established without importing it."""
    external = tmp_path / "pointing.csv"
    external.write_text("observationId\n", encoding="utf-8")
    path = Manifest(
        stage="snapshot",
        experiment={"name": "test"},
        inputs=[fingerprint(external, "pointing_table")],
    ).write(manifest_path(tmp_path, "snapshot"))
    assert inputs_by_role(path)["pointing_table"]["sha256"] == sha256_file(external)


def test_a_directory_fingerprint_is_stable_and_content_addressed(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    (cache / "nested").mkdir(parents=True)
    (cache / "a.bsp").write_bytes(b"kernel a")
    (cache / "nested" / "b.tls").write_bytes(b"kernel b")

    first = fingerprint_directory(cache)
    assert first.file_count == 2
    assert first.total_bytes == len(b"kernel a") + len(b"kernel b")
    assert fingerprint_directory(cache).digest == first.digest

    (cache / "a.bsp").write_bytes(b"kernel A")
    assert fingerprint_directory(cache).digest != first.digest


def test_derived_seeds_are_deterministic() -> None:
    assert derive_seed(20260825, "draw-0000") == derive_seed(20260825, "draw-0000")


def test_neighbouring_labels_do_not_give_neighbouring_seeds() -> None:
    """The simulator's own source warns that incremented seeds correlate between runs."""
    first = derive_seed(20260825, "draw-0000")
    second = derive_seed(20260825, "draw-0001")
    assert abs(first - second) > 1_000_000


def test_a_different_master_seed_gives_a_different_campaign() -> None:
    assert derive_seed(1, "draw-0000") != derive_seed(2, "draw-0000")


def test_streams_derived_for_different_labels_diverge_immediately() -> None:
    left = [stream(7, "population/draw-0000").random() for _ in range(5)]
    right = [stream(7, "population/draw-0001").random() for _ in range(5)]
    assert left != right
