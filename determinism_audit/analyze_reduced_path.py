"""Does the reduced-generator path (search_small_area_observables=True) repartition?

The default path keeps ALL correlation surfaces, whose cross-terms lock the
minimum clique cover. The reduced path keeps a minimal generating set, which
could strip those locking terms. Run the production function across every
networkx coloring strategy and check whether the resulting clique partition
(set of stabilizer groups) is invariant.

Full rationale and results: see FINDINGS.md, Part 3.
"""

from __future__ import annotations

import networkx as nx

from tqec.computation.open_graph import fill_ports_for_minimal_simulation
from tqec.gallery.cnot import cnot

from determinism_audit.analyze_reachability import disjoint_union

STRATEGIES = [
    "largest_first",
    "smallest_last",
    "independent_set",
    "connected_sequential_bfs",
    "connected_sequential_dfs",
    "saturation_largest_first",
]

original = nx.algorithms.coloring.greedy_color


def check(label: str, graph, search_small_area: bool) -> None:
    seen: set[frozenset[frozenset[str]]] = set()
    sizes: set[int] = set()
    for strat in STRATEGIES:
        nx.algorithms.coloring.greedy_color = (
            lambda g, *a, _s=strat, **k: original(g, strategy=_s)
        )
        try:
            filled = fill_ports_for_minimal_simulation(graph, search_small_area)
        finally:
            nx.algorithms.coloring.greedy_color = original
        partition = frozenset(frozenset(fg.stabilizers) for fg in filled)
        seen.add(partition)
        sizes.add(len(filled))
    print(f"\n# {label}  (search_small_area={search_small_area})")
    print(f"  distinct #cliques across strategies: {sorted(sizes)}")
    print(f"  distinct PARTITIONS across strategies: {len(seen)}")
    print(
        "  -> "
        + (
            "partition-stable; #952 sort suffices"
            if len(seen) == 1
            else "REPARTITIONS across strategies; sort canNOT fix this"
        )
    )


def main() -> None:
    union = disjoint_union(cnot(), cnot(), dx=100)
    check("two_independent_cnots", union, search_small_area=False)
    check("two_independent_cnots", union, search_small_area=True)


if __name__ == "__main__":
    main()
