from pathlib import Path

from recursionlens import trace


@trace
def fib(n):
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)


naive = fib.run(5)
memoized = fib.with_options(memoize=True).run(5)
comparison = naive.compare(memoized)

assert naive.total_calls == 15
assert naive.unique_subproblems == 6
assert memoized.executed_calls == 6
assert memoized.cached_calls == 3
assert naive.value == memoized.value == 5

output = Path(__file__).parent
naive.export_html(output / "fib-tree.html")
naive.export_html(output / "fib-dag.html", mode="dag")
naive.export_html(output / "fib-expanded.html", mode="expanded")
naive.export_json(output / "fib-trace.json")
comparison.export_html(output / "fib-comparison.html")

print("RecursionLens quickstart passed")
print(f"Naive: {naive.executed_calls} executed bodies")
print(f"Memoized: {memoized.executed_calls} executed bodies, {memoized.cached_calls} cache hits")
print(f"Reports written to {output}")
