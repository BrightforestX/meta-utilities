# Formal validation — Midspiral + Quint

## Midspiral

Business rules live under `formal/midspiral/*.yaml` and are checked with `scripts/verify_midspiral_rules.sh` (asserts `id`, `surrealql_assertion`, `midspiral` keys).

## Quint.sh

Executable specs live under `formal/quint/*.qnt`. Validate with:

```bash
quint typecheck formal/quint/counter.qnt
# or
npx @informalsystems/quint typecheck formal/quint/mutex.qnt
```

## Batch contract

SDLC batch jobs set `validation.validation_cmd` as the source of truth (exit 0 required).
