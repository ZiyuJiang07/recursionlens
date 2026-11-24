"""Browser bridge: runs inside Pyodide and returns everything the page renders."""

import ast
import contextlib
import html
import io
import json
import sys
import time

import recursionlens
from recursionlens import fit_growth, record_tutor, trace
from recursionlens._doctor import diagnose
from recursionlens._render import render_report

MAX_TUTOR_STEPS = 1500
MAX_JSON_CHARS = 400_000
MAX_GROWTH_SAMPLES = 30
MAX_GROWTH_STEPS = 200_000
MAX_GROWTH_SECONDS = 5


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
                if getattr(target, "has_cache", False):
                    baseline = target.with_options(bypass_cache=True).run(*args, **kwargs)
                    comparison = baseline.compare(
                        report, labels=("no cache", "with cache")
                    )
                else:
                    memoized = target.with_options(memoize=True).run(*args, **kwargs)
                    comparison = report.compare(memoized)
            except BaseException as exc:
                error = html.escape(_message(exc))
                comparison_html = f'<p class="hint">Comparison unavailable: {error}</p>'
            else:
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
        "uses_cache": bool(getattr(target, "has_cache", False)),
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


def suggest_growth_call(call: str) -> str:
    """Replace the first integer argument in a call with the size placeholder."""
    call = (call or "").strip()
    try:
        expression = _parse_call(call)
    except (SyntaxError, ValueError):
        return ""

    for argument in [*expression.args, *(keyword.value for keyword in expression.keywords)]:
        try:
            value = ast.literal_eval(argument)
        except (ValueError, TypeError, SyntaxError):
            continue
        if type(value) is not int:
            continue
        lines = call.encode("utf-8").splitlines(keepends=True)
        start = sum(map(len, lines[:argument.lineno - 1])) + argument.col_offset
        stop = sum(map(len, lines[:argument.end_lineno - 1])) + argument.end_col_offset
        source = call.encode("utf-8")
        return (source[:start] + b"{n}" + source[stop:]).decode("utf-8")
    return ""


@contextlib.contextmanager
def _growth_limit():
    """Bound a measurement and restore any previously installed Python trace."""
    previous = sys.gettrace()
    deadline = time.monotonic() + MAX_GROWTH_SECONDS
    steps = 0

    def check(frame, event, arg):
        nonlocal steps
        if frame.f_code.co_filename != "<web>":
            return check
        steps += 1
        if steps > MAX_GROWTH_STEPS or time.monotonic() > deadline:
            raise RuntimeError("Growth measurement limit reached. Choose smaller inputs or fewer samples.")
        return check

    sys.settrace(check)
    try:
        yield
    finally:
        sys.settrace(previous)


def growth_payload(code: str, call_template: str, start: int, stop: int, step: int = 1) -> str:
    """Measure the supplied code at each size in the inclusive input range."""
    call = None
    try:
        if any(type(value) is not int for value in (start, stop, step)):
            raise ValueError("The input range and step must be integers.")
        if start < 0 or start > stop or step < 1:
            raise ValueError("Use a non-negative range with start <= stop and a positive step.")
        if (stop - start) // step + 1 > MAX_GROWTH_SAMPLES:
            raise ValueError(f"Measure at most {MAX_GROWTH_SAMPLES} input sizes at once.")
        if "{n}" not in call_template:
            raise ValueError("Put {n} in the call template where the input size should change.")
        compiled = compile(code, "<web>", "exec")
        samples = []
        with contextlib.redirect_stdout(io.StringIO()), _growth_limit():
            for size in range(start, stop + 1, step):
                call = call_template.replace("{n}", str(size))
                expression = _parse_call(call)
                # The chart needs run-wide counts, so only the root call is stored.
                target, args, kwargs = _prepare_call(compiled, expression)
                if getattr(target, "has_cache", False):
                    if hasattr(target, "cache_clear"):
                        target.cache_clear()
                    memoized = target.with_options(max_calls=1).run(*args, **kwargs)
                    target, args, kwargs = _prepare_call(compiled, expression)
                    naive = target.with_options(
                        bypass_cache=True, max_calls=1
                    ).run(*args, **kwargs)
                else:
                    naive = target.with_options(max_calls=1).run(*args, **kwargs)
                    target, args, kwargs = _prepare_call(compiled, expression)
                    memoized = target.with_options(memoize=True, max_calls=1).run(
                        *args, **kwargs
                    )
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
        fit = None
        memoized_fit = None
        if len(samples) >= 3:
            try:
                fit = fit_growth(
                    [sample["size"] for sample in samples],
                    [sample["naive"] for sample in samples],
                ).to_dict()
                memoized_fit = fit_growth(
                    [sample["size"] for sample in samples],
                    [sample["memoized"] for sample in samples],
                ).to_dict()
            except ValueError:
                fit = None
        return json.dumps({"samples": samples, "fit": fit, "memoized_fit": memoized_fit}, ensure_ascii=False)
    except BaseException as exc:  # noqa: BLE001 - show the failure in the playground
        return json.dumps({"error": _message(exc), "failed_call": call}, ensure_ascii=False)
