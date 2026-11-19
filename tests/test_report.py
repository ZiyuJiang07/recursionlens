"""Unit tests for :class:`TraceReport` and :class:`ComparisonReport` properties.

These tests exercise the report objects directly, including the fallback
paths where runtime counts are not provided and the report must compute
metrics from the node list.
"""

import pytest

from recursionlens import trace
from recursionlens._model import CallNode, build_dag
from recursionlens._report import ComparisonReport, TraceReport


def _make_simple_report():
    """Build a TraceReport manually with three nodes: fib(2) → fib(1), fib(0)."""
    root = CallNode(call_id=0, identity="0:fib(2)", signature="fib(n=2)", depth=0, status="returned", result="1")
    child_a = CallNode(call_id=1, identity="1:fib(1)", signature="fib(n=1)", depth=1, status="returned", result="1")
    child_b = CallNode(call_id=2, identity="2:fib(0)", signature="fib(n=0)", depth=1, status="returned", result="0")
    root.children = [child_a, child_b]

    return TraceReport(
        function_name="fib",
        value=1,
        nodes=[root, child_a, child_b],
        roots=[root],
        total_calls=3,
        max_depth=1,
        memoize=False,
        succeeded=True,
    )


# -- TraceReport without runtime counts ----------------------------------------

def test_report_without_runtime_counts_falls_back_to_nodes():
    """When _executed_calls and _cached_calls are None, counts come from nodes."""
    report = _make_simple_report()

    # All three nodes are "returned" (not cached), so executed = 3, cached = 0
    assert report.executed_calls == 3
    assert report.cached_calls == 0


def test_report_with_runtime_counts_uses_them():
    report = _make_simple_report()
    report._executed_calls = 99
    report._cached_calls = 7

    assert report.executed_calls == 99
    assert report.cached_calls == 7


def test_report_recorded_calls():
    report = _make_simple_report()
    assert report.recorded_calls == 3


# -- TraceReport DAG caching ---------------------------------------------------

def test_dag_nodes_are_cached():
    report = _make_simple_report()
    nodes1 = report.dag_nodes
    nodes2 = report.dag_nodes
    # The same list object should be returned (cached)
    assert nodes1 is nodes2


def test_dag_edges_are_cached():
    report = _make_simple_report()
    edges1 = report.dag_edges
    edges2 = report.dag_edges
    assert edges1 is edges2


# -- TraceReport properties ----------------------------------------------------

def test_result_returns_root_result():
    report = _make_simple_report()
    assert report.result == "1"


def test_error_returns_none_on_success():
    report = _make_simple_report()
    assert report.error is None


def test_error_returns_root_error():
    root = CallNode(call_id=0, identity="a", signature="f()", depth=0, status="error", error="ValueError: bad")
    report = TraceReport(
        function_name="f", value=None, nodes=[root], roots=[root],
        total_calls=1, max_depth=0, succeeded=False,
    )
    assert report.error == "ValueError: bad"


def test_result_and_error_none_when_no_roots():
    report = TraceReport(
        function_name="f", value=None, nodes=[], roots=[],
        total_calls=0, max_depth=0,
    )
    assert report.result is None
    assert report.error is None


def test_unique_subproblems():
    report = _make_simple_report()
    assert report.unique_subproblems == 3  # all distinct identities


def test_repeated_calls():
    report = _make_simple_report()
    assert report.repeated_calls == 0  # no repeats


# -- metrics / to_dict ---------------------------------------------------------

def test_metrics_keys():
    report = _make_simple_report()
    m = report.metrics()
    expected_keys = {
        "total_calls", "recorded_calls", "executed_calls", "cached_calls",
        "unique_subproblems", "repeated_calls", "max_depth",
        "memoize", "truncated", "succeeded",
    }
    assert set(m.keys()) == expected_keys


def test_to_dict_schema():
    report = _make_simple_report()
    data = report.to_dict()
    assert data["schema_version"] == 1
    assert data["function_name"] == "fib"
    assert data["result"] == "1"
    assert data["error"] is None
    assert len(data["roots"]) == 1
    assert "nodes" in data["dag"]
    assert "edges" in data["dag"]


# -- ComparisonReport ----------------------------------------------------------

def test_comparison_same_result_true():
    @trace
    def fib(n):
        if n < 2:
            return n
        return fib(n - 1) + fib(n - 2)

    naive = fib.run(5)
    memoized = fib.with_options(memoize=True).run(5)
    comparison = naive.compare(memoized)

    assert comparison.same_result is True


def test_comparison_same_result_false_on_different_values():
    @trace
    def identity(value):
        return value

    a = identity.run(1)
    b = identity.run(2)
    comparison = a.compare(b)

    assert comparison.same_result is False


def test_comparison_same_result_false_on_failed_run():
    @trace
    def fail():
        raise ValueError("broken")

    @trace
    def ok():
        return 1

    with pytest.raises(ValueError):
        fail.run()
    a = fail.last_report
    b = ok.run()
    comparison = a.compare(b)

    assert comparison.same_result is False


def test_comparison_to_dict_has_deltas():
    @trace
    def fib(n):
        if n < 2:
            return n
        return fib(n - 1) + fib(n - 2)

    naive = fib.run(5)
    memoized = fib.with_options(memoize=True).run(5)
    data = naive.compare(memoized).to_dict()

    assert "delta" in data
    assert data["delta"]["executed_calls"] == -9
    assert data["labels"] == ["naive", "memoized"]
    assert data["same_result"] is True


def test_comparison_to_dict_with_custom_labels():
    @trace
    def fib(n):
        if n < 2:
            return n
        return fib(n - 1) + fib(n - 2)

    naive = fib.run(3)
    memoized = fib.with_options(memoize=True).run(3)
    comparison = naive.compare(memoized, labels=("without", "with"))
    data = comparison.to_dict()

    assert data["labels"] == ["without", "with"]
