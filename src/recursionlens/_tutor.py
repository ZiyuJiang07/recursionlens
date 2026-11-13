"""Line-by-line stepping for recursive functions, in the spirit of Python Tutor.

The recorder in this module is pure standard library: it compiles the user's
source, runs the requested call under ``sys.settrace``, and stores one step per
line, call, return, or exception together with a snapshot of the call stack.
The optional widget in :func:`tutor` only renders those steps.
"""

from __future__ import annotations

import contextlib
import io
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

FILENAME = "<recursionlens-tutor>"
DEFAULT_CODE = """def fib(n):
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)
"""
DEFAULT_CALL = "fib(5)"
MAX_STEPS = 4000
MAX_LOCAL_CHARS = 80


@dataclass
class TutorFrame:
    """One frame of the call stack at a single step."""

    function: str
    line: int
    variables: Dict[str, str]


@dataclass
class TutorStep:
    """One recorded moment: a line, a call, a return, or an exception."""

    index: int
    event: str
    function: str
    line: int
    depth: int
    frames: List[TutorFrame] = field(default_factory=list)
    value: Optional[str] = None
    output: str = ""

    @property
    def label(self) -> str:
        names = {"call": "call", "line": "line", "return": "return", "exception": "exception"}
        return names.get(self.event, self.event)


@dataclass
class TutorTrace:
    """The full recording of one interactive run."""

    code: str
    call: str
    steps: List[TutorStep] = field(default_factory=list)
    error: Optional[str] = None
    result: Optional[str] = None
    stdout: str = ""
    truncated: bool = False

    @property
    def step_count(self) -> int:
        return len(self.steps)

    @property
    def max_depth(self) -> int:
        return max((step.depth for step in self.steps), default=0)

    def step(self, index: int) -> TutorStep:
        if not self.steps:
            raise IndexError("this trace has no steps")
        return self.steps[max(0, min(index, len(self.steps) - 1))]

    def describe(self) -> str:
        """Short human-readable summary, useful without the widget."""

        lines = [
            f"call: {self.call}",
            f"steps: {self.step_count}",
            f"max depth: {self.max_depth}",
        ]
        if self.result is not None:
            lines.append(f"result: {self.result}")
        if self.error:
            lines.append(f"error: {self.error}")
        if self.truncated:
            lines.append(f"recording stopped after {MAX_STEPS} steps")
        return "\n".join(lines)


def _short(value: Any, limit: int = MAX_LOCAL_CHARS) -> str:
    try:
        text = repr(value)
    except Exception as error:  # pragma: no cover - defensive
        return f"<unrepresentable {type(error).__name__}>"
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def _snapshot(frame) -> List[TutorFrame]:
    stack = []
    current = frame
    while current is not None:
        code = current.f_code
        if code.co_filename == FILENAME and code.co_name != "<module>":
            variables = {
                name: _short(value)
                for name, value in current.f_locals.items()
                if not name.startswith("__")
            }
            stack.append(
                TutorFrame(function=code.co_name, line=current.f_lineno, variables=variables)
            )
        current = current.f_back
    stack.reverse()
    return stack


def record_tutor(code: str, call: Optional[str] = None, max_steps: int = MAX_STEPS) -> TutorTrace:
    """Execute ``call`` in ``code`` and record every step.

    The user's code runs with normal Python semantics; RecursionLens only
    observes it. Raising the same exceptions, printing to stdout, and hitting
    the recursion limit all behave exactly as they would outside this
    recorder.
    """

    call = (call or DEFAULT_CALL).strip()
    trace = TutorTrace(code=code, call=call)
    if not call:
        trace.error = "Enter an expression to run, for example fib(5)."
        return trace

    try:
        compiled = compile(code, FILENAME, "exec")
    except SyntaxError as error:
        trace.error = f"SyntaxError: {error.msg} (line {error.lineno})"
        return trace

    namespace: Dict[str, Any] = {"__name__": "__tutor__", "__builtins__": __builtins__}
    try:
        expression = compile(call, FILENAME, "eval")
    except SyntaxError as error:
        trace.error = f"SyntaxError in call: {error.msg}"
        return trace

    output = io.StringIO()
    previous_trace = sys.gettrace()
    steps: List[TutorStep] = []
    limit_reached = [False]
    last_exception_line = [None]

    def record(event: str, frame, value: Optional[str] = None) -> None:
        if len(steps) >= max_steps:
            limit_reached[0] = True
            return
        if event != "exception":
            last_exception_line[0] = None
        stack = _snapshot(frame)
        steps.append(
            TutorStep(
                index=len(steps),
                event=event,
                function=frame.f_code.co_name,
                line=frame.f_lineno,
                depth=len(stack),
                frames=stack,
                value=value,
                output=output.getvalue(),
            )
        )

    def local_tracer(frame, event, arg):
        if frame.f_code.co_filename != FILENAME or frame.f_code.co_name == "<module>":
            return None
        if event == "line":
            record("line", frame)
        elif event == "return":
            record("return", frame, None if arg is None else _short(arg))
        elif event == "exception":
            exc_type = arg[0]
            line = frame.f_lineno
            key = (frame.f_code.co_name, line, getattr(exc_type, "__name__", "Exception"))
            if last_exception_line[0] != key:
                last_exception_line[0] = key
                message = f"{getattr(exc_type, '__name__', 'Exception')}: {arg[1]}"
                record("exception", frame, message)
        return local_tracer

    def global_tracer(frame, event, arg):
        if frame.f_code.co_filename != FILENAME or frame.f_code.co_name == "<module>":
            return None
        if event == "call":
            if len(steps) >= max_steps:
                limit_reached[0] = True
                return None
            record("call", frame)
            return local_tracer
        return local_tracer

    try:
        with contextlib.redirect_stdout(output):
            exec(compiled, namespace)
            sys.settrace(global_tracer)
            try:
                result = eval(expression, namespace)
            finally:
                sys.settrace(previous_trace)
    except BaseException as error:  # the user's code may raise anything
        trace.error = f"{type(error).__name__}: {error}"
    else:
        trace.result = _short(result, 400)

    trace.steps = steps
    trace.stdout = output.getvalue()
    trace.truncated = limit_reached[0]
    if not steps and trace.error is None:
        trace.error = (
            f"Nothing to step through: `{call}` did not call a function defined in the code. "
            "Define a function and call it, for example fib(5)."
        )
    return trace


def _widgets():
    try:
        import ipywidgets  # noqa: F401
    except ImportError as error:  # pragma: no cover - depends on environment
        raise ImportError(
            "The interactive tutor needs ipywidgets. Install it with "
            '`python -m pip install "recursionlens[tutor]"`.'
        ) from error
    return ipywidgets


_CSS = """
<style>
.rl-tutor{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#242424}
.rl-tutor-bar{display:flex;gap:6px;align-items:center;margin:6px 0}
.rl-tutor-step{font-size:12px;color:#66645f;min-width:190px}
.rl-tutor-code{margin:0;background:#fbfaf6;border:1px solid #e8e5dc;border-radius:10px;padding:10px 6px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px;line-height:1.55;overflow:auto;max-height:340px}
.rl-tutor-code .ln{display:flex;gap:10px;padding:0 8px;border-radius:6px}
.rl-tutor-code .ln.cur{background:#fdf1ec;box-shadow:inset 3px 0 0 #d85a30}
.rl-tutor-code .n{color:#b3b0a6;text-align:right;min-width:22px;user-select:none}
.rl-tutor-code .t{white-space:pre}
.rl-tutor-stack{display:flex;flex-direction:column;gap:8px;max-height:340px;overflow:auto;padding:2px}
.rl-tutor-frame{border:1px solid #e2dfd6;border-radius:10px;padding:10px 12px;background:#fff}
.rl-tutor-frame.cur{border-color:#d85a30;background:#fffaf7}
.rl-tutor-head{font-size:12px;font-weight:600;display:flex;justify-content:space-between;gap:8px}
.rl-tutor-head span{font-weight:400;color:#8a877d}
.rl-tutor-vars{margin-top:6px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;display:grid;grid-template-columns:auto 1fr;gap:2px 12px}
.rl-tutor-vars .k{color:#185fa5}
.rl-tutor-vars .v{color:#3d3b35;word-break:break-all}
.rl-tutor-empty{font-size:12px;color:#8a877d}
.rl-tutor-out{margin-top:8px;background:#f4f2ec;border-radius:8px;padding:8px 10px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;white-space:pre-wrap;color:#3d3b35}
.rl-tutor-error{color:#a32d2d;font-size:12px;margin-top:8px}
</style>
"""


class TutorPlayer:
    """Interactive widget: edit code, change the call, then step through it."""

    def __init__(self, code: str = DEFAULT_CODE, call: str = DEFAULT_CALL) -> None:
        widgets = _widgets()
        self.trace: Optional[TutorTrace] = None

        self.code_area = widgets.Textarea(
            value=code,
            description="",
            layout=widgets.Layout(width="100%", height="190px"),
            continuous_update=False,
        )
        self.call_input = widgets.Text(
            value=call,
            description="Input",
            placeholder="fib(5)",
            layout=widgets.Layout(width="240px"),
        )
        self.run_button = widgets.Button(
            description="Run", button_style="primary", layout=widgets.Layout(width="86px")
        )
        self.first_button = widgets.Button(description="⏮", layout=widgets.Layout(width="44px"))
        self.prev_button = widgets.Button(description="◀", layout=widgets.Layout(width="44px"))
        self.next_button = widgets.Button(description="▶", layout=widgets.Layout(width="44px"))
        self.last_button = widgets.Button(description="⏭", layout=widgets.Layout(width="44px"))
        self.slider = widgets.IntSlider(
            value=0, min=0, max=0, step=1, readout=False,
            layout=widgets.Layout(flex="1 1 auto", min_width="160px"),
        )
        self.status = widgets.HTML(value='<div class="rl-tutor-step">not run yet</div>')
        self.code_html = widgets.HTML()
        self.stack_html = widgets.HTML()
        self.output_html = widgets.HTML()
        self.message = widgets.HTML()

        self.run_button.on_click(self._on_run)
        self.first_button.on_click(lambda _: self.go(0))
        self.prev_button.on_click(lambda _: self.go(self.index - 1))
        self.next_button.on_click(lambda _: self.go(self.index + 1))
        self.last_button.on_click(lambda _: self.go(self.trace.step_count - 1 if self.trace else 0))
        self.slider.observe(self._on_slide, names="value")

        body = widgets.HBox(
            [
                widgets.VBox([self.code_area], layout=widgets.Layout(width="50%")),
                widgets.VBox(
                    [widgets.HTML('<div class="rl-tutor-empty">Step through a run to see the call stack</div>'), self.stack_html],
                    layout=widgets.Layout(width="50%"),
                ),
            ],
            layout=widgets.Layout(width="100%"),
        )
        self.widget = widgets.VBox(
            [
                widgets.HTML(_CSS),
                widgets.HTML('<div class="rl-tutor"><b>RecursionLens tutor</b></div>'),
                self.code_area,
                widgets.HBox([self.call_input, self.run_button]),
                widgets.HBox(
                    [self.first_button, self.prev_button, self.next_button, self.last_button, self.slider]
                ),
                self.status,
                body,
                self.message,
                self.output_html,
            ],
            layout=widgets.Layout(width="100%"),
        )
        self._render_code()
        self._render_stack(None)

    # -- state ---------------------------------------------------------
    @property
    def index(self) -> int:
        return int(self.slider.value)

    def _on_slide(self, change) -> None:
        if self.trace and self.trace.steps:
            self.go(int(change["new"]))

    def _on_run(self, _button=None) -> None:
        self.run()

    def run(self, code: Optional[str] = None, call: Optional[str] = None) -> TutorTrace:
        if code is not None:
            self.code_area.value = code
        if call is not None:
            self.call_input.value = call
        self.trace = record_tutor(self.code_area.value, self.call_input.value)
        self.slider.max = max(0, self.trace.step_count - 1)
        self.slider.value = 0
        self._render_code()
        self._render_step()
        return self.trace

    def go(self, index: int) -> None:
        if not self.trace or not self.trace.steps:
            return
        index = max(0, min(index, self.trace.step_count - 1))
        if int(self.slider.value) != index:
            self.slider.value = index
            return
        self._render_step()

    # -- rendering -----------------------------------------------------
    def _render_code(self) -> None:
        lines = self.code_area.value.splitlines() or [""]
        rows = []
        for number, text in enumerate(lines, start=1):
            escaped = (
                text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                or "&nbsp;"
            )
            rows.append(
                f'<div class="ln" data-line="{number}"><span class="n">{number}</span>'
                f'<span class="t">{escaped}</span></div>'
            )
        self.code_html.value = f'<pre class="rl-tutor-code">{"".join(rows)}</pre>'

    def _render_step(self) -> None:
        if not self.trace or not self.trace.steps:
            self.status.value = '<div class="rl-tutor-step">no steps to show</div>'
            self._render_stack(None)
            self._render_message()
            return
        step = self.trace.step(self.index)
        self.status.value = (
            f'<div class="rl-tutor-step">step {step.index + 1} / {self.trace.step_count} · '
            f"{step.label} · {step.function} · line {step.line}</div>"
        )
        self._render_code_with_highlight(step.line, [frame.line for frame in step.frames])
        self._render_stack(step)
        self._render_message()
        self.output_html.value = (
            f'<pre class="rl-tutor-out">{step.output}</pre>' if step.output.strip() else ""
        )

    def _render_code_with_highlight(self, current: int, stack_lines: List[int]) -> None:
        lines = self.code_area.value.splitlines() or [""]
        rows = []
        for number, text in enumerate(lines, start=1):
            escaped = (
                text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                or "&nbsp;"
            )
            classes = "ln cur" if number == current else "ln"
            rows.append(
                f'<div class="{classes}" data-line="{number}"><span class="n">{number}</span>'
                f'<span class="t">{escaped}</span></div>'
            )
        self.code_html.value = f'<pre class="rl-tutor-code">{"".join(rows)}</pre>'

    def _render_stack(self, step: Optional[TutorStep]) -> None:
        if step is None or not step.frames:
            self.stack_html.value = '<div class="rl-tutor-empty">No active frames</div>'
            return
        cards = []
        for position, frame in enumerate(step.frames):
            current = position == len(step.frames) - 1
            variables = "".join(
                f'<span class="k">{name}</span><span class="v">{value}</span>'
                for name, value in frame.variables.items()
            )
            if not variables:
                variables = '<span class="v">(no locals)</span>'
            badge = "current" if current else f"depth {position + 1}"
            cards.append(
                f'<div class="rl-tutor-frame{" cur" if current else ""}">'
                f'<div class="rl-tutor-head">{frame.function}<span>{badge} · line {frame.line}</span></div>'
                f'<div class="rl-tutor-vars">{variables}</div></div>'
            )
        self.stack_html.value = f'<div class="rl-tutor-stack">{"".join(cards)}</div>'

    def _render_message(self) -> None:
        if not self.trace:
            self.message.value = ""
            return
        parts = []
        if self.trace.result is not None:
            parts.append(f'<div class="rl-tutor-empty">result: {self.trace.result}</div>')
        if self.trace.error:
            parts.append(f'<div class="rl-tutor-error">{self.trace.error}</div>')
        if self.trace.truncated:
            parts.append(
                f'<div class="rl-tutor-error">Recording stopped after {MAX_STEPS} steps; execution continued.</div>'
            )
        self.message.value = "".join(parts)

    def _ipython_display_(self):  # pragma: no cover - notebook only
        from IPython.display import display

        display(self.widget)


def tutor(code: str = DEFAULT_CODE, call: str = DEFAULT_CALL) -> TutorPlayer:
    """Create an interactive step-through player for a recursive function."""

    player = TutorPlayer(code=code, call=call)
    return player
