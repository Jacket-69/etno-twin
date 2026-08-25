"""Command-line entry point.

Reproducing an experiment must cost one command; that is a committed metric of this
project, so the entry point exists from the first commit even though it does nothing
yet.
"""

from __future__ import annotations

import argparse

from etno_twin import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="etno-twin",
        description="Population-level inference on extreme trans-Neptunian objects.",
    )
    parser.add_argument("--version", action="version", version=f"etno-twin {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
