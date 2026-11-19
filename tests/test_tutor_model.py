"""Unit tests for :class:`TutorTrace` and :class:`TutorStep` methods.

These tests exercise the data-class methods (``step`` clamping, ``describe``,
``step_count``, ``max_depth``) without relying on the widget.
"""

import pytest

from recursionlens._tutor import TutorFrame, TutorStep, TutorTrace


def _make_trace(steps=None):
    trace = TutorTrace(code="def f(): pass", call="f()")
    if steps is not None:
        trace.steps = steps
    return trace


def test_step_count_empty():
    trace = _make_trace([])
    assert trace.step_count == 0


def test_step_count_with_steps():
    steps = [
        TutorStep(index=0, event="call", function="f", line=1, depth=1),
        TutorStep(index=1, event="line", function="f", line=2, depth=1),
    ]
    trace = _make_trace(steps)
    assert trace.step_count == 2


def test_step_clamps_negative_index():
    steps = [
        TutorStep(index=0, event="call", function="f", line=1, depth=1),
        TutorStep(index=1, event="line", function="f", line=2, depth=1),
    ]
    trace = _make_trace(steps)
    assert trace.step(-1).index == 0
    assert trace.step(-100).index == 0


def test_step_clamps_overflow_index():
    steps = [
        TutorStep(index=0, event="call", function="f", line=1, depth=1),
        TutorStep(index=1, event="line", function="f", line=2, depth=1),
    ]
    trace = _make_trace(steps)
    assert trace.step(100).index == 1


def test_step_raises_on_empty_trace():
    trace = _make_trace([])
    with pytest.raises(IndexError, match="no steps"):
        trace.step(0)


def test_max_depth_empty():
    trace = _make_trace([])
    assert trace.max_depth == 0


def test_max_depth_with_steps():
    steps = [
        TutorStep(index=0, event="call", function="f", line=1, depth=1),
        TutorStep(index=1, event="call", function="g", line=2, depth=3),
        TutorStep(index=2, event="line", function="g", line=3, depth=2),
    ]
    trace = _make_trace(steps)
    assert trace.max_depth == 3


def test_describe_includes_basics():
    steps = [TutorStep(index=0, event="call", function="f", line=1, depth=1)]
    trace = _make_trace(steps)
    trace.result = "42"

    desc = trace.describe()
    assert "call: f()" in desc
    assert "steps: 1" in desc
    assert "max depth: 1" in desc
    assert "result: 42" in desc


def test_describe_includes_error():
    trace = _make_trace([])
    trace.error = "ValueError: bad"

    desc = trace.describe()
    assert "error: ValueError: bad" in desc


def test_describe_includes_truncation():
    trace = _make_trace([])
    trace.truncated = True

    desc = trace.describe()
    assert "stopped" in desc


def test_tutor_step_label_property():
    step = TutorStep(index=0, event="call", function="f", line=1, depth=1)
    assert step.label == "call"

    step.event = "line"
    assert step.label == "line"

    step.event = "return"
    assert step.label == "return"

    step.event = "exception"
    assert step.label == "exception"


def test_tutor_step_label_unknown_event():
    step = TutorStep(index=0, event="custom", function="f", line=1, depth=1)
    assert step.label == "custom"


def test_tutor_frame_has_variables():
    frame = TutorFrame(function="fib", line=2, variables={"n": "5"})
    assert frame.function == "fib"
    assert frame.line == 2
    assert frame.variables["n"] == "5"


def test_tutor_trace_defaults():
    trace = TutorTrace(code="code", call="f()")
    assert trace.steps == []
    assert trace.error is None
    assert trace.result is None
    assert trace.stdout == ""
    assert trace.truncated is False
