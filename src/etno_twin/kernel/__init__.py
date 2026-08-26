"""Shared kernel: hashing, manifests, measurement and schema declarations.

The kernel is the bottom layer. It may not import stages or simulators, and it depends
on the standard library alone — the same property that lets the core run in an
environment with no Fortran toolchain and no scientific stack.
"""
