# RecursionLens user guide

> New to JupyterLab? Open the [pre-rendered tutorial](RecursionLens_Tutorial.ipynb). Its trees and DAGs are visible immediately, and it includes a one-minute demo recipe.

## Use case 1: understand a recursive call

Decorate a synchronous function with `@trace`. A normal call returns the original value and stores its latest report:

```python
from recursionlens import trace

@trace
def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)

factorial(4)
factorial.last_report
```

Use `run` when you want the report directly:

```python
report = factorial.run(4)
print(report.value)               # 24
print(report.total_calls)         # 4
print(report.unique_subproblems)  # 4
print(report.repeated_calls)      # 0
print(report.max_depth)           # 4
```

## Use case 2: expose repeated subproblems

```python
@trace
def fib(n):
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)

naive = fib.run(5)
naive.show(mode="tree")
naive.show(mode="dag")
naive.show(mode="expanded")
```

The default tree is collapsible. `mode="expanded"` renders every recorded invocation at once as a compact SVG tree, with no nodes collapsed. Repeated calls are underlined coral, cache hits are green, and errors are red. The DAG merges all nodes with the same bound arguments, while retaining dependency edges and execution counts.

## Use case 3: measure the effect of memoization

```python
naive = fib.run(5)
memoized = fib.with_options(memoize=True).run(5)
comparison = naive.compare(memoized, labels=("naive", "memoized"))
comparison
```

Run options live on `with_options`, so every keyword accepted by your function is forwarded untouched by `run`.

`total_calls` includes cache-only invocations. `executed_calls` excludes cache hits. This distinction is why the memoized report can observe nine calls while executing only six function bodies.

Memoization is intended for deterministic functions with hashable arguments. Do not use it as a semantic guarantee for functions that read files, consume randomness, depend on global state, or perform other side effects.

## Use case 4: export evidence

```python
naive.export_json("trace.json")
naive.export_html("tree.html")
naive.export_html("dag.html", mode="dag")
naive.export_html("expanded.html", mode="expanded")
comparison.export_html("comparison.html")
```

The JSON schema has a `schema_version` field. HTML reports are self-contained and require no network access.

## Limits and troubleshooting

### The report is truncated

The default recording limit is 1,000 nodes. Increase it deliberately for a larger example:

```python
report = fib.with_options(max_calls=5000).run(7)
```

The function still runs normally after the recording limit is reached. `total_calls` counts all observed calls, while tree and DAG metrics only cover recorded nodes.

### Memoization did not apply

If bound arguments are unhashable, RecursionLens leaves those calls uncached and adds a warning. Convert teaching inputs to immutable values such as tuples when appropriate.

### HTML does not appear

In JupyterLab, finish a cell with `report` or call `report.show()`. Outside IPython, `show()` returns the HTML string when IPython is unavailable. You can always use `export_html()` instead.

### Exceptions

Exceptions are recorded on the affected nodes and re-raised. Access `function.last_report` to inspect the failed run. RecursionLens does not suppress or repair the original error.
