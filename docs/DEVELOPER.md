# RecursionLens developer guide

## Architecture

- `_trace.py`: decorator, canonical argument binding, invocation recording, memoization, exception propagation, and recording limits.
- `_model.py`: call-node and DAG data structures plus deterministic tree-to-DAG compression.
- `_report.py`: public report APIs, metrics, comparisons, JSON, and export methods.
- `_render.py`: escaped, self-contained HTML, nested tree markup, and inline SVG DAGs.
- `tests/`: executable acceptance criteria and renderer checks.

The runtime package uses only the Python standard library. IPython is discovered optionally inside `show()` and is not an installation dependency.

## Development loop

1. Read `README.md`, the relevant guide, and the tests; turn the intended change into a testable acceptance criterion.
2. Commit the current working state before a large agent-driven edit.
3. Add or update a focused test.
4. Implement one module at a time.
5. Run `python -m pytest tests -v`; do not commit while tests fail.
6. Review both the diff and generated HTML/JSON, not only test output.
7. Update user documentation and `CHANGELOG.md` when behavior changes.

## Critical invariants

- Function return values and exceptions must pass through unchanged.
- Recursive invocations must use the active recorder; a context variable isolates nested runs.
- Recorder stack and depth must be restored in `finally` blocks.
- Cache hits count as observed calls but not executed function bodies.
- A DAG node represents a canonical bound-argument signature, not merely the source-level function name.
- Rendering must escape all user-controlled strings and must not require external resources.
- Truncation must be visible and must not silently change the wrapped function's result.

## Deliberate limitations

The package is designed for synchronous, deterministic teaching functions. The tracer is not a security sandbox. Side-effecting functions, concurrency, generators, async code, and generalized impure memoization require separate specifications rather than ad hoc patches.

## Agent continuation prompt

> Read README.md, docs/DEVELOPER.md, and the relevant tests. State the acceptance criterion before editing. Implement one focused change, run the complete test suite, inspect a generated report for user-visible regressions, and explain any invariant affected. Do not broaden the supported function domain without updating the documentation and tests.

## Release checks

- Run all tests and coverage.
- Build a wheel and install it in a fresh virtual environment.
- Run `examples/quickstart.py` from the installed wheel.
- Open the demo notebook in the target JupyterLab environment and restart/run all cells.
- Confirm README installation instructions match the actual release channel.
- Confirm the PyPI Homepage points to this GitHub repository when publishing.
