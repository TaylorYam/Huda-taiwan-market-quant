# Production Persistence Decision v0.1

- Status: MVP stack selected; production hardening pending
- Date: 2026-09-17
- Tracking: [Issue #18](https://github.com/TaylorYam/Huda-taiwan-market-quant/issues/18)
- Boundary: daily-level observations and derived results; this records a free-tier MVP choice and does not activate or purchase any service.

## Decision scope

The production scheduler must write observations and derived results to one durable source that a later Dashboard can read. The source must preserve the Phase 1 observation identity, source payload hash, parser version, quality status, and revision lineage. A runner-local file or a short-lived workflow artifact is not a production source.

The Phase 1 local SQLite decision is already accepted in [ADR 0001](adr/0001-phase-1-storage-boundary.md). The free-tier MVP deployment choice is recorded in [ADR 0002](adr/0002-free-tier-mvp-stack.md); it does not replace the local boundary or claim production SLA.

## Selected free-tier MVP stack

| Layer | Selected service | Responsibility | Free-tier boundary |
|---|---|---|---|
| Source data | TWSE and TAIFEX official daily APIs | Collect the daily observations needed by the v0.1 factors | Respect each source's access, retention, and redistribution terms |
| Scheduler and writer | GitHub Actions | Run the daily Python collector, quality checks, idempotent writes, and manual reruns | Subject to repository/account Actions quotas; credentials stay in Actions secrets |
| Persistent database | Supabase Free PostgreSQL | Store normalized observations, revisions, factor results, and market scores | 500 MB database quota; no managed automatic backups or PITR; low-activity projects may pause |
| Dashboard and read API | Vercel Hobby | Serve the dashboard and read-only application endpoints | Hobby Cron is optional, daily only, and may run within the configured hour; it is not the primary writer |

SQLite remains the local development store. The storage interface must allow a SQLite export to be migrated into PostgreSQL without losing logical keys, payload hashes, parser versions, quality states, or revision lineage.

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

The selected MVP uses managed PostgreSQL through Supabase Free. Render Free is not selected because its free database expires after 30 days and has no managed backups. Paid Supabase, Render, AWS RDS, or another PostgreSQL provider remain upgrade paths if the free-tier boundaries are reached.

## Evidence still required

- Measure the real observation and derived-result volume after the daily collectors are available; do not size from guesses.
- Run a SQLite-to-candidate migration dry run and compare row counts, logical identities, hashes, and revision chains.
- Add a manual `pg_dump` export workflow and execute a restore drill into an isolated environment; record recovery time and the latest recoverable observation date.
- Verify Actions-to-database and Dashboard-to-database permissions separately, including secret rotation.
- Define retention for normalized observations, derived results, and any raw payloads independently.
- Record the free-tier quota assumptions and a clear upgrade trigger before enabling the daily workflow.
- Confirm the source terms allow the planned retention, internal Dashboard access, and backup copies.

## Accepted ADR gate

Issue #18's provider selection is complete through [ADR 0002](adr/0002-free-tier-mvp-stack.md). The daily production workflow remains gated on the migration dry run, manual backup and restore drill, access separation, quota monitoring, and source-license check. Until those checks pass, the repository may continue local SQLite development and data collection but must not treat runner-local storage as the production source.
