# 0001: Phase 1 本機 SQLite 開發預設與正式持久化邊界

- Status: Proposed
- Date: 2026-09-16

## Context

The data contract requires source observations, normalized values, publication and retrieval times, payload hashes, parser versions, quality states, revisions, and derived factor results to remain auditable and reproducible. Phase 1 is currently a low-concurrency local development effort. A GitHub-hosted runner does not preserve its local files between runs, and GitHub Actions artifacts have retention limits, so neither is a permanent historical database. The formal daily scheduler, deployment environment, service owner, retention policy, and source-data permissions are not yet selected.

## Decision

1. Phase 1 local development uses a SQLite database that is excluded from Git.
2. Data access is isolated behind a storage interface so parsers and factor calculation do not depend on SQLite details.
3. SQLite is the single write source for the local Phase 1 workflow. CSV is a reproducible inspection and exchange export; Parquet is not a second write source at this stage.
4. GitHub Actions artifacts may hold short-lived workflow reports or troubleshooting output, but they are not the historical database.
5. The formal daily scheduler's unique persistent source remains undecided. Before enabling a production schedule, a subsequent Accepted ADR must select the service, owner, retention, backup and restore process, credentials, cost controls, and data-permission boundary.

## Contract invariants

This decision preserves [Data Contract v0.1](../data-contract-v0.1.md):

- Use the logical key `dataset_id + observation_date + source_record_key + publication_label/source_revision`.
- Process trading dates in `Asia/Taipei`; use UTC for `retrieved_at` and `ingested_at`.
- Re-running the same payload is idempotent and does not duplicate an observation.
- A source correction appends a new revision with `supersedes_id`; it does not silently overwrite a value.
- Preserve source identity, source date, timestamps, units, payload hash, parser version, and quality status.
- Keep missing or failed observations unavailable; do not substitute zero, 50, or a previous value.
- Preserve raw payloads only within the source's permission boundary; retain a payload hash and audit metadata when raw retention is not allowed.

## Alternatives considered

- **Git repository**: provides review history but is unsuitable for a growing market-data store and may conflict with source redistribution terms.
- **CSV or Parquet as the only source**: useful for exchange and scans, but would require a separate layer for keys, revisions, idempotency, and transactional writes.
- **GitHub Actions artifacts**: useful for short-lived outputs but subject to retention and quota limits.
- **Immediate external database**: fits production sharing, but the provider, cost, permissions, backup, and retention requirements are not yet known.

## Consequences

Phase 1 can implement parsers, quality checks, and data-contract behavior without purchasing a service. The storage interface preserves a migration path to an external database. Local SQLite does not provide durable sharing between scheduled runners and a Dashboard, so the production persistence decision remains a release gate for a formal daily scheduler.

## Follow-up

Issue #9 records this boundary decision. A later ADR must select the formal persistent source before production scheduling, including backup and restore tests, retention, access control, secret rotation, cost limits, and source-data licensing.

## Related documents

- [Data Contract v0.1](../data-contract-v0.1.md)
- [Data Storage Options v0.1](../data-storage-options-v0.1.md)
- [Architecture](../architecture.md)
- [Issue #9](https://github.com/TaylorYam/Huda-taiwan-market-quant/issues/9)
