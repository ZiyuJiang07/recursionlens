# RecursionLens

**English** | [简体中文](https://github.com/ZiyuJiang07/recursionlens/blob/main/README.zh-CN.md)

**See not just what recursion returns, but where the repeated work happens.**

RecursionLens is a zero-runtime-dependency Python package for exploring recursive execution in JupyterLab. It turns a traced run into an expandable call tree, a compressed subproblem DAG, and a quantitative naive-versus-memoized comparison.

> **JupyterLab tutorial, already executed:** [Open RecursionLens_Tutorial.ipynb](https://github.com/ZiyuJiang07/recursionlens/blob/main/docs/RecursionLens_Tutorial.ipynb). All eight code cells have saved output. If Jupyter hides HTML/SVG from a downloaded notebook, use its **Trust** action or click **Run All Cells** once. For a zero-setup preview, download and open the [static HTML companion](https://github.com/ZiyuJiang07/recursionlens/raw/main/docs/RecursionLens_Tutorial.html).

## Project team

CS1302A Group 50:

- Ziyu JIANG
- Xinyue CAI
- Kehan CAO
- Ruoxi LYU
- Haobo MA

## Why RecursionLens?

A recursive function normally exposes only its final return value or traceback. Students still have to reconstruct the execution in their heads. RecursionLens answers three different questions:

1. **Call tree:** what actually happened, invocation by invocation?
2. **Subproblem DAG:** how many distinct problems and dependencies exist after identical arguments are merged?
3. **Execution comparison:** what changes when memoization is enabled?

For `fib(5)`, that story is **15 observed calls → 6 unique subproblems → 6 executed bodies with memoization**.

## Innovation beyond a call graph

The existing `rcviz` package documents decorator-based recursion trees with arguments, return values, and Jupyter rendering. RecursionLens deliberately focuses on a different workflow:

- transform one trace between an invocation tree and a compressed subproblem DAG;
- show the complete call tree at once in an SVG view or keep a collapsible tree for larger runs;
- quantify repeated calls, executed bodies, cache hits, and maximum depth;
- compare naive and memoized runs in one report with side-by-side DAGs;
- render self-contained HTML/SVG in JupyterLab without Graphviz, native libraries, external JavaScript, or a CDN;
- export versioned JSON for reproducible analysis and testing.

## Installation

RecursionLens requires Python 3.9 or later.

Install from PyPI:

```bash
python -m pip install recursionlens
```

For local development:

```bash
git clone https://github.com/ZiyuJiang07/recursionlens.git
cd recursionlens
python -m pip install -e ".[dev]"
```

The package has no runtime dependencies.

## Quickstart in JupyterLab

```python
from recursionlens import trace

@trace
def fib(n):
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)

naive = fib.run(5)
naive  # expandable call tree in the notebook output area
```

Switch the same trace to the compressed subproblem DAG:

```python
naive.show(mode="dag")
```

Or show every call at once as one compact SVG tree, with no nodes collapsed:

```python
naive.show(mode="expanded")
```

Run the function again with memoization and compare the evidence:

```python
memoized = fib.with_options(memoize=True).run(5)
comparison = naive.compare(memoized)
comparison
```

The comparison confirms the returned values match and reports the measured changes, including **15 → 6 executed function bodies**.

Normal function behavior is preserved:

```python
assert fib(5) == 5
assert fib.last_report.total_calls == 15
```

## Export a report

```python
naive.export_html("fib-tree.html")
naive.export_html("fib-dag.html", mode="dag")
naive.export_json("fib-trace.json")
comparison.export_html("fib-comparison.html")
```

HTML reports are standalone files that can be opened without a notebook server. JSON contains the tree, DAG nodes and edges, metrics, warnings, and schema version.

## Supported scope

Version 0.1 targets synchronous, deterministic teaching examples such as factorial, Fibonacci, and pure mathematical recursion.

- Memoization requires hashable bound arguments; unhashable arguments produce a warning instead of a crash.
- Identical arguments do not necessarily imply redundant work for functions with side effects or external state.
- `max_calls` bounds the stored tree without changing the function's result. A truncated report explicitly marks partial tree/DAG metrics.
- RecursionLens executes your function; it is **not a sandbox for untrusted code**.
- Async functions, generators, automatic Big-O inference, and automatic code rewriting are non-goals for 0.1.

## Documentation and demo

- [Executed JupyterLab tutorial](https://github.com/ZiyuJiang07/recursionlens/blob/main/docs/RecursionLens_Tutorial.ipynb) - setup, three views, comparison, export, troubleshooting, and a one-minute demo recipe
- [Static HTML tutorial preview](https://github.com/ZiyuJiang07/recursionlens/raw/main/docs/RecursionLens_Tutorial.html) - the same tutorial with all visual reports rendered, no Jupyter required
- [Runnable example notebook](https://github.com/ZiyuJiang07/recursionlens/blob/main/examples/demo.ipynb)
- [User guide](https://github.com/ZiyuJiang07/recursionlens/blob/main/docs/USER.md)
- [Developer guide](https://github.com/ZiyuJiang07/recursionlens/blob/main/docs/DEVELOPER.md)
- [Changelog](https://github.com/ZiyuJiang07/recursionlens/blob/main/CHANGELOG.md)

## Development and testing

```bash
python -m pytest tests -v
python -m build
python -m twine check dist/*
```

The test suite covers trace invariants, cache behavior, signatures, exceptions, truncation, JSON, HTML escaping, DAG rendering, and comparison reports. Contributions should keep the public API, tests, and user documentation synchronized.

## License

MIT © 2026 Ziyu JIANG, Xinyue CAI, Kehan CAO, Ruoxi LYU, Haobo MA.
