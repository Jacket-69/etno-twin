"""Shared fixtures.

Paths inside an experiment configuration resolve against the working directory, and the
documented working directory is the repository root. The tests adopt the same rule rather
than a second one of their own.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from etno_twin.kernel.config import ExperimentConfig, load_experiment

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _run_from_repository_root() -> Iterator[None]:
    previous = Path.cwd()
    os.chdir(REPO_ROOT)
    try:
        yield
    finally:
        os.chdir(previous)


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def fake_experiment() -> ExperimentConfig:
    """The configuration continuous integration runs, loaded as the stages see it."""
    return load_experiment(REPO_ROOT / "experiments" / "smoke-fake.toml")


@pytest.fixture
def sorcha_experiment() -> ExperimentConfig:
    return load_experiment(REPO_ROOT / "experiments" / "smoke-sorcha.toml")


@pytest.fixture
def sorcha_log_excerpt() -> str:
    return (REPO_ROOT / "fixtures" / "logs" / "sorcha-run-excerpt.log").read_text(encoding="utf-8")
