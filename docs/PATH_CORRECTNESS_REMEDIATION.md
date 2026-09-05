# Path correctness remediation

## Input boundaries

Path market observations now reuse SelectionEvidence's existing provenance
validator: one non-null consistent source, version, allowed price type and
synthetic flag. A duplicate calendar date is a conflict, even when prices match.
Conflicting or invalid context becomes insufficient, with an explicit limitation;
the canonical source facts are not deduplicated, averaged or rewritten.

Multi-omit checks require nonempty unique Episode-owned execution references,
an included anchor, and the registered horizon. Ordering comes from the canonical
replay frame. Full-phase downstream failure retains the first conflicting fill.
The adverse fixture omits two adds, leaves 400 shares, legally sells 300, then
rejects the next 400-share SELL (`EXE-4`); no quantity is repaired.

## Open endpoint

Open position paths include the existing EpisodeSnapshot's referenced
ReplayPositionState at as-of. Quantity and average cost are copied. Execution
and Decision IDs are null, so this is neither a synthetic execution nor an exit.
Existing execution-based peak-state selection is unchanged.

## Equivalent segment scan

Repeated inclusive date scans use binary-search bounds; repeated anchor-prefix
maxima use the same running maximum. No financial formula, sampling, smoothing
or segmentation threshold changed. Adversarial alternating-price series have
identical complete serialized outputs before and after optimization.

| Observations | Before (seconds) | After (seconds) | Serialized bytes |
| --- | --- | --- | --- |
| 1,000 | 0.0652 | 0.0019 | 443,438 |
| 2,000 | 0.2741 | 0.0038 | 888,437 |
| 4,000 | 1.0300 | 0.0067 | 1,778,437 |

These are local measurements, not timing assertions or a universal SLA.
`tests/test_path_input_boundaries.py` preserves pre-optimization SHA-256 golden
values and actual byte sizes. Together with `tests/test_open_position_endpoint.py`
it covers the reproduced failures, not merely status or source-string presence.
