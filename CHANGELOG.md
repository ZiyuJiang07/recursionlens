# Changelog

## 0.1.1 — 2026-11-12

### Added

- `report.show(mode="expanded")` renders every recorded invocation as one compact SVG tree, with no nodes collapsed.
- Repeated calls are underlined coral, cache hits are green, and errors are red.
- Expanded mode is capped at 120 visible calls with an explicit omission notice.

## 0.1.0 — 2026-11-12

### Added

- `@trace` decorator with normal-call passthrough and `function.last_report`.
- Explicit naive and memoized runs with canonical bound-argument signatures.
- Call trees with return values, errors, repeated-call badges, and cache-hit badges.
- Compressed subproblem DAGs with call, execution, cache, and dependency data.
- Quantitative two-run comparison reports.
- JupyterLab HTML display, self-contained HTML export, and versioned JSON export.
- Recording limits, unhashable-argument warnings, and HTML escaping.
- Pytest suite, demo notebook, user/developer documentation, and CI.

### Hardened after review

- Memoization keys include argument types, distinguishing `1` from `1.0`.
- Run options no longer consume user function arguments with reserved names.
- Internal subproblem identities are untruncated and unique per decorated function.
- DAG edges are laid out and drawn from parent to child without overlapping nodes.
- Exception formatting cannot replace the original exception.
- Comparisons use returned values, and failed reports are labelled as raised errors.
