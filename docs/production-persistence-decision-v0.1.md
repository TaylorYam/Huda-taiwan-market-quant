# Production Persistence Decision v0.1

- Status: decision preparation
- Date: 2026-09-17
- Tracking: [Issue #18](https://github.com/TaylorYam/Huda-taiwan-market-quant/issues/18)
- Boundary: daily-level observations and derived results; no purchase or service activation is authorized by this document.

## Decision scope

The production scheduler must write observations and derived results to one durable source that a later Dashboard can read. The source must preserve the Phase 1 observation identity, source payload hash, parser version, quality status, and revision lineage. A runner-local file or a short-lived workflow artifact is not a production source.

The Phase 1 local SQLite decision is already accepted in [ADR 0001](adr/0001-phase-1-storage-boundary.md). This document prepares the separate decision for production persistence; it does not replace that local boundary.

## Non-negotiable requirements

1. **Durability:** data survives a new GitHub-hosted runner and an application restart.
2. **Transactional writes:** duplicate daily inputs remain idempotent, while corrected inputs append a revision linked by `supersedes_id`.
3. **Recoverability:** backups have a defined schedule, retention, owner, and restore test.
4. **Controlled access:** Actions can write with least privilege; the Dashboard can read without write credentials; secrets can be rotated.
5. **Auditability:** observations remain traceable to source URL, source date, retrieval time, payload hash, parser version, and quality state.
6. **Migration:** the schema and data can be loaded from the Phase 1 SQLite export without losing logical identity or lineage.
7. **Policy fit:** retention and raw-payload storage respect the source's terms and the repository's data handling boundary.
8. **Cost control:** expected monthly cost and an alert or hard limit are documented before activation.

## Candidate classes

| Candidate class | Fit for the production write source | What must be proven before selection |
|---|---|---|
| Managed PostgreSQL | Strong fit for transactional observations, revisions, factor results, and Dashboard reads | Provider, region, backups, restore drill, connection security, cost ceiling, and migration tooling |
| Object storage plus query layer | Strong for immutable raw payloads and partitioned exports; weaker as the only transactional write source | Atomic revision/index strategy, concurrent-read behavior, query latency, restore path, and access policy |
| Persistent single-host SQLite | Possible for one writer and a colocated Dashboard; weak for runner replacement and shared access | Host durability, encrypted backups, failover/recovery, network access, and operational ownership |
| GitHub artifacts or repository commits | Not suitable as the historical database | No further evaluation; retention, write semantics, and source redistribution constraints fail the production boundary |

These are candidate classes rather than vendor recommendations. Provider pricing, account limits, data residency, and licensing remain unknown until a specific service is proposed.

## Evidence still required

- Measure the real observation and derived-result volume after the daily collectors are available; do not size from guesses.
- Run a SQLite-to-candidate migration dry run and compare row counts, logical identities, hashes, and revision chains.
- Execute a restore drill into an isolated environment and record recovery time and the latest recoverable observation date.
- Verify Actions-to-database and Dashboard-to-database permissions separately, including secret rotation.
- Define retention for normalized observations, derived results, and any raw payloads independently.
- Record monthly cost assumptions and an alert or hard limit.
- Confirm the source terms allow the planned retention, internal Dashboard access, and backup copies.

## Accepted ADR gate

Issue #18 is complete only when a follow-up ADR names the selected class and provider, owner, region, retention, backup and restore process, access roles, secret handling, migration path, cost controls, and licensing boundary. Until then, the repository may continue local SQLite development and data collection, but it must not enable a production daily scheduler that relies on runner-local storage.
