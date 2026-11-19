"""Unit tests for rendering helpers in :mod:`recursionlens._render`.

These tests exercise the utility functions (``esc``, ``short``,
``compact_call``, ``_mono_width``, ``dag_depths``) directly.
"""

import pytest

from recursionlens._model import DAGNode
from recursionlens._render import compact_call, dag_depths, esc, short, _mono_width


# -- esc -----------------------------------------------------------------------

def test_esc_html_escapes_special_characters():
    assert esc("<script>") == "&lt;script&gt;"
    assert esc('"hello"') == "&quot;hello&quot;"
    assert esc("'world'") == "&#x27;world&#x27;"
    assert esc("&") == "&amp;"


def test_esc_passes_through_plain_text():
    assert esc("hello") == "hello"
    assert esc(42) == "42"


# -- short ---------------------------------------------------------------------

def test_short_preserves_short_strings():
    assert short("hello") == "hello"
    assert short("a" * 34) == "a" * 34


def test_short_truncates_long_strings():
    result = short("a" * 100, limit=10)
    assert len(result) == 10
    assert result.endswith("...")


def test_short_custom_limit():
    assert short("abcdef", limit=6) == "abcdef"
    assert short("abcdefg", limit=6) == "abc..."


# -- compact_call --------------------------------------------------------------

def test_compact_call_strips_parameter_names():
    assert compact_call("fib(n=5)") == "fib(5)"
    assert compact_call("factorial(n=10)") == "factorial(10)"


def test_compact_call_handles_multiple_args():
    assert compact_call("paths(row=3, col=4)") == "paths(3, 4)"


def test_compact_call_truncates_long_signatures():
    long_sig = "very_long_function_name(arg=" + "x" * 50 + ")"
    result = compact_call(long_sig)
    assert len(result) <= 18


def test_compact_call_handles_no_args():
    assert compact_call("func()") == "func()"


def test_compact_call_handles_non_signature_text():
    assert compact_call("not a signature") == "not a signature"


# -- _mono_width ---------------------------------------------------------------

def test_mono_width_scales_with_length():
    assert _mono_width("abc") > _mono_width("ab")
    assert _mono_width("abc") > _mono_width("")


def test_mono_width_scales_with_size():
    assert _mono_width("abc", size=14.0) > _mono_width("abc", size=12.0)


def test_mono_width_empty_string():
    assert _mono_width("") == 0.0


# -- dag_depths ----------------------------------------------------------------

def test_dag_depths_single_node():
    nodes = [DAGNode(identity="a", signature="f()")]
    depths = dag_depths(nodes)
    assert depths == {"a": 0}


def test_dag_depths_linear_chain():
    nodes = [
        DAGNode(identity="a", signature="f(3)", children=["b"]),
        DAGNode(identity="b", signature="f(2)", children=["c"]),
        DAGNode(identity="c", signature="f(1)"),
    ]
    depths = dag_depths(nodes)
    assert depths == {"a": 2, "b": 1, "c": 0}


def test_dag_depths_diamond():
    nodes = [
        DAGNode(identity="a", signature="f(3)", children=["b", "c"]),
        DAGNode(identity="b", signature="f(2)", children=["d"]),
        DAGNode(identity="c", signature="f(1)", children=["d"]),
        DAGNode(identity="d", signature="f(0)"),
    ]
    depths = dag_depths(nodes)
    assert depths["a"] == 2
    assert depths["d"] == 0


def test_dag_depths_empty():
    assert dag_depths([]) == {}


def test_dag_depths_cycle_safe():
    """If a cycle somehow exists, dag_depths should not infinite-loop."""
    nodes = [
        DAGNode(identity="a", signature="f()", children=["b"]),
        DAGNode(identity="b", signature="g()", children=["a"]),
    ]
    depths = dag_depths(nodes)
    assert "a" in depths
    assert "b" in depths
