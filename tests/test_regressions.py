import re

import pytest

from recursionlens import trace


def test_memoization_distinguishes_equal_values_with_different_types():
    @trace
    def type_name(value):
        return type(value).__name__

    @trace
    def pair():
        return type_name(1), type_name(1.0)

    report = pair.with_options(memoize=True).run()

    assert report.value == ("int", "float")
    assert report.unique_subproblems == 3


def test_run_forwards_arguments_named_memoize_and_max_calls():
    @trace
    def option(memoize=False, max_calls=0):
        return memoize, max_calls

    report = option.run(memoize="user", max_calls=7)

    assert report.value == ("user", 7)


def test_untruncated_identity_keeps_long_argument_values_distinct():
    @trace
    def leaf(value):
        return value[-1]

    @trace
    def pair():
        return leaf("a" * 200 + "x") + leaf("a" * 200 + "y")

    report = pair.run()

    assert report.total_calls == 3
    assert report.unique_subproblems == 3
    assert report.repeated_calls == 0


def test_factory_functions_with_same_qualname_are_not_merged():
    def factory(label):
        @trace
        def leaf(value):
            return label

        return leaf

    first = factory("first")
    second = factory("second")

    @trace
    def pair():
        return first(1), second(1)

    report = pair.run()

    assert report.value == ("first", "second")
    assert report.unique_subproblems == 3


def test_exception_formatting_cannot_replace_original_exception():
    class BadError(Exception):
        def __str__(self):
            raise RuntimeError("formatting failed")

    @trace
    def fail():
        raise BadError("original")

    with pytest.raises(BadError):
        fail.run()

    assert "BadError" in fail.last_report.error
    assert "message unavailable" in fail.last_report.error


def test_dag_edges_flow_left_to_right_outside_node_boxes():
    @trace
    def fib(n):
        if n < 2:
            return n
        return fib(n - 1) + fib(n - 2)

    output = fib.run(2).to_html(mode="dag")
    paths = re.findall(r'<path d="M([\d.]+),[\d.]+ L([\d.]+),', output)

    assert len(paths) == 2
    for source_x, target_x in paths:
        assert float(source_x) < float(target_x)


def test_comparison_uses_returned_values_not_repr_strings():
    @trace
    def identity(value):
        return value

    comparison = identity.run(1).compare(identity.run(1.0))

    assert comparison.same_result is True
    assert "same returned value: yes" in comparison.to_html()


def test_failed_run_header_does_not_claim_returned_none():
    @trace
    def fail():
        raise ValueError("broken")

    with pytest.raises(ValueError):
        fail.run()

    output = fail.last_report.to_html()

    assert "raised <code>ValueError: broken</code>" in output
    assert "returned <code>None</code>" not in output


def test_show_fallbacks_return_html_without_ipython(monkeypatch):
    @trace
    def identity(value):
        return value

    report = identity.run(1)
    comparison = report.compare(identity.run(1))
    monkeypatch.setitem(__import__("sys").modules, "IPython", None)

    assert isinstance(report.show(), str)
    assert isinstance(comparison.show(), str)
