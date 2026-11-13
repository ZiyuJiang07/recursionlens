"""Browser bridge: runs inside Pyodide and returns everything the page renders."""

import ast
import json

import recursionlens
from recursionlens import record_tutor, trace

MAX_TUTOR_STEPS = 1500
MAX_JSON_CHARS = 400_000


def _message(exc: BaseException) -> str:
    if isinstance(exc, SyntaxError):
        where = f" (line {exc.lineno})" if getattr(exc, "lineno", None) else ""
        return f"SyntaxError: {exc.msg}{where}"
    return f"{type(exc).__name__}: {exc}"


def _run(code: str, call: str) -> dict:
    call = (call or "").strip()
    if not call:
        raise ValueError("Enter a call such as fib(5).")

    namespace = {"__name__": "__main__"}
    exec(compile(code, "<web>", "exec"), namespace)

    expression = ast.parse(call, mode="eval").body
    if not isinstance(expression, ast.Call):
        raise ValueError("Enter a function call, for example fib(5).")
    if not isinstance(expression.func, ast.Name):
        raise ValueError("Call a function defined in the code, for example fib(5).")
    name = expression.func.id

    originals = {
        key: value
        for key, value in list(namespace.items())
        if callable(value)
        and not key.startswith("_")
        and getattr(value, "__module__", None) == "__main__"
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

    report = target.run(*args, **kwargs)
    memoized = target.with_options(memoize=True).run(*args, **kwargs)
    comparison = report.compare(memoized)

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

    payload = {
        "views": {
            "tree": report.to_html(),
            "expanded": report.to_html(mode="expanded"),
            "dag": report.to_html(mode="dag"),
            "compare": comparison.to_html(),
        },
        "metrics": report.metrics(),
        "result": report.result,
        "error": report.error,
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
        dumped = json.dumps(report.to_dict(), indent=2, ensure_ascii=False)
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
