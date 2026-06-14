"""Part 3 of the determinism audit: can the clique cover *repartition*?

The #952 sort canonicalizes a *reordering* of a fixed clique partition, but not a
*repartition* (a genuinely different grouping of stabilizers). For each open-port
gallery example this reconstructs the exact compatibility graph that
``fill_ports_for_minimal_simulation`` builds and brute-force enumerates all
distinct minimum clique-cover partitions: exactly one => the sort fully
canonicalizes; more than one => a boundary case the sort cannot protect.

Full rationale and results: see FINDINGS.md, Part 3.
"""

from __future__ import annotations

from itertools import combinations, product

from tqec.computation.open_graph import _is_compatible_paulis
from tqec.gallery.cnot import cnot
from tqec.gallery.cz import cz
from tqec.gallery.move_rotation import move_rotation
from tqec.gallery.steane_encoding import steane_encoding
from tqec.gallery.three_cnots import three_cnots

# All open-port gallery examples. ``cz`` is included here (the clique-cover
# analysis only needs ``find_correlation_surfaces``, which works for it) even
# though it cannot yet be compiled to a Stim circuit for the Part 2 test.
EXAMPLES = {
    "cnot": cnot,
    "three_cnots": three_cnots,
    "move_rotation": move_rotation,
    "steane_encoding": steane_encoding,
    "cz": cz,
}


def generators_for(example: str) -> list[str]:
    """Reconstruct the stabilizer generators exactly as open_graph.py does."""
    graph = EXAMPLES[example]()
    correlation_surfaces = graph.find_correlation_surfaces()
    stab_to_surface = {s.external_stabilizer_on_graph(graph): s for s in correlation_surfaces}
    return list(stab_to_surface.keys())


def incompatible_edges(generators: list[str]) -> set[tuple[int, int]]:
    """Edges of the complement graph that ``greedy_color`` colors (incompatible pairs)."""
    n = len(generators)
    return {
        (i, j)
        for i, j in combinations(range(n), 2)
        if not _is_compatible_paulis(generators[i], generators[j])
    }


def is_proper(coloring: tuple[int, ...], edges: set[tuple[int, int]]) -> bool:
    return all(coloring[i] != coloring[j] for i, j in edges)


def partition_of(coloring: tuple[int, ...], generators: list[str]) -> frozenset[frozenset[str]]:
    """Map a coloring to its partition: a set of cliques, each a set of stabilizers."""
    classes: dict[int, set[str]] = {}
    for node, color in enumerate(coloring):
        classes.setdefault(color, set()).add(generators[node])
    return frozenset(frozenset(c) for c in classes.values())


def all_minimum_partitions(
    generators: list[str], edges: set[tuple[int, int]]
) -> tuple[int, set[frozenset[frozenset[str]]]]:
    """Brute-force the chromatic number and ALL distinct minimum-color partitions."""
    n = len(generators)
    for num_colors in range(1, n + 1):
        partitions: set[frozenset[frozenset[str]]] = set()
        for coloring in product(range(num_colors), repeat=n):
            # require all colors used so we only count genuine `num_colors` covers
            if len(set(coloring)) != num_colors:
                continue
            if is_proper(coloring, edges):
                partitions.add(partition_of(coloring, generators))
        if partitions:
            return num_colors, partitions
    return n, set()


def report(label: str, generators: list[str]) -> int:
    """Print the partition analysis for a generator set; return #distinct partitions."""
    edges = incompatible_edges(generators)
    min_cliques, partitions = all_minimum_partitions(generators, edges)
    print(f"\n=== {label} ===")
    print(f"  generators ({len(generators)}): {generators}")
    print(f"  incompatible pairs: {len(edges)}")
    print(f"  minimum #cliques (chromatic number of complement): {min_cliques}")
    print(f"  distinct minimum clique-cover PARTITIONS: {len(partitions)}")
    verdict = (
        "UNIQUE -> sorting fully canonicalizes; #952 complete for this case"
        if len(partitions) == 1
        else "MULTIPLE -> genuine repartition; sort fix does NOT make this deterministic"
    )
    print(f"  verdict: {verdict}")
    if len(partitions) > 1:
        for p in sorted(partitions, key=lambda part: sorted(sorted(c) for c in part)):
            print("    partition:", sorted(sorted(c) for c in p))
    return len(partitions)


def main() -> None:
    print("# Current gallery examples (open ports)")
    for example in EXAMPLES:
        report(example, generators_for(example))

    print("\n\n# Synthetic boundary case (NOT reachable from the current gallery)")
    print(
        "# Two independent, disjoint-support incompatible pairs: X/Z on ports {0,1}\n"
        "# and X/Z on ports {2,3}. The incompatibility-complement graph is then\n"
        "# bipartite but DISCONNECTED (two separate edges), so it admits two\n"
        "# genuinely different minimum 2-clique covers. Sorting each cover and the\n"
        "# covers themselves yields two DIFFERENT canonical results, so the #952\n"
        "# sort cannot make a generator set with this structure deterministic."
    )
    synthetic = ["XXII", "ZZII", "IIXX", "IIZZ"]
    report("synthetic_disconnected_repartition", synthetic)


if __name__ == "__main__":
    main()
