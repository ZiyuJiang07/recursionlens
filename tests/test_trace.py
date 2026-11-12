import pytest

from recursionlens import trace


@trace
def fib(n):
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)


@trace
def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)


def test_naive_fib_metrics_and_value():
    report = fib.run(5)

    assert report.value == 5
    assert report.total_calls == 15
    assert report.executed_calls == 15
    assert report.cached_calls == 0
    assert report.unique_subproblems == 6
    assert report.repeated_calls == 9
    assert report.max_depth == 5


def test_memoized_fib_metrics_and_same_value():
    naive = fib.run(5)
    memoized = fib.with_options(memoize=True).run(5)

    assert memoized.value == naive.value
    assert memoized.executed_calls == 6
    assert memoized.cached_calls == 3
    assert memoized.total_calls == 9
    assert memoized.unique_subproblems == 6


def test_fib_four_dag():
    report = fib.run(4)

    assert report.total_calls == 9
    assert report.unique_subproblems == 5
    assert len(report.dag_edges) == 6


def test_linear_recursion_has_no_repeated_subproblems():
    report = factorial.run(4)

    assert report.value == 24
    assert report.total_calls == 4
    assert report.max_depth == 4
    assert report.repeated_calls == 0


def test_positional_and_keyword_arguments_share_signature():
    positional = fib.run(4)
    keyword = fib.run(n=4)

    assert [node.signature for node in positional.dag_nodes] == [
        node.signature for node in keyword.dag_nodes
    ]


def test_normal_call_returns_value_and_exposes_report():
    assert fib(5) == 5
    assert fib.last_report.total_calls == 15


def test_exception_is_recorded_and_reraised():
    @trace
    def fail(n):
        if n == 0:
            raise ValueError("bottom")
        return fail(n - 1)

    with pytest.raises(ValueError, match="bottom"):
        fail.run(2)

    report = fail.last_report
    assert report.total_calls == 3
    assert report.roots[0].status == "error"
    assert report.nodes[-1].error == "ValueError: bottom"
    assert factorial(3) == 6


def test_truncation_preserves_result():
    complete = fib.run(5)
    limited = fib.with_options(max_calls=4).run(5)

    assert limited.value == complete.value
    assert limited.recorded_calls == 4
    assert limited.total_calls == 15
    assert limited.truncated is True


def test_unhashable_arguments_warn_instead_of_crashing():
    @trace
    def length(items):
        if len(items) <= 1:
            return len(items)
        midpoint = len(items) // 2
        return length(items[:midpoint]) + length(items[midpoint:])

    report = length.with_options(memoize=True).run([1, 2, 3])

    assert report.value == 3
    assert report.warnings


def test_json_schema_contains_tree_dag_and_metrics():
    data = fib.run(4).to_dict()

    assert data["schema_version"] == 1
    assert data["metrics"]["total_calls"] == 9
    assert len(data["dag"]["nodes"]) == 5
    assert len(data["dag"]["edges"]) == 6
    assert data["roots"][0]["children"]


def test_comparison_deltas():
    comparison = fib.run(5).compare(fib.with_options(memoize=True).run(5)).to_dict()

    assert comparison["left"]["executed_calls"] == 15
    assert comparison["right"]["executed_calls"] == 6
    assert comparison["delta"]["executed_calls"] == -9
