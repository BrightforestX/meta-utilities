# CI Quality Gates (P7)

Gate 1 (pre-merge fast): lint, static, unit, contract tests + pre-run agent yaml validation.
Gate 2 (PR): integration + BDD (@p0 @acceptance) + deterministic config gen snapshots.
Gate 3 (nightly): replay/soak + negative invalid-yaml tests; flaky replay must be quarantined with owner+due date.

Every phase milestone requires:
- linked failing tests before impl
- passing G/W/T scenarios for the ACs
- coverage/contract evidence in PR

This is enforced by the tests in this package + the plan.
