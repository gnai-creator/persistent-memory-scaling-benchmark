# Graph reification vs. learned memory state

> **Graph reification turns memories into explicit addressable facts. ASM-CM
> turns experience into an evolving learned state.**

This distinction frames the benchmark and must appear before its results.

## Graph reification

In graph reification, a relationship or assertion becomes an identifiable object
that can itself carry metadata. A direct graph statement such as:

```text
Alice -- works_at --> Acme
```

can be represented conceptually as:

```text
Statement_847
├── subject     → Alice
├── predicate   → works_at
├── object      → Acme
├── since       → 2024
├── source      → contract_17
├── confidence  → 0.97
├── observed_at → 2026-08-01
└── valid_until → ...
```

The assertion is now addressable. Provenance, time, confidence, authorization,
versions, and contradictions can be attached to it explicitly. In a graph-based
memory architecture, history therefore remains represented as graph objects and
relationships that storage and indexes must preserve.

## ASM-CM memory state

ASM-CM does not require an explicit graph node corresponding to every remembered
assertion inside its associative state. Experience updates a learned neural state:

```text
"Felipe likes coffee"
          ↓
    neural update
          ↓
 associative state
          ↓
 ████████████████
```

Exact payloads and provenance may still be kept externally when required, but the
active associative mechanism is represented as compact learned state rather than a
growing set of explicit fact nodes.

## What the benchmark tests

Neither representation is automatically superior. Reification is valuable for
auditability, explicit provenance, and structured inspection. A compact learned
state can be valuable for bounded active memory, efficiency, and associative
continuity.

The scaling hypothesis follows directly from the representations:

- explicit facts, relationships, metadata, and their indexes accumulate as
  represented knowledge grows;
- ASM-CM is designed to compress successive associations into bounded neural
  state, while optional canonical payload storage may still grow on disk.

The benchmark measures the operational price of these choices: resident RAM,
persistent storage, active-state size, ingestion cost, retrieval latency, reader
context, and retrieval quality under controlled workloads.

## Interpreting the comparison as a Pareto frontier

The benchmark is not a count of how many columns each system wins. Graph
reification may plausibly outperform a compressed associative state in pure
retrieval or answer quality, particularly when questions map cleanly to explicit
entities and relationships. Compression may trade some fidelity for a substantially
smaller active representation.

Three outcomes were defined before completing the paired run:

1. **TrustGraph wins retrieval or answer quality.** The relevant question becomes
   how much RAM, persistent storage, ingestion work, context, and operational
   complexity purchase that advantage.
2. **The systems are approximately tied in quality.** A materially smaller active
   representation would then favor ASM-CM on resource efficiency.
3. **ASM-CM also wins retrieval.** This would indicate that associative compression
   preserved both efficiency and retrieval effectiveness under this protocol.

A result unfavorable to ASM-CM would require considering the joint outcome, not a
single metric: substantially better retrieval and answer quality, less reader
context, lower latency, and a comparable or smaller footprint from TrustGraph.

The intended interpretation is therefore:

> **TrustGraph optimizes explicitness and retrieval fidelity. ASM-CM optimizes
> associative compression and resource efficiency. The benchmark measures the
> resulting Pareto trade-off.**
