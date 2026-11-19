"""Cache hits must come from the code's own cache, not from RecursionLens."""

import functools

from recursionlens import trace


def test_lru_cache_hits_are_detected():
    @trace
    @functools.lru_cache(maxsize=None)
    def fib(n):
        return n if n < 2 else fib(n - 1) + fib(n - 2)

    report = fib.run(10)

    assert report.recorded_calls == 19
    assert report.cached_calls == 8
    assert report.executed_calls == 11
    assert sum(node.cached for node in report.nodes) == 8
    assert report.metrics()["cached_calls"] == 8


def test_functools_cache_is_detected_too():
    @trace
    @functools.cache
    def fib(n):
        return n if n < 2 else fib(n - 1) + fib(n - 2)

    report = fib.run(8)

    assert report.cached_calls == 6
    assert report.executed_calls == 9


def test_cached_nodes_do_not_execute_the_body():
    executions = []

    @trace
    @functools.lru_cache(maxsize=None)
    def fib(n):
        executions.append(n)
        return n if n < 2 else fib(n - 1) + fib(n - 2)

    report = fib.run(5)

    assert sorted(executions) == [0, 1, 2, 3, 4, 5]
    assert report.cached_calls == 3
    assert all(not node.children for node in report.nodes if node.cached)


def test_plain_recursion_reports_no_cache_hits():
    @trace
    def fib(n):
        return n if n < 2 else fib(n - 1) + fib(n - 2)

    report = fib.run(6)

    assert report.cached_calls == 0
    assert report.executed_calls == report.recorded_calls


def test_memoize_mode_still_counts_its_own_hits():
    @trace
    def fib(n):
        return n if n < 2 else fib(n - 1) + fib(n - 2)

    report = fib.with_options(memoize=True).run(6)

    assert report.cached_calls > 0
    assert report.executed_calls + report.cached_calls == report.recorded_calls


def test_bypass_cache_runs_the_plain_algorithm():
    @trace
    @functools.lru_cache(maxsize=None)
    def fib(n):
        return n if n < 2 else fib(n - 1) + fib(n - 2)

    fib.cache_clear()
    cached = fib.run(10)
    baseline = fib.with_options(bypass_cache=True).run(10)

    assert cached.recorded_calls == 19
    assert baseline.recorded_calls == 177
    assert baseline.cached_calls == 0
    assert baseline.value == cached.value


def test_comparison_uses_the_uncached_baseline():
    @trace
    @functools.lru_cache(maxsize=None)
    def fib(n):
        return n if n < 2 else fib(n - 1) + fib(n - 2)

    fib.cache_clear()
    cached = fib.run(10)
    baseline = fib.with_options(bypass_cache=True).run(10)
    comparison = baseline.compare(cached, labels=("no cache", "with cache"))
    data = comparison.to_dict()

    assert data["labels"] == ["no cache", "with cache"]
    assert data["left"]["total_calls"] == 177
    assert data["right"]["total_calls"] == 19
    assert data["delta"]["executed_calls"] == -166
    assert data["same_result"] is True


def test_bypass_leaves_the_cache_untouched():
    @trace
    @functools.lru_cache(maxsize=None)
    def fib(n):
        return n if n < 2 else fib(n - 1) + fib(n - 2)

    fib.cache_clear()
    fib.with_options(bypass_cache=True).run(6)

    assert fib.cache_info().currsize == 0


def test_plain_functions_report_no_cache():
    @trace
    def fib(n):
        return n if n < 2 else fib(n - 1) + fib(n - 2)

    assert fib.has_cache is False
