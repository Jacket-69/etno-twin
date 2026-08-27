"""Seed derivation for a campaign.

The survey simulator's own source warns that re-using or casually incrementing seeds
between runs produces hard-to-detect correlations in the outputs. Campaign seeds are
therefore derived as independent streams from one recorded master seed, by hashing the
master seed together with a label, so neighbouring labels give unrelated streams.

Nothing here pins the simulator's seed. The simulator seeds itself from ``urandom`` by
design — its stochasticity is part of the forward model the inference has to learn — and
what this project owes is a *record* of the seed that was used, recovered from the run
log. See `docs/architecture/spike-sp1-integration-surface.md`.
"""

from __future__ import annotations

import hashlib
import random

_DIGEST_BYTES = 8
MAX_SEED = (1 << (8 * _DIGEST_BYTES)) - 1


def derive_seed(master_seed: int, label: str) -> int:
    """Derive one independent stream seed from a master seed and a label.

    Uses BLAKE2b over ``"<master>/<label>"``. Deterministic, so a campaign is auditable
    from the master seed alone, and diffusive, so ``draw-0000`` and ``draw-0001`` are not
    neighbouring integers.
    """
    payload = f"{master_seed}/{label}".encode()
    digest = hashlib.blake2b(payload, digest_size=_DIGEST_BYTES).digest()
    return int.from_bytes(digest, "big")


def stream(master_seed: int, label: str) -> random.Random:
    """A ``random.Random`` bound to the stream derived for ``label``."""
    return random.Random(derive_seed(master_seed, label))
