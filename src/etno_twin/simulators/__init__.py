"""Bindings of the survey-simulator port.

Two bindings, one contract. The workstation runs `sorcha_adapter`; continuous
integration runs `fake`, which needs no Fortran toolchain, no network and none of the
780 MB of ephemeris kernels. The campaign stage does not know which one it invoked
beyond the name in its configuration — it spawns a process and reads files back, for
both.

Nothing in this package imports the simulator it drives. The sorcha binding builds an
argument vector for sorcha's command-line interface and parses the log it writes, which
is the interface sorcha actually supports; its Python entry point takes file paths for
its arguments and calls `sys.exit` in sixty-five places, so process isolation is the only
robust boundary. The consequence is worth stating plainly: `import sorcha` appears
nowhere in this package, and an import-linter contract keeps it that way.
"""
