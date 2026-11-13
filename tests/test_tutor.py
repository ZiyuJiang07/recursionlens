import pytest

from recursionlens import record_tutor, tutor
from recursionlens._tutor import DEFAULT_CODE

FIB = """def fib(n):
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)
"""


def test_records_a_step_per_line_call_and_return():
    trace = record_tutor(FIB, "fib(5)")

    assert trace.error is None
    assert trace.result == "5"
    assert trace.step_count == 60
    assert trace.max_depth == 5
    assert trace.steps[0].event == "call"
    assert trace.steps[0].depth == 1
    assert trace.steps[-1].event == "return"
    assert trace.steps[-1].value == "5"


def test_changing_the_input_changes_the_recording():
    small = record_tutor(FIB, "fib(3)")
    large = record_tutor(FIB, "fib(6)")

    assert small.result == "2"
    assert large.result == "8"
    assert small.step_count < large.step_count
    assert small.max_depth == 3
    assert large.max_depth == 6


def test_stack_snapshots_show_recursive_frames_and_locals():
    trace = record_tutor(FIB, "fib(3)")
    deepest = max(trace.steps, key=lambda step: step.depth)

    assert [frame.function for frame in deepest.frames] == ["fib"] * 3
    assert "n" in deepest.frames[-1].variables
    assert all("n" in frame.variables for frame in deepest.frames)


def test_line_numbers_stay_inside_the_source():
    trace = record_tutor(FIB, "fib(4)")
    line_count = len(FIB.splitlines())

    assert all(1 <= step.line <= line_count for step in trace.steps)
    assert {step.event for step in trace.steps} == {"call", "line", "return"}


def test_return_values_are_recorded_per_frame():
    trace = record_tutor(FIB, "fib(4)")
    returns = [step.value for step in trace.steps if step.event == "return"]

    assert returns[-1] == "3"
    assert "1" in returns


def test_exception_is_recorded_and_reported():
    code = """def countdown(n):
    if n == 0:
        raise ValueError("boom")
    return countdown(n - 1)
"""
    trace = record_tutor(code, "countdown(2)")

    assert trace.error == "ValueError: boom"
    assert trace.result is None
    assert any(step.event == "exception" for step in trace.steps)


def test_print_output_is_captured_progressively():
    code = """def down(n):
    print("enter", n)
    if n == 0:
        return 0
    return down(n - 1)
"""
    trace = record_tutor(code, "down(2)")
    outputs = [step.output for step in trace.steps if step.output]

    assert trace.stdout == "enter 2\nenter 1\nenter 0\n"
    assert outputs[0].strip() == "enter 2"
    assert outputs[-1] == trace.stdout


def test_syntax_error_is_reported_without_raising():
    trace = record_tutor("def broken(:\n    pass\n", "broken()")

    assert trace.steps == []
    assert trace.error and trace.error.startswith("SyntaxError")


def test_unknown_function_explains_the_problem():
    trace = record_tutor(FIB, "missing(5)")

    assert trace.error == "NameError: name 'missing' is not defined"


def test_calling_a_non_function_produces_guidance():
    trace = record_tutor("x = 1\n", "x")

    assert trace.steps == []
    assert "did not call a function" in trace.error


def test_plain_code_without_a_call_is_rejected_early():
    trace = record_tutor(FIB, "   ")

    assert trace.steps == []
    assert "Enter an expression" in trace.error


def test_default_code_matches_the_documented_example():
    assert "def fib(n):" in DEFAULT_CODE


def test_widget_builds_and_steps_through_the_trace():
    pytest.importorskip("ipywidgets")
    player = tutor()

    assert player.trace is not None and player.trace.step_count == 60
    trace = player.run()

    assert trace.step_count == 60
    assert player.slider.max == 59
    assert "step 1 / 60" in player.status.value
    assert 'class="ln cur"' in player.code_html.value
    assert "rl-tutor-frame" in player.stack_html.value

    player.go(2)

    assert "step 3 / 60" in player.status.value
    assert "line 4" in player.status.value


def test_widget_reruns_with_a_new_input_value():
    pytest.importorskip("ipywidgets")
    player = tutor()

    player.run(call="fib(4)")
    assert player.trace.step_count == 36
    assert player.slider.max == 35

    player.run(call="fib(3)")
    assert player.trace.step_count == 20
    assert player.slider.max == 19
