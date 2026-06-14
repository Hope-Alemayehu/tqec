"""Empirical determinism check for PR #952 (issue #825).

Asserts the generated Stim circuit text for every open-port gallery example is
byte-identical across repeated in-process regenerations and across separate
interpreter runs with ``PYTHONHASHSEED`` in {0, 1, 2, 42} (the seed must be set
before interpreter start, hence a fresh ``subprocess`` per seed).

Two tiers, because detector computation is ~20x the cost of the rest:
  * detector-free (``manhattan_radius=-1``): ALL examples, k in {1,2}. Fast.
  * full circuit (``manhattan_radius=2``, incl. DETECTOR): subset, marked ``slow``.

Run:
    pytest determinism_audit/test_determinism.py -v                 # fast tier
    pytest determinism_audit/test_determinism.py -v -m slow         # + detectors

Full rationale (the four #825 ordering categories): see FINDINGS.md, Part 2.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from determinism_audit.generate_circuit import EXAMPLES, circuit_sha

REPO_ROOT = Path(__file__).resolve().parent.parent
HASH_SEEDS = ("0", "1", "2", "42")
KS = (1, 2)
# Representative subset for the expensive full-detector tier.
FULL_SUBSET = ("cnot", "move_rotation")


def _subprocess_sha(example: str, k: int, manhattan_radius: int, seed: str) -> str:
    """Generate the circuit SHA in a fresh interpreter with PYTHONHASHSEED=seed."""
    env = {**os.environ, "PYTHONHASHSEED": seed}
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "determinism_audit.generate_circuit",
            "--example",
            example,
            "--k",
            str(k),
            "--mr",
            str(manhattan_radius),
        ],
        env=env,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip().splitlines()[-1]


# --------------------------------------------------------------------------- #
# Fast tier: detector-free, all examples, both k.
# --------------------------------------------------------------------------- #
@pytest.mark.timeout(300)
@pytest.mark.parametrize("example", sorted(EXAMPLES))
@pytest.mark.parametrize("k", KS)
def test_inprocess_regeneration_stable(example: str, k: int) -> None:
    shas = {circuit_sha(example, k, manhattan_radius=-1) for _ in range(3)}
    assert len(shas) == 1, f"{example} k={k}: in-process regeneration not stable: {shas}"


@pytest.mark.timeout(600)
@pytest.mark.parametrize("example", sorted(EXAMPLES))
@pytest.mark.parametrize("k", KS)
def test_cross_hashseed_stable(example: str, k: int) -> None:
    reference = circuit_sha(example, k, manhattan_radius=-1)
    seed_shas = {seed: _subprocess_sha(example, k, -1, seed) for seed in HASH_SEEDS}
    distinct = set(seed_shas.values()) | {reference}
    assert len(distinct) == 1, (
        f"{example} k={k}: circuit text depends on PYTHONHASHSEED:\n"
        f"  in-process: {reference}\n"
        + "\n".join(f"  seed={s}: {h}" for s, h in seed_shas.items())
    )


# --------------------------------------------------------------------------- #
# Slow tier: FULL circuit including DETECTOR instructions (all four categories).
# --------------------------------------------------------------------------- #
@pytest.mark.slow
@pytest.mark.timeout(3600)
@pytest.mark.parametrize("example", FULL_SUBSET)
@pytest.mark.parametrize("k", KS)
def test_full_circuit_cross_hashseed_stable(example: str, k: int) -> None:
    reference = circuit_sha(example, k, manhattan_radius=2)
    seed_shas = {seed: _subprocess_sha(example, k, 2, seed) for seed in HASH_SEEDS}
    distinct = set(seed_shas.values()) | {reference}
    assert len(distinct) == 1, (
        f"{example} k={k}: FULL circuit text depends on PYTHONHASHSEED:\n"
        f"  in-process: {reference}\n"
        + "\n".join(f"  seed={s}: {h}" for s, h in seed_shas.items())
    )
