# DB Schema Baseline (P3)

Scenario outputs are persisted by the camel-oasis-scaffold into SQLite (portable default; Postgres optional).

Expected core tables (from OASIS + our scenarios):
- user / agent profiles
- post, comment
- like, dislike, follow, mute, trace (action log)

For math bridge we extract:
- cascade_series (I(t) per post)
- event_times (for Hawkes)
- engagement_outcomes (for A/B, polarization)

See scaffold src/analysis/db_loader.py for the extraction functions.

Migration strategy: additive columns + view compatibility. Use timestamped .sql migrations under db_migrations/ (future). No auto-migration in P0/P1; explicit PR + contract test on loader when schema changes.

Postgres: optional. When present, same logical schema + constraints/triggers for write-time validation of action attempts (future enhancement per original platform spec).
