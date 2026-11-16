"""Browser bridge: runs inside Pyodide and returns everything the page renders."""

import ast
import contextlib
import html
import io
import json

import recursionlens
from recursionlens import record_tutor, trace
from recursionlens._doctor import diagnose
from recursionlens._render import render_report

MAX_TUTOR_STEPS = 1500
MAX_JSON_CHARS = 400_000


def _message(exc: BaseException) -> str:
    if isinstance(exc, SyntaxError):
        where = f" (line {exc.lineno})" if getattr(exc, "lineno", None) else ""
        return f"SyntaxError: {exc.msg}{where}"
    return f"{type(exc).__name__}: {exc}"


def _parse_call(call: str) -> ast.Call:
    call = (call or "").strip()
    if not call:
        raise ValueError("Enter a call such as fib(5).")

    expression = ast.parse(call, mode="eval").body
    if not isinstance(expression, ast.Call):
        raise ValueError("Enter a function call, for example fib(5).")
    if not isinstance(expression.func, ast.Name):
        raise ValueError("Call a function defined in the code, for example fib(5).")
    return expression


def _prepare_call(code, expression):
    namespace = {"__name__": "__main__"}
    exec(code, namespace)
    name = expression.func.id

    originals = {
        key: value
        for key, value in list(namespace.items())
        if callable(value) and getattr(value, "__module__", None) == "__main__"
    }
    for key, function in originals.items():
        namespace[key] = trace(function)

    def evaluate(node):
        return eval(compile(ast.Expression(node), "<web>", "eval"), namespace)

    args = [evaluate(node) for node in expression.args]
    kwargs = {kw.arg: evaluate(kw.value) for kw in expression.keywords if kw.arg}

    target = namespace.get(name)
    if target is None or not hasattr(target, "run"):
        raise ValueError(f"{name} is not a function defined in the code.")
    return target, args, kwargs


def _run(code: str, call: str) -> dict:
    expression = _parse_call(call)
    compiled = compile(code, "<web>", "exec")

    run_error = None
    comparison_metrics = None
    with contextlib.redirect_stdout(io.StringIO()):
        target, args, kwargs = _prepare_call(compiled, expression)
        try:
            report = target.run(*args, **kwargs)
        except BaseException as exc:
            report = target.last_report
            if report is None or not report.roots:
                raise
            run_error = _message(exc)

        if run_error:
            comparison_html = '<p class="hint">Comparison unavailable because this run raised an error.</p>'
        else:
            try:
                target, args, kwargs = _prepare_call(compiled, expression)
                memoized = target.with_options(memoize=True).run(*args, **kwargs)
            except BaseException as exc:
                error = html.escape(_message(exc))
                comparison_html = f'<p class="hint">Comparison unavailable: {error}</p>'
            else:
                comparison = report.compare(memoized)
                comparison_html = comparison.to_html()
                comparison_metrics = comparison.to_dict()

    tutor = record_tutor(code, call)
    steps = []
    for step in tutor.steps[:MAX_TUTOR_STEPS]:
        output = step.output if len(step.output) <= 600 and step.output.strip() else ""
        steps.append(
            {
                "event": step.event,
                "line": step.line,
                "value": step.value,
                "output": output,
                "frames": [
                    {
                        "function": frame.function,
                        "line": frame.line,
                        "variables": frame.variables,
                    }
                    for frame in step.frames
                ],
            }
        )

    serialized = report.to_dict()
    payload = {
        "views": {
            "tree": render_report(report, interactive=True),
            "expanded": render_report(report, mode="expanded", interactive=True),
            "dag": render_report(report, mode="dag", interactive=True),
            "compare": comparison_html,
        },
        "comparison": comparison_metrics,
        "metrics": report.metrics(),
        "result": report.result,
        "run_error": run_error,
        "trace": {"roots": serialized["roots"], "dag": serialized["dag"]},
        "doctor": diagnose(report),
        "tutor": {
            "steps": steps,
            "truncated": tutor.step_count > MAX_TUTOR_STEPS or tutor.truncated,
            "error": tutor.error,
            "result": tutor.result,
            "stdout": tutor.stdout[-4000:],
        },
        "version": recursionlens.__version__,
        "json": None,
    }

    try:
        dumped = json.dumps(serialized, indent=2, ensure_ascii=False)
        payload["json"] = dumped if len(dumped) <= MAX_JSON_CHARS else None
    except (TypeError, ValueError):
        payload["json"] = None

    return payload


def run_payload(code: str, call: str) -> str:
    """Entry point called from JavaScript; always returns JSON text."""

    try:
        return json.dumps(_run(code, call), ensure_ascii=False)
    except BaseException as exc:  # noqa: BLE001 - the page shows whatever went wrong
        return json.dumps({"error": _message(exc)}, ensure_ascii=False)


def growth_payload(code: str, call_template: str, start: int, stop: int) -> str:
    """Measure executed bodies across the preset sizes of a built-in example."""
    try:
        if start > stop:
            raise ValueError("The growth measurement needs at least one input.")
        compiled = compile(code, "<web>", "exec")
        samples = []
        with contextlib.redirect_stdout(io.StringIO()):
            for size in range(start, stop + 1):
                call = call_template.format(n=size)
                expression = _parse_call(call)
                # The chart needs run-wide counts, so only the root call is stored.
                target, args, kwargs = _prepare_call(compiled, expression)
                naive = target.with_options(max_calls=1).run(*args, **kwargs)
                target, args, kwargs = _prepare_call(compiled, expression)
                memoized = target.with_options(memoize=True, max_calls=1).run(*args, **kwargs)
                if not naive.compare(memoized).same_result:
                    raise ValueError(f"The runs returned different results for {call}.")
                samples.append(
                    {
                        "size": size,
                        "call": call,
                        "naive": naive.executed_calls,
                        "memoized": memoized.executed_calls,
                    }
                )
        return json.dumps({"samples": samples}, ensure_ascii=False)
    except BaseException as exc:  # noqa: BLE001 - show the failure in the playground
        return json.dumps({"error": _message(exc)}, ensure_ascii=False)
