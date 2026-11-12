# RecursionLens 0.1 specification

## Purpose

RecursionLens turns a Python recursive function call into a JupyterLab-friendly report that explains repeated work through a call tree, a compressed subproblem DAG, and a naive-versus-memoized comparison.

## Users and stories

- As a student, I want to see which recursive calls repeat so that I can understand why naive recursion can be expensive.
- As a teacher, I want to compare naive and memoized execution without installing Graphviz so that a demo works in a fresh JupyterLab environment.
- As a package user, I want machine-readable traces so that I can test and export execution evidence.

## Inputs

- A synchronous Python function decorated with `@trace`.
- Positional or keyword arguments accepted by that function.
- Optional `memoize` and `max_calls` settings for `function.with_options(...).run(...)`.

The supported teaching domain is deterministic, synchronous recursive functions. Memoization additionally requires hashable bound arguments. Functions with external side effects are outside the correctness guarantee.

## Outputs

- Normal function calls preserve the original return value or exception and expose `function.last_report`.
- `function.run(...)` returns a `TraceReport` containing the returned value, call nodes, metrics, warnings, and truncation state.
- A report exports a nested call tree, a subproblem DAG, JSON, and self-contained HTML.
- Two reports produce a quantitative `ComparisonReport` with side-by-side DAGs.

## Acceptance criteria

1. Naive `fib(5)` records 15 calls, 6 unique subproblems, 9 repeated calls, and maximum depth 5.
2. Memoized `fib(5)` records 6 executed calls and 3 cache hits; it returns the same value as naive execution.
3. Naive `fib(4)` records 9 calls and 5 unique subproblems; its DAG has 6 directed dependency edges.
4. `factorial(4)` records 4 calls and no repeated subproblems.
5. Positional and keyword forms of the same bound arguments have the same subproblem signature.
6. Exceptions are recorded and re-raised; the recorder is usable again afterwards.
7. Recording stops adding nodes after `max_calls` without changing the function's return value, and the report is marked truncated.
8. Reports display through `_repr_html_` in JupyterLab and contain no runtime dependency on Graphviz, external JavaScript, or a CDN.
9. HTML output escapes source values and includes tree, DAG, metrics, and comparison views.
10. JSON export contains nodes, DAG edges, metrics, and metadata with stable primitive types.
11. Expanded mode renders every recorded call in one SVG tree with no collapsed nodes; a visible omission notice appears above 120 calls.

## Non-goals for 0.1

- Arbitrary sandboxing or execution of untrusted code.
- Async functions, generators, threads, or distributed execution.
- Automatic Big-O inference or automatic code rewriting.
- A JupyterLab extension, hosted web application, or Graphviz renderer.
- Guaranteed semantic memoization for impure functions or unhashable arguments.

## Test plan

Use pytest for numeric trace invariants, cache behavior, signatures, exceptions, truncation, serialization, escaping, and HTML views. Run an editable install and a built-wheel install in clean virtual environments. Execute the demo notebook's core examples in a fresh Python process and inspect generated HTML artifacts.
