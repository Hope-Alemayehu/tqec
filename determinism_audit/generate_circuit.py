"""Worker: build the full Stim circuit for an open-port gallery example and
reduce it to a SHA-256, so byte-identical output is easy to compare across runs.

Used by ``test_determinism.py`` both as an import (``circuit_sha``) and via the
CLI (``python generate_circuit.py --example cnot --k 1 [--db PATH]``) for the
cross-``PYTHONHASHSEED`` subprocess runs. The ``__main__`` guard is required:
detector computation uses ``multiprocessing`` with Windows ``spawn``, which
re-imports this module.

Full rationale (the four #825 ordering categories): see FINDINGS.md, Part 2.
"""

from __future__ import annotations

import argparse
import hashlib

from tqec.compile.compile import compile_block_graph
from tqec.computation.block_graph import BlockGraph
from tqec.gallery.cnot import cnot
from tqec.gallery.move_rotation import move_rotation
from tqec.gallery.steane_encoding import steane_encoding
from tqec.gallery.three_cnots import three_cnots

# Every gallery example that has open ports AND can currently be compiled to a
# Stim circuit, so it exercises ``fill_ports_for_minimal_simulation`` (the
# function patched by #952) end-to-end. (``cz`` also has open ports but raises
# NotImplementedError during circuit generation today, so it is excluded here;
# it is still covered by the Part 3 clique-cover analysis.)
EXAMPLES = {
    "cnot": cnot,
    "three_cnots": three_cnots,
    "move_rotation": move_rotation,
    "steane_encoding": steane_encoding,
}

# A separator that cannot appear inside a stim circuit, so concatenating the
# per-filled-graph circuit texts is an injective fingerprint of the whole set
# (including the number and ORDER of filled graphs, which #952 fixes).
_SEP = "\n===== FILLED GRAPH BOUNDARY =====\n"


def circuit_texts(
    example: str, k: int, manhattan_radius: int = 2, database_path: str | None = None
) -> list[str]:
    """Return the full Stim circuit text for every filled graph of ``example``.

    The filled graphs are returned in the order produced by
    ``fill_ports_for_minimal_simulation`` (canonicalized by #952); we do NOT
    re-sort them, so this also captures the clique-ordering determinism.

    ``manhattan_radius=2`` (the production default) emits the complete circuit
    including ``DETECTOR`` instructions (all four #825 categories). A negative
    value skips detector computation -- much faster, and still exercises gate
    targets, qubit coords/indices, observable record targets, and the relative
    ordering of QUBIT_COORDS / OBSERVABLE_INCLUDE.
    """
    graph: BlockGraph = EXAMPLES[example]()
    filled = graph.fill_ports_for_minimal_simulation()
    texts: list[str] = []
    for fg in filled:
        circuit = compile_block_graph(
            fg.graph, observables=fg.observables
        ).generate_stim_circuit(
            k, manhattan_radius=manhattan_radius, database_path=database_path
        )
        texts.append(str(circuit))
    return texts


def circuit_sha(
    example: str, k: int, manhattan_radius: int = 2, database_path: str | None = None
) -> str:
    """SHA-256 over the concatenated full circuit text of all filled graphs."""
    joined = _SEP.join(circuit_texts(example, k, manhattan_radius, database_path))
    return hashlib.sha256(joined.encode()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--example", required=True, choices=sorted(EXAMPLES))
    parser.add_argument("--k", required=True, type=int)
    parser.add_argument(
        "--mr",
        type=int,
        default=2,
        help="manhattan_radius; 2 = full circuit incl detectors, -1 = skip detectors",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="detector database path; omit to recompute detectors from scratch",
    )
    args = parser.parse_args()
    # Print ONLY the hash on the last line so callers can parse it robustly.
    print(circuit_sha(args.example, args.k, args.mr, args.db))


if __name__ == "__main__":
    main()
