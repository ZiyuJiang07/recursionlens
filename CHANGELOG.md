# Changelog

All notable changes to RecursionLens are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- Growth has an editor-side entry and stays available after code edits or a
  failed main input call. Stale trace views stay disabled until a new trace
  completes successfully.
- Growth expands positional and keyword arguments using Python call semantics
  and bypasses cached helper functions when measuring the uncached baseline.
- Growth now measures the current editor code using an editable input call
  template, range, and step. It refreshes results when the source or range
  changes and fits both execution curves independently.

### Added
- `fit_growth()` and `GrowthFit`: dependency-free Big-O estimation from
  measured execution counts, covering constant, logarithmic, linear,
  linearithmic, quadratic, and exponential shapes with R² scores and warnings
  for weak evidence.
- Growth playground panel now displays the estimated complexity for the
  code being measured.

### Changed
- `fit_growth()` reports near-constant samples as `O(1)` instead of letting a
  sloped model win by fitting measurement noise.
- `CONTRIBUTING.md` with development setup, coding conventions, and PR checklist.
- `CHANGELOG.md` to track project history.
- Module-level docstrings for `_model.py`, `_render.py`, `_report.py`,
  `_doctor.py`, and `_trace.py` describing each module's role and boundaries.
- Comprehensive docstrings for public and internal helper functions across
  all modules.
- Unit tests for `build_dag` (deterministic ordering, cycle safety),
  `safe_repr` / `full_repr` (exception safety), `cache_key_for` (type
  sensitivity), `compact_call` / `short` (truncation), `dag_depths`
  (depth computation), `TutorTrace.step` (index clamping), and
  `ComparisonReport.to_dict` (delta correctness).
- Tests for `TraceReport` properties when constructed without runtime counts
  (fallback to node-based computation).

### Changed
- `TraceReport.dag_nodes` and `TraceReport.dag_edges` now cache the `build_dag`
  result instead of recomputing it on every access.
- `_render.py` CSS string verified complete — the `_CSS` constant contains
  all rules including `.rl-note` and `.rl-expanded`.
- `_doctor.py` `diagnose` function signature annotated with explicit return
  type `list[Finding]` (was already the case at runtime; now documented).

### Fixed
- `_tutor.py`: `Tuple` was used in a type annotation on line 194 but not
  imported from `typing`. It worked at runtime because
  `from __future__ import annotations` makes annotations strings, but
  `get_type_hints()` would have failed. Added the missing import.

## [0.2.0] - 2026-01-15

### Added
- Python Tutor-style interactive stepper (`tutor()` and `record_tutor()`).
- Recursion Doctor: automatic pattern detection for repeated subproblems,
  active-path reentry, failed calls, and partial traces.
- Browser playground with step-through, expanded tree, DAG, comparison,
  growth charts, and cache-savings prediction.
- Memoization support with type-aware cache keys.
- Subproblem DAG compression from the call tree.
- Self-contained HTML/SVG rendering (no Graphviz, no external JS).
- JSON export with schema version 1.
- Bilingual documentation (English and Simplified Chinese).
- Growth measurement across input sizes with CSV download.
- `max_calls` truncation with preserved run-wide totals.
