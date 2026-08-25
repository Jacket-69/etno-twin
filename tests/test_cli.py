"""Smoke tests for the command-line entry point."""

from __future__ import annotations

import pytest

from etno_twin.cli import build_parser, main


def test_parser_has_program_name() -> None:
    assert build_parser().prog == "etno-twin"


def test_main_returns_zero_with_no_arguments(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "extreme trans-Neptunian" in capsys.readouterr().out
