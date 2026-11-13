# RecursionLens

**English** | [简体中文](https://github.com/ZiyuJiang07/recursionlens/blob/main/README.zh-CN.md)

**See not just what recursion returns, but where the repeated work happens.**

RecursionLens is a zero-runtime-dependency Python package for exploring recursive execution in JupyterLab. It turns a traced run into an expandable call tree, a compressed subproblem DAG, and a quantitative naive-versus-memoized comparison.

> **JupyterLab tutorial, already executed:** [Open RecursionLens_Tutorial.ipynb](https://github.com/ZiyuJiang07/recursionlens/blob/main/docs/RecursionLens_Tutorial.ipynb) ([简体中文版](https://github.com/ZiyuJiang07/recursionlens/blob/main/docs/RecursionLens_Tutorial.zh-CN.ipynb)). Sixteen code cells have saved output; the final cell opens the interactive player when you run it in a live kernel. If Jupyter hides HTML/SVG from a downloaded notebook, use its **Trust** action or click **Run All Cells** once. For a zero-setup preview, download and open the [static HTML companion](https://github.com/ZiyuJiang07/recursionlens/raw/main/docs/RecursionLens_Tutorial.html) or its [Chinese version](https://github.com/ZiyuJiang07/recursionlens/raw/main/docs/RecursionLens_Tutorial.zh-CN.html).

## Project team

CS1302A Group 50:

- Ziyu JIANG
- Xinyue CAI
- Kehan CAO
- Ruoxi LYU
- Haobo MA

## Why RecursionLens?

RecursionLens grew out of a beginner's own difficulty with recursion. Loops can be read line by line, but a non-tail-recursive call such as `fib` or a tree traversal expands into many interleaved calls: the same subproblem is entered again and again, and a value only comes back after its whole subtree has finished. The step-by-step mentor provided by our course (OPT) is excellent for ordinary programs, since it shows one execution step at a time, yet a recursive run becomes a long stream of push and pop steps with no view of the overall shape of the computation, and no indication of which subproblems repeat. The usual fallback is to draw the call tree by hand on paper. RecursionLens automates that drawing and adds the numbers a hand-drawn tree cannot show.

It answers three different questions:

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

The package has no runtime dependencies. The interactive tutor is the only optional extra, and it needs `ipywidgets`.

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

## Step through a function line by line

Version 0.2 adds a Python Tutor-style player that runs inside the notebook. Paste a function, choose the call, and step through it:

```python
from recursionlens import tutor

tutor()   # editable code panel, an input box for the call, and step controls
```

The player highlights the current line, shows every stack frame with its local variables, and lets you change the call (for example `fib(5)` → `fib(3)`) to record a fresh run and redraw. It reports each call, line, return, and exception, which makes the order of a recursion easy to follow.

The tutor runs the code you paste with normal Python semantics; it is not a sandbox.

`tutor()` needs `ipywidgets`:

```bash
python -m pip install "recursionlens[tutor]"
```

The recording is plain Python, so it also works without the widget:

```python
from recursionlens import record_tutor

trace = record_tutor("def fib(n): ...", "fib(5)")
print(trace.describe())
trace.steps[0].frames        # stack snapshot for one step
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

- [Command guide (English)](https://github.com/ZiyuJiang07/recursionlens/blob/main/docs/RecursionLens_Tutorial.ipynb) - one example per public command: decorator, report object, three views, metrics, memoization, comparison, export, and error handling
- [命令手册（简体中文）](https://github.com/ZiyuJiang07/recursionlens/blob/main/docs/RecursionLens_Tutorial.zh-CN.ipynb) - the same guide in Simplified Chinese
- [Static HTML preview](https://github.com/ZiyuJiang07/recursionlens/raw/main/docs/RecursionLens_Tutorial.html) - English, no Jupyter required
- [静态 HTML 预览](https://github.com/ZiyuJiang07/recursionlens/raw/main/docs/RecursionLens_Tutorial.zh-CN.html) - 中文，不需要 Jupyter
- [Runnable example notebook](https://github.com/ZiyuJiang07/recursionlens/blob/main/examples/demo.ipynb)

## Development and testing

```bash
python -m pytest tests -v
python -m build
python -m twine check dist/*
```

The test suite covers trace invariants, cache behavior, signatures, exceptions, truncation, JSON, HTML escaping, DAG rendering, and comparison reports. Contributions should keep the public API, tests, and README synchronized.

Documentation is bilingual: `README.md` / `README.zh-CN.md` and `docs/RecursionLens_Tutorial.ipynb` / `docs/RecursionLens_Tutorial.zh-CN.ipynb` must be updated together, including their generated HTML files.

## License

MIT © 2026 Ziyu JIANG, Xinyue CAI, Kehan CAO, Ruoxi LYU, Haobo MA.
