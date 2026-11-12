import json

import pytest

from recursionlens import trace


@trace
def fib(n):
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)


def test_tree_html_is_self_contained_and_jupyter_compatible():
    report = fib.run(4)
    output = report._repr_html_()

    assert "Call tree" in output
    assert "fib(n=4)" in output
    assert "repeated" in output
    assert "https://" not in output
    assert "<script" not in output


def test_dag_html_contains_svg_and_merged_counts():
    output = fib.run(4).to_html(mode="dag")

    assert "Subproblem DAG" in output
    assert "<svg" in output
    assert "calls 2" in output


def test_invalid_view_mode_is_rejected():
    with pytest.raises(ValueError, match="mode"):
        fib.run(3).to_html(mode="unknown")


def test_memoized_dag_marks_cache_hits():
    output = fib.with_options(memoize=True).run(5).to_html(mode="dag")

    assert "cache hit" in output
    assert "cached 1" in output


def test_user_values_are_html_escaped():
    @trace
    def identity(value):
        return value

    output = identity.run("<script>alert('x')</script>").to_html()

    assert "<script>alert" not in output
    assert "&lt;script&gt;" in output


def test_json_and_html_exports(tmp_path):
    report = fib.run(4)
    json_path = report.export_json(tmp_path / "trace.json")
    html_path = report.export_html(tmp_path / "trace.html", mode="dag")

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["metrics"]["unique_subproblems"] == 5
    assert html_path.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")


def test_comparison_html_and_export(tmp_path):
    naive = fib.run(5)
    memoized = fib.with_options(memoize=True).run(5)
    comparison = naive.compare(memoized)
    output = comparison._repr_html_()

    assert "execution comparison" in output
    assert "naive" in output
    assert "memoized" in output
    assert "-9" in output
    assert "same returned value: yes" in output

    path = comparison.export_html(tmp_path / "comparison.html")
    assert "execution comparison" in path.read_text(encoding="utf-8")


def test_truncated_report_explains_partial_metrics():
    output = fib.with_options(max_calls=3).run(5).to_html()

    assert "recording limit was reached" in output
