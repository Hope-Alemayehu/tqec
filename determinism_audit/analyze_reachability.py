"""Is a clique-cover *repartition* reachable from a legitimate TQEC computation?

Single gallery examples each have a unique minimum clique cover (Part 3); this
probes two physically-motivated ways a real computation could break that:

  1. Two independent CNOTs in one (disconnected) block graph -> the
     compatibility-complement graph is disconnected -> multiple minimum covers.
  2. A scan of every gallery example's generators for mixed-basis / Y strings
     (a port carrying both X and Z), which could create odd cycles (chromatic
     number >= 3) -- the other way to defeat the sort.

Reuses the brute-force partition enumerator from analyze_clique_cover.py.
Full rationale and results: see FINDINGS.md, Part 3.
"""

from __future__ import annotations

from tqec.computation.block_graph import BlockGraph
from tqec.computation.cube import Port

from determinism_audit.analyze_clique_cover import (
    EXAMPLES,
    generators_for,
    incompatible_edges,
)


def min_partitions(n: int, edges: set[tuple[int, int]]) -> tuple[int, int]:
    """Chromatic number of the complement + number of distinct minimum clique covers.

    Backtracking over partitions into independent sets of the complement graph
    (= clique covers of the compatibility graph). Packs into existing classes
    first so a small cover is found early, then prunes any branch exceeding the
    best found. Canonical by construction (a new class is only ever appended at
    the end, nodes processed in fixed order), so label permutations are not
    double-counted. Scales to a few dozen nodes when the cover is small.
    """
    adj: list[set[int]] = [set() for _ in range(n)]
    for i, j in edges:
        adj[i].add(j)
        adj[j].add(i)

    best = n + 1
    partitions: set[frozenset[frozenset[int]]] = set()

    def backtrack(node: int, classes: list[set[int]]) -> None:
        nonlocal best
        if len(classes) > best:
            return
        if node == n:
            k = len(classes)
            if k < best:
                best = k
                partitions.clear()
            partitions.add(frozenset(frozenset(c) for c in classes))
            return
        for cls in classes:
            if not (adj[node] & cls):
                cls.add(node)
                backtrack(node + 1, classes)
                cls.discard(node)
        classes.append({node})
        backtrack(node + 1, classes)
        classes.pop()

    backtrack(0, [])
    return best, len(partitions)


def generators_for_graph(graph: BlockGraph) -> list[str]:
    """Reconstruct the stabilizer generators for an arbitrary open block graph."""
    surfaces = graph.find_correlation_surfaces()
    stab_to_surface = {s.external_stabilizer_on_graph(graph): s for s in surfaces}
    return list(stab_to_surface.keys())


def disjoint_union(g1: BlockGraph, g2: BlockGraph, dx: int) -> BlockGraph:
    """Place ``g2`` far from ``g1`` and merge both into one disconnected graph."""
    union = BlockGraph()
    g2 = g2.shift_by(dx=dx)
    for cube in g1.cubes:
        union.add_cube(cube.position, cube.kind, cube.label)
    for cube in g2.cubes:
        # Relabel g2's ports so labels stay unique across the two components.
        label = f"{cube.label}_b" if cube.kind == Port() else cube.label
        union.add_cube(cube.position, cube.kind, label)
    for pipe in list(g1.pipes) + list(g2.pipes):
        union.add_pipe(pipe.u.position, pipe.v.position, pipe.kind)
    return union


def report(label: str, generators: list[str]) -> None:
    edges = incompatible_edges(generators)
    n_cliques, n_partitions = min_partitions(len(generators), edges)
    has_y = any("Y" in g for g in generators)
    is_mixed = any(("X" in g and "Z" in g) or "Y" in g for g in generators)
    print(f"\n=== {label} ===")
    print(f"  generators ({len(generators)}): {generators}")
    print(f"  any Y on a port? {has_y}   any mixed-basis generator? {is_mixed}")
    print(f"  incompatible pairs: {len(edges)}   min #cliques: {n_cliques}")
    print(f"  distinct minimum clique-cover PARTITIONS: {n_partitions}")
    print(
        "  verdict:",
        "UNIQUE (sort canonicalizes)"
        if n_partitions == 1
        else "MULTIPLE -> repartition; sort does NOT fix this",
    )


def main() -> None:
    print("# 1) Mixed-basis / Y check across single gallery examples")
    for example in EXAMPLES:
        gens = generators_for(example)
        mixed = any(("X" in g and "Z" in g) or "Y" in g for g in gens)
        print(f"  {example:16s} mixed-basis/Y generator present? {mixed}")

    print("\n\n# 2) Two INDEPENDENT cnots in one block graph (disjoint support)")
    from tqec.gallery.cnot import cnot  # noqa: PLC0415

    union = disjoint_union(cnot(), cnot(), dx=100)
    print(f"  union num_ports = {union.num_ports} (two 4-port cnots)")
    report("two_independent_cnots", generators_for_graph(union))


if __name__ == "__main__":
    main()
