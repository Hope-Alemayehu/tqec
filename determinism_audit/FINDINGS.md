# PR #952 — Is the `greedy_color` clique-ordering fix a *general* determinism fix?

**Question:** does the #952 sort of the clique cover
make Stim circuit-text generation deterministic across all four ordering
categories in issue #825, or is it only a patch for one specific source?

**Short answer:** Across the audited generation path and the examples/seeds
tested, circuit generation is deterministic in **all four** #825 categories. #952
is the fix for the *one* category that was genuinely order-unstable
(observable/clique ordering); the other three were already pinned by explicit
`sorted()` calls or insertion-ordered traversal. The remaining theoretical gap
(a *repartition* of the clique cover) is **not reachable** by any current gallery
example. So: a general fix for today's gallery, **not** an absolute proof for all
possible inputs.

This was produced on branch `determinism-audit` with the #952 fix applied. No
production code was modified; everything here is analysis + test scripts under
`determinism_audit/`.

---

## Part 1 — Static audit of the four #825 categories

Entry point: `CompiledGraph.generate_stim_circuit`
([src/tqec/compile/graph.py:465](../src/tqec/compile/graph.py#L465)) →
`LayerTree.generate_circuit`
([src/tqec/compile/tree/tree.py:251](../src/tqec/compile/tree/tree.py#L251)).
The final circuit is assembled at
[tree.py:353-356](../src/tqec/compile/tree/tree.py#L353-L356): `QUBIT_COORDS`
first (via `qubit_map.to_circuit()`), then the per-node body.

| # | Category | Where the order is fixed (file:line) | Mechanism | Deterministic? |
|---|----------|--------------------------------------|-----------|----------------|
| 1 | Gate targets | [manipulation.py:134-140](../src/tqec/circuit/schedule/manipulation.py#L134-L140) `_sort_target_groups` (sort by `tuple(t.value ...)`), re-applied at emission [manipulation.py:295](../src/tqec/circuit/schedule/manipulation.py#L295) and in dedup [manipulation.py:195](../src/tqec/circuit/schedule/manipulation.py#L195) | explicit `sorted()` | **Yes** |
| 2a | Detector record targets | [annotations.py:46](../src/tqec/compile/tree/annotations.py#L46) `sorted([...])`; also [detector.py:73](../src/tqec/compile/detectors/detector.py#L73) `measurement_records.sort(...)` | explicit `sorted()` | **Yes** |
| 2b | Observable record targets | [builder.py:54](../src/tqec/compile/observables/builder.py#L54) `sorted(self.measurement_offsets)` | explicit `sorted()` | **Yes** |
| 2c | Order of the DETECTOR list itself | [compute.py:802](../src/tqec/compile/detectors/compute.py#L802) `list(set(detectors))`, fed by iterating `frozenset[Detector]` at [compute.py:798](../src/tqec/compile/detectors/compute.py#L798) | `set`/`frozenset` of `Detector` — **but** `Detector.__hash__` ([detector.py:28](../src/tqec/compile/detectors/detector.py#L28)) → `frozenset[Measurement]` → `Measurement` (`hash((GridQubit, int))`) → `GridQubit.__hash__` = `hash((int,int))` ([qubit.py:62-63](../src/tqec/circuit/qubit.py#L62-L63)). All-integer hashes, which CPython does **not** randomize. | **Yes** (int-hash safe; *seed-independent*) — see caveat |
| 3a | Qubit index assignment | [manipulation.py:343](../src/tqec/circuit/schedule/manipulation.py#L343) `QubitMap.from_qubits(sorted(needed_qubits))` (`GridQubit.__lt__` at [qubit.py:68](../src/tqec/circuit/qubit.py#L68)) | explicit `sorted()` | **Yes** |
| 3b | QUBIT_COORDS emission order | [qubit_map.py:160](../src/tqec/circuit/qubit_map.py#L160) `sorted(self.i2q.items(), key=lambda t: t[0])` | explicit `sorted()` by int index | **Yes** |
| 4 | Relative order of QUBIT_COORDS / DETECTOR / OBSERVABLE_INCLUDE | QUBIT_COORDS first [tree.py:354-356](../src/tqec/compile/tree/tree.py#L354-L356); then per leaf `detectors + observables` [node.py:179](../src/tqec/compile/tree/node.py#L179); observable index from `enumerate(self._abstract_observables)` [tree.py:110](../src/tqec/compile/tree/tree.py#L110) | insertion-ordered list traversal / concatenation | **Yes** (given 2c) |

**Where #952 fits.** None of the four categories above is the clique/observable
*ordering* that #952 fixed. #952 acts **upstream** of this path, in
`fill_ports_for_minimal_simulation`
([src/tqec/computation/open_graph.py:139](../src/tqec/computation/open_graph.py#L139)):
it sorts the clique cover so the *set of filled graphs* and the
*observable-index assignment* fed into generation are stable. The four
in-circuit categories were already deterministic; #952 closed the one remaining
upstream source (where `greedy_color`'s color labels otherwise leaked into
`OBSERVABLE_INCLUDE` indices, and hence into `str(circuit)` / the sinter
`strong_id`).

**One caveat worth flagging (category 2c).** The detector *list* order is the
only place output order is decided by iterating a `set`/`frozenset` of complex
objects rather than an explicit `sorted()`. It is deterministic **today** purely
because every contributing hash bottoms out in `int`s (and CPython never
randomizes `int`/`tuple`/`frozenset`-of-`int` hashes, regardless of
`PYTHONHASHSEED`). It is *not* protected by an explicit sort. If a `str` ever
enters `Detector`/`Measurement`/`GridQubit` hashing, this line would silently
become seed-dependent. A defensive `sorted(...)` here (by coordinates +
measurement offsets) would make the guarantee explicit rather than incidental.

---

## Part 2 — Empirical proof (byte-identical circuit text)

Worker: [`generate_circuit.py`](generate_circuit.py) builds every filled graph of
an example (in the #952-canonicalized order), generates the Stim circuit, and
prints a SHA-256 of the concatenated circuit text. Test:
[`test_determinism.py`](test_determinism.py) asserts the SHA is identical across
3 in-process regenerations and across fresh subprocesses with
`PYTHONHASHSEED ∈ {0, 1, 2, 42}` (the seed must be set before interpreter start,
hence subprocesses). Detector computation costs ~20× the rest, so it is split
into two tiers.

**Tier A — detector-free (`manhattan_radius=-1`), ALL examples, k ∈ {1, 2}.**
Exercises gate targets, qubit coords/indices, observable record targets and
instruction ordering (categories 1, 2b, 3, 4).

```
$ .venv/Scripts/python.exe -m pytest determinism_audit/test_determinism.py -v
================ 16 passed, 4 deselected in 655.57s (0:10:55) =================
```

All 16 cells (4 examples × k∈{1,2} × {in-process ×3, seeds 0/1/2/42}) passed —
see [`RESULTS_fast_tier.txt`](RESULTS_fast_tier.txt).

**Tier B — FULL circuit incl. `DETECTOR` (`manhattan_radius=2`), representative
subset {cnot, move_rotation}, k ∈ {1, 2}.** Adds categories 2a and 2c (the
detector list + detector record targets — the only `set`-ordered category).

```
$ .venv/Scripts/python.exe -m pytest determinism_audit/test_determinism.py -v -m slow
================ 4 passed, 16 deselected in 2487.44s (0:41:27) ================
```

All 4 cells ({cnot, move_rotation} × k∈{1,2} × seeds 0/1/2/42, full circuit incl.
`DETECTOR`) passed — see [`RESULTS_full_tier.txt`](RESULTS_full_tier.txt).
Full-detector generation is ~55–105 s per example at k=1; the subset keeps the
deep proof tractable. The static audit already shows the detector path is
seed-independent for *all* examples — Tier B confirms it end-to-end on
representatives. The remaining full-detector cells run with the same command;
they are slower, not different in kind.

**Conclusion (Part 2):** for every case tested, the full circuit text — and hence
all four #825 categories that appear in it — is byte-identical across
regenerations and across hash seeds. This is empirical determinism *across the
examples and seeds tested*, not an absolute proof for all inputs.

---

## Part 3 — Stressing the boundary: can the clique cover *repartition*?

The sort in #952 canonicalizes a **reordering** of a fixed partition. It cannot
canonicalize a **repartition** — if the Pauli-compatibility graph admits two
genuinely different *minimum* clique covers, `greedy_color` could pick either and
sorting would not hide the difference.

Script: [`analyze_clique_cover.py`](analyze_clique_cover.py) reconstructs the
exact compatibility graph that `fill_ports_for_minimal_simulation` builds, then
brute-force enumerates **all** distinct minimum clique-cover partitions.
Raw output: [`RESULTS_part3_clique_cover.txt`](RESULTS_part3_clique_cover.txt).

Result for every open-port gallery example:

| Example | #generators | min #cliques | distinct minimum partitions | verdict |
|---------|-------------|--------------|------------------------------|---------|
| cnot | 4 | 2 | **1** | unique → sort canonicalizes |
| three_cnots | 6 | 2 | **1** | unique → sort canonicalizes |
| move_rotation | 2 | 2 | **1** | unique → sort canonicalizes |
| steane_encoding | 7 | 2 | **1** | unique → sort canonicalizes |
| cz | 4 | 2 | **1** | unique → sort canonicalizes |

Every example reduces to a **unique** 2-clique cover (X-type vs Z-type
stabilizers form a connected bipartite incompatibility graph, whose 2-partition
is unique). With a unique partition, `greedy_color`'s only freedom is the *label*
of each clique — exactly what the #952 sort removes. So #952 is **complete** for
all current gallery examples.

**Is a repartition reachable today?** Not through the curated *single* gallery
examples — but **yes** through a legitimate (non-synthetic) computation, without
any new code family. A repartition needs a generator set whose
incompatibility-complement graph admits multiple minimum clique covers — e.g.
chromatic number ≥ 3 with multiple optimal colorings, or a *disconnected*
complement whose components can be independently assigned. Two facts make this
physically reachable in surface codes alone:

- **Disconnected block graphs are fully supported.** The correlation-surface
  finder explicitly partitions the ZX graph into connected components and returns
  the *product* of each component's surfaces
  ([_correlation.py:344-357](../src/tqec/computation/_correlation.py#L344-L357)).
  `validate()` checks only *local* cube conditions
  ([block_graph.py:336-356](../src/tqec/computation/block_graph.py#L336-L356)) and
  `compile` only requires "no open ports"
  ([compile.py:100-108](../src/tqec/compile/compile.py#L100-L108)) —
  `is_single_connected()` exists but is **never enforced**. So a block graph that
  factors into independent sub-computations (e.g. two operations run in parallel
  in one simulation) is a valid input.
- **The `search_small_area_observables=True` option strips the locking terms.**
  The default path keeps *all* correlation surfaces, whose cross-product terms
  re-link disconnected components and pin a unique cover. The reduced path
  ([open_graph.py:104-117](../src/tqec/computation/open_graph.py#L104-L117)) keeps
  a minimal generating set, removing exactly those locking terms.

Concrete witness — **two independent CNOTs in one block graph** (`disjoint_union`
in [`analyze_reachability.py`](analyze_reachability.py)), run through the
*production* `fill_ports_for_minimal_simulation` across all six networkx coloring
strategies ([`analyze_reduced_path.py`](analyze_reduced_path.py),
[`RESULTS_reduced_path.txt`](RESULTS_reduced_path.txt)):

```
two_independent_cnots  (search_small_area=False)  -> partitions: 1   (#952 sort suffices)
two_independent_cnots  (search_small_area=True)   -> partitions: 3, #cliques in {3,4}
                                                     -> REPARTITIONS; sort canNOT fix this
```

The default path stays partition-stable even when disconnected (the full product
surfaces re-link the components — which is also why the synthetic 4-generator
case `['XXII','ZZII','IIXX','IIZZ']` *overstates* the risk: it omits those
cross-terms). But the reduced path produces **3 distinct partitions** and even a
different *number* of cliques (3 vs 4), which output sorting cannot hide. Note the
reduced path is reachable only via the module-level function — the convenience
method `BlockGraph.fill_ports_for_minimal_simulation()` hardcodes `False`
([block_graph.py:591](../src/tqec/computation/block_graph.py#L591)).

**Classification.** Not "will never happen given the physics," and *not* gated on
color/Floquet codes (TQEC supports neither — it is a surface-code lattice-surgery
/ ZX compiler). The reachable trigger is **a multi-component computation +
`search_small_area_observables=True`**. The everyday path (single connected
computation, or the default `search_small_area=False`) is genuinely safe and
#952 fully fixes it there. Closing the remaining corner needs a canonical
*partition* choice or a fixed deterministic coloring strategy, not just output
sorting.

The original synthetic demonstration (still in
[`analyze_clique_cover.py`](analyze_clique_cover.py)) shows the bare mechanism —
two disjoint X/Z pairs → **2** distinct minimum covers:

```
synthetic_disconnected_repartition  generators ['XXII','ZZII','IIXX','IIZZ']
  distinct minimum clique-cover PARTITIONS: 2
  verdict: MULTIPLE -> genuine repartition; sort fix does NOT make this deterministic
```

---

## Bottom line

- **#952 is the correct and sufficient fix for the determinism bug it targets.**
  It removes the one genuine source of order instability — the `greedy_color`
  color labels leaking into the observable/clique ordering — and circuit
  generation is then deterministic across all four #825 categories for every
  gallery example, verified both statically and empirically (seeds 0/1/2/42,
  k=1,2).
- **It is a general fix for the current gallery, not an absolute one.** Two
  things keep that honest: (1) category 2c (detector list order) is deterministic
  by relying on int-only hashing, not an explicit sort — robust today, but worth
  a defensive `sorted()` to make it future-proof; (2) a *repartition* of the
  clique cover would defeat the sort, and — unlike originally thought — this is
  reachable by a legitimate computation, not just a synthetic one: a
  multi-component block graph (e.g. two independent CNOTs in one simulation) run
  with `search_small_area_observables=True` produces 3 distinct partitions across
  coloring strategies (see Part 3). It is *not* gated on color/Floquet codes
  (TQEC supports neither). The default path (`search_small_area=False`) stays
  partition-stable even when disconnected, so #952 is complete there.
- **Suggested follow-ups (optional):** add an explicit `sorted()` at
  [compute.py:802](../src/tqec/compile/detectors/compute.py#L802), and keep the
  cross-`PYTHONHASHSEED` test (Tier A is fast enough for CI) as a regression
  guard.

---

## Reproducing

All commands run from the repo root on branch `determinism-audit` (with the #952
fix applied), using the project venv.

```bash
# Part 1 — citations are static; see the file:line links in the table above.

# Part 2 (Tier A) — detector-free, all examples, k=1,2, across hash seeds:
.venv/Scripts/python.exe -m pytest determinism_audit/test_determinism.py -v
#   -> 16 passed, 4 deselected   (RESULTS_fast_tier.txt)

# Part 2 (Tier B) — FULL circuit incl. detectors, {cnot, move_rotation}, k=1,2:
.venv/Scripts/python.exe -m pytest determinism_audit/test_determinism.py -v -m slow
#   -> 4 passed, 16 deselected   (RESULTS_full_tier.txt)

# Generate a single circuit SHA by hand (used by the cross-seed subprocess test):
PYTHONHASHSEED=0  .venv/Scripts/python.exe -m determinism_audit.generate_circuit --example cnot --k 1 --mr 2
PYTHONHASHSEED=42 .venv/Scripts/python.exe -m determinism_audit.generate_circuit --example cnot --k 1 --mr 2
#   (the two SHAs must match)

# Part 3 — clique-cover partition uniqueness + synthetic boundary case:
.venv/Scripts/python.exe -m determinism_audit.analyze_clique_cover
#   -> RESULTS_part3_clique_cover.txt

# Part 3 (reachability) — two independent CNOTs; reduced path repartitions:
.venv/Scripts/python.exe -m determinism_audit.analyze_reachability
#   -> RESULTS_reachability.txt
.venv/Scripts/python.exe -m determinism_audit.analyze_reduced_path
#   -> RESULTS_reduced_path.txt  (search_small_area=True -> 3 partitions, #cliques {3,4})
```

### Files

| File | Purpose |
|------|---------|
| [`generate_circuit.py`](generate_circuit.py) | Worker: example → full circuit → SHA-256 (importable + CLI) |
| [`test_determinism.py`](test_determinism.py) | Pytest: in-process + cross-`PYTHONHASHSEED` equality, two tiers |
| [`analyze_clique_cover.py`](analyze_clique_cover.py) | Part 3: enumerate all minimum clique-cover partitions |
| [`analyze_reachability.py`](analyze_reachability.py) | Part 3 reachability: two-independent-CNOTs construction + mixed-basis/Y scan |
| [`analyze_reduced_path.py`](analyze_reduced_path.py) | Part 3 reachability: reduced path (`search_small_area=True`) repartitions across coloring strategies |
| [`RESULTS_fast_tier.txt`](RESULTS_fast_tier.txt) | Tier A output (16 passed) |
| [`RESULTS_full_tier.txt`](RESULTS_full_tier.txt) | Tier B output (4 passed, full detectors) |
| [`RESULTS_part3_clique_cover.txt`](RESULTS_part3_clique_cover.txt) | Part 3 output |
| [`RESULTS_reachability.txt`](RESULTS_reachability.txt), [`RESULTS_reduced_path.txt`](RESULTS_reduced_path.txt) | Part 3 reachability output |

> Note: `multiprocessing` detector computation uses Windows `spawn`, which
> re-imports the entry module — the worker's `if __name__ == "__main__"` guard is
> required, and each subprocess pays a tqec-import startup cost.
