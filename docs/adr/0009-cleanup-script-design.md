# ADR-0009: Cleanup Script Design

## Status
Accepted

## Context
The Cleanup process (defined in CONTEXT.md) needs a concrete implementation. Key design decisions were required around consensus threshold, conflict handling, annotation handling, safety checks, and execution mode.

## Decisions

**Consensus threshold — 1 vote sufficient.**
Duplicate pairs are detected by identical checksum (byte-for-byte copies). A single confident vote is sufficient justification for deletion. Requiring multiple annotators would leave most auto-assigned clusters (single voter) permanently uncleanable.

**Conflicting votes — skip the cluster.**
When two or more users disagree on which image is the original, the cluster is skipped and reported. The cost of a wrong deletion is permanent and unrecoverable; the cost of skipping is a manual follow-up.

**Annotations on redundant images — delete without migrating.**
Redundant images are exact byte-for-byte copies of their original. Any annotation work (ratings, bboxes) can be redone on the original. Migration adds complexity for negligible benefit given the duplication.

**Safety check — verify original file exists on disk before deleting.**
If the original file is not accessible (network share unmounted, file moved), the cluster is skipped. This prevents deleting the only remaining copy of an image due to transient infrastructure issues.

**Execution mode — dry run by default, `--execute` to commit.**
Standard practice for irreversible bulk operations. The dry run reports exactly what would be deleted, enabling review before commitment.

## Consequences
- `scripts/cleanup.py` is the canonical implementation.
- Conflicted clusters accumulate over time and require manual resolution before they can be cleaned.
- Annotations on redundant images are permanently lost on cleanup — this is accepted.
- Running cleanup multiple times is safe (already-deleted images simply aren't found on disk or in DB).
