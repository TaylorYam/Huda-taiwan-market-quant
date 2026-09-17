# 0002: 免費 MVP 部署與持久化堆疊

- Status: Accepted
- Date: 2026-09-17

## Context

The project needs daily Taiwan market observations, derived factor results, and a Dashboard while keeping the first usable version at zero recurring cost. The data volume is expected to be small and daily, but the design still needs a durable shared database, idempotent writes, revision lineage, and a path away from local SQLite. The project is not yet asking for production SLA, managed point-in-time recovery, or paid data feeds.

## Decision

1. Use TWSE and TAIFEX official daily interfaces as the initial data sources. Do not purchase a commercial market-data feed for the MVP.
2. Use GitHub Actions as the primary daily scheduler and writer. The workflow must be idempotent, support manual reruns, and keep database credentials in Actions secrets.
3. Use Supabase Free PostgreSQL as the shared persistence target for normalized observations, revisions, factor results, and Market Scores.
4. Use Vercel Hobby for the Dashboard and read-only application endpoints. Vercel Cron may be used as an optional manual or backup trigger, but it is not the authoritative writer because Hobby execution is daily with an imprecise time window and failed invocations are not retried automatically.
5. Keep the existing ignored local SQLite store for development and migration tests. The storage interface remains the seam between collectors/factors and the persistence implementation.
6. Add an explicit manual database export and restore process before enabling unattended daily writes. Free-tier services are a development and MVP boundary, not a backup or availability guarantee.

## Alternatives considered

- **Supabase paid PostgreSQL**: stronger backup and inactivity behavior, but unnecessary recurring cost for the first MVP.
- **Render Free PostgreSQL**: not selected because the free database expires after 30 days and does not provide managed backups.
- **AWS RDS PostgreSQL**: provides more control and operational options, but adds billing and setup overhead before the project's volume and reliability needs justify it.
- **Vercel as the database**: not selected. Vercel hosts the application and connects to an external Postgres provider; its old Vercel Postgres product is no longer available to new projects.
- **Commercial market-data feeds**: deferred until official daily data fails a completeness, stability, or licensing requirement.

## Consequences

The project can deploy a free Dashboard and a shared PostgreSQL-backed MVP without putting the database on a GitHub-hosted runner. The free boundary has material limitations: Supabase Free has a 500 MB database quota, no managed automatic backups or PITR, and may pause low-activity projects; Vercel Hobby Cron is not precise and has no automatic retry. These limitations must be visible in monitoring and documented in the runbook.

The first upgrade triggers are: database usage approaching 500 MB, need for automatic backups or PITR, repeated inactivity pauses, need for more reliable scheduling or retries, or a source-data license requiring stronger access controls. A future ADR should record any paid-provider migration.

## Follow-up

- Implement the PostgreSQL schema adapter behind the existing storage interface.
- Add the Supabase connection configuration using secret names only; never commit a populated `.env` file.
- Add a manual `pg_dump` export and isolated restore check.
- Deploy the Dashboard to Vercel only after the read-only query path works against a seeded database.
- Update [Issue #18](https://github.com/TaylorYam/Huda-taiwan-market-quant/issues/18) with migration, backup, access, quota, and source-term evidence before enabling the unattended daily workflow.

## Provider references

- [Supabase pricing and free-tier limits](https://supabase.com/pricing)
- [Supabase free-project pausing](https://supabase.com/docs/guides/platform/free-project-pausing)
- [Vercel Postgres and Marketplace integrations](https://vercel.com/docs/postgres)
- [Vercel Cron usage and pricing](https://vercel.com/docs/cron-jobs/usage-and-pricing)
- [Render free services and Postgres limits](https://render.com/docs/free)
