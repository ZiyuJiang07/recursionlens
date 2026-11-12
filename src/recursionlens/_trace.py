from __future__ import annotations

import contextvars
import functools
import inspect
from collections import Counter
from typing import Any, Callable, Dict, List, Optional, Tuple

from ._model import CallNode
from ._report import TraceReport

_ACTIVE: contextvars.ContextVar[Optional["TraceRecorder"]] = contextvars.ContextVar(
    "recursionlens_active_recorder", default=None
)
_MAX_REPR = 160


def safe_repr(value: Any) -> str:
    """Return a bounded representation suitable for display and JSON."""

    try:
        text = repr(value)
    except Exception as error:
        text = f"<unrepresentable {type(value).__name__}: {type(error).__name__}>"
    if len(text) > _MAX_REPR:
        return text[: _MAX_REPR - 3] + "..."
    return text


def bind_arguments(func: Callable[..., Any], args: tuple, kwargs: dict) -> inspect.BoundArguments:
    bound = inspect.signature(func).bind(*args, **kwargs)
    bound.apply_defaults()
    return bound


def signature_for(func: Callable[..., Any], bound: inspect.BoundArguments) -> str:
    arguments = ", ".join(
        f"{name}={safe_repr(value)}" for name, value in bound.arguments.items()
    )
    return f"{func.__qualname__}({arguments})"


def cache_key_for(
    func: Callable[..., Any], bound: inspect.BoundArguments
) -> Optional[Tuple[Any, ...]]:
    key = (func, tuple(bound.arguments.items()))
    try:
        hash(key)
    except (TypeError, ValueError):
        return None
    return key


class TraceRecorder:
    def __init__(self, memoize: bool, max_calls: int) -> None:
        if max_calls < 1:
            raise ValueError("max_calls must be at least 1")
        self.memoize = memoize
        self.max_calls = max_calls
        self.nodes: List[CallNode] = []
        self.roots: List[CallNode] = []
        self.stack: List[Optional[CallNode]] = []
        self.signatures: Counter = Counter()
        self.cache: Dict[Tuple[Any, ...], Any] = {}
        self.total_calls = 0
        self.depth = 0
        self.max_depth = 0
        self.truncated = False
        self.warnings: List[str] = []

    def add_node(self, signature: str, status: str) -> Optional[CallNode]:
        if len(self.nodes) >= self.max_calls:
            self.truncated = True
            return None

        repeated = self.signatures[signature] > 0
        self.signatures[signature] += 1
        node = CallNode(
            call_id=len(self.nodes),
            signature=signature,
            depth=self.depth,
            status=status,
            repeated=repeated,
        )
        self.nodes.append(node)

        if not self.stack:
            self.roots.append(node)
        elif self.stack[-1] is not None:
            self.stack[-1].children.append(node)
        return node

    def warn_unhashable(self) -> None:
        message = "Arguments are unhashable; this run was not memoized for those calls."
        if message not in self.warnings:
            self.warnings.append(message)


def _invoke(
    func: Callable[..., Any],
    args: tuple,
    kwargs: dict,
    recorder: TraceRecorder,
) -> Any:
    bound = bind_arguments(func, args, kwargs)
    signature = signature_for(func, bound)
    cache_key = cache_key_for(func, bound) if recorder.memoize else None

    recorder.total_calls += 1
    recorder.depth += 1
    recorder.max_depth = max(recorder.max_depth, recorder.depth)

    if recorder.memoize and cache_key is not None and cache_key in recorder.cache:
        try:
            value = recorder.cache[cache_key]
            node = recorder.add_node(signature, "cached")
            if node is not None:
                node.result = safe_repr(value)
            return value
        finally:
            recorder.depth -= 1

    node = recorder.add_node(signature, "running")
    recorder.stack.append(node)
    try:
        value = func(*args, **kwargs)
        if node is not None:
            node.status = "returned"
            node.result = safe_repr(value)

        if recorder.memoize:
            if cache_key is None:
                recorder.warn_unhashable()
            else:
                recorder.cache[cache_key] = value
        return value
    except BaseException as error:
        if node is not None:
            node.status = "error"
            node.error = f"{type(error).__name__}: {error}"
        raise
    finally:
        recorder.stack.pop()
        recorder.depth -= 1


def trace(func: Callable[..., Any]) -> Callable[..., Any]:
    """Instrument a synchronous recursive function while preserving its call behavior."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        active = _ACTIVE.get()
        if active is not None:
            return _invoke(func, args, kwargs, active)

        recorder = TraceRecorder(memoize=False, max_calls=1000)
        token = _ACTIVE.set(recorder)
        try:
            value = _invoke(func, args, kwargs, recorder)
        except BaseException:
            wrapper.last_report = _make_report(func, recorder, None)
            raise
        else:
            wrapper.last_report = _make_report(func, recorder, value)
            return value
        finally:
            _ACTIVE.reset(token)

    def run(*args: Any, memoize: bool = False, max_calls: int = 1000, **kwargs: Any) -> TraceReport:
        recorder = TraceRecorder(memoize=memoize, max_calls=max_calls)
        token = _ACTIVE.set(recorder)
        try:
            value = _invoke(func, args, kwargs, recorder)
        except BaseException:
            wrapper.last_report = _make_report(func, recorder, None)
            raise
        else:
            report = _make_report(func, recorder, value)
            wrapper.last_report = report
            return report
        finally:
            _ACTIVE.reset(token)

    wrapper.run = run
    wrapper.last_report = None
    wrapper.__recursionlens_original__ = func
    return wrapper


def _make_report(
    func: Callable[..., Any], recorder: TraceRecorder, value: Any
) -> TraceReport:
    return TraceReport(
        function_name=func.__qualname__,
        value=value,
        nodes=recorder.nodes,
        roots=recorder.roots,
        total_calls=recorder.total_calls,
        max_depth=recorder.max_depth,
        memoize=recorder.memoize,
        truncated=recorder.truncated,
        warnings=list(recorder.warnings),
    )
