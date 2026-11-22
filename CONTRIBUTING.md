# Contributing to RecursionLens

Thank you for your interest in improving RecursionLens! This guide covers the
development workflow, coding conventions, and release process.

## Development setup

RecursionLens targets Python 3.9+ and has zero runtime dependencies. The only
extra you need for development is the `dev` optional dependency group, which
pulls in pytest, coverage, and ipywidgets.

```bash
git clone https://github.com/ZiyuJiang07/recursionlens.git
cd recursionlens
python -m pip install -e ".[dev]"
```

Verify the installation:

```bash
python -m pytest tests -v
python examples/quickstart.py
```

All 63+ tests should pass in under a second.

## Project structure

```
recursionlens/
├── src/recursionlens/
│   ├── __init__.py       Public API exports
│   ├── _complexity.py    Growth-model fitting and Big-O estimates
│   ├── _trace.py         Decorator, recorder, and run configuration
│   ├── _model.py         CallNode, DAGNode, and build_dag()
│   ├── _render.py        HTML/SVG rendering for all views
│   ├── _report.py        TraceReport and ComparisonReport
│   ├── _doctor.py        Pattern diagnosis (Recursion Doctor)
│   └── _tutor.py         Python Tutor-style line-by-line stepper
├── tests/                Pytest suite (one file per module)
├── assets/               Browser playground (app.js, app.css, bridge.py)
├── docs/                 Tutorial notebooks (EN + zh-CN) and static HTML
├── examples/             Quickstart script and demo notebook
├── .github/workflows/    CI: tests on Python 3.9, 3.12, 3.13
└── pyproject.toml        Build config, metadata, pytest options
```

## Coding conventions

### Style

- Follow the existing code style: 4-space indent, double quotes for strings,
  `from __future__ import annotations` at the top of every module.
- Every public function and class must have a docstring. Private helpers
  (names starting with `_`) should have a one-line docstring or comment when
  their purpose is not obvious from the name.
- Use `typing` annotations on all function signatures. The codebase supports
  Python 3.9, so avoid 3.10+ syntax (no `X | Y` unions, no `match` statements).

### Module boundaries

- `_trace.py` owns the `trace` decorator, `TraceRecorder`, and `RunConfiguration`.
  It is the only module that executes user code.
- `_model.py` owns the data structures. It must not import from `_trace` or
  `_render`.
- `_render.py` owns all HTML/SVG generation. It may import from `_model` but
  not from `_trace`.
- `_report.py` owns the serializable report objects. It imports from `_model`
  and lazily imports `_render` inside methods to avoid a circular dependency.
- `_doctor.py` owns pattern detection. It reads from `TraceReport` and
  `CallNode` but does not execute user code.
- `_tutor.py` owns the stepper. It uses `sys.settrace` and is independent of
  the `trace` decorator.
- `_complexity.py` fits growth models from measured counts. It uses only the
  standard library and imports no other RecursionLens modules.

### Testing

- Every new feature or bug fix must include a test.
- Tests are in `tests/`, one file per source module. Name them
  `test_<module>.py`.
- Tests must be deterministic and not depend on a Jupyter kernel. Tests that
  need ipywidgets should use `pytest.importorskip("ipywidgets")`.
- Run the full suite before pushing:

```bash
python -m pytest tests -v
```

### Documentation

- The README is bilingual: `README.md` (English) and `README.zh-CN.md`
  (Simplified Chinese). Update both together.
- Tutorial notebooks in `docs/` also have EN and zh-CN versions. Keep them
  synchronized.
- If you add a public API, add it to `__all__` in `__init__.py` and mention it
  in the README.

## CI

GitHub Actions runs on every push and pull request:

- Python 3.9 on Ubuntu 22.04
- Python 3.12 on Ubuntu latest
- Python 3.13 on Ubuntu latest

Each job installs the package with `.[dev]`, runs pytest, and runs the
quickstart script. All three jobs must pass before a pull request can merge.

## Pull request checklist

- [ ] Tests pass locally on your target Python version
- [ ] New code has tests
- [ ] Public API changes are reflected in `__all__` and the README
- [ ] Both English and Chinese docs are updated if documentation changes
- [ ] No new runtime dependencies (the package must stay zero-dependency)
- [ ] The quickstart script runs without error: `python examples/quickstart.py`

## Release process

1. Update `version` in `pyproject.toml` and `__version__` in `__init__.py`.
2. Add an entry to `CHANGELOG.md`.
3. Update the README if the version number appears in install instructions.
4. Run the full test suite and the quickstart.
5. Build and check:

```bash
python -m build
python -m twine check dist/*
```

6. Tag the commit and push. The maintainers will handle the PyPI upload.

## License

By contributing, you agree that your changes are licensed under the MIT
License, as described in `LICENSE`.
