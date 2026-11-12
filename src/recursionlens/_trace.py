from __future__ import annotations

import contextvars
import functools
import inspect
import itertools
from collections import Counter
from typing import Any, Callable, Dict, List, Optional, Tuple

from ._model import CallNode
from ._report import TraceReport

_ACTIVE: contextvars.ContextVar[Optional["TraceRecorder"]] = contextvars.ContextVar(
    "recursionlens_active_recorder", default=None
)
_FUNCTION_IDS = itertools.count(1)
_MAX_REPR = 160


def full_repr(value: Any) -> str:
    try:
        return repr(value)
    except Exception as error:
        return f"<unrepresentable {type(value).__name__}: {type(error).__name__}>"


def safe_repr(value: Any) -> str:
    """Return a bounded representation suitable for display and JSON."""

    text = full_repr(value)
    if len(text) > _MAX_REPR:
        return text[: _MAX_REPR - 3] + "..."
    return text


def safe_exception(error: BaseException) -> str:
    try:
        message = str(error)
    except BaseException:
        message = "<exception message unavailable>"
    return f"{type(error).__name__}: {message}"


def bind_arguments(func: Callable[..., Any], args: tuple, kwargs: dict) -> inspect.BoundArguments:
    bound = inspect.signature(func).bind(*args, **kwargs)
    bound.apply_defaults()
    return bound


def signature_for(func: Callable[..., Any], bound: inspect.BoundArguments) -> str:
    arguments = ", ".join(
        f"{name}={safe_repr(value)}" for name, value in bound.arguments.items()
    )
    return f"{func.__qualname__}({arguments})"


def identity_for(
    function_id: int, func: Callable[..., Any], bound: inspect.BoundArguments
) -> str:
    """Build an untruncated internal identity independent of display formatting."""

    arguments = ", ".join(
        f"{name}:{type(value).__module__}.{type(value).__qualname__}={full_repr(value)}"
        for name, value in bound.arguments.items()
    )
    return f"{function_id}:{func.__module__}:{func.__qualname__}({arguments})"


def cache_key_for(
    func: Callable[..., Any], bound: inspect.BoundArguments
) -> Optional[Tuple[Any, ...]]:
    # Python considers 1, 1.0, and True equal with equal hashes. Types are part
    # of this key so memoization cannot change a type-sensitive pure function.
    key = (
        func,
        tuple((name, type(value), value) for name, value in bound.arguments.items()),
    )
    try:
        hash(key)
    except Exception:
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
        self.identities: Counter = Counter()
        self.cache: Dict[Tuple[Any, ...], Any] = {}
        self.total_calls = 0
        self.depth = 0
        self.max_depth = 0
        self.truncated = False
        self.warnings: List[str] = []

    def add_node(self, identity: str, signature: str, status: str) -> Optional[CallNode]:
        if len(self.nodes) >= self.max_calls:
            self.truncated = True
            return None

        repeated = self.identities[identity] > 0
        self.identities[identity] += 1
        node = CallNode(
            call_id=len(self.nodes),
            identity=identity,
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
    function_id: int,
    func: Callable[..., Any],
    args: tuple,
    kwargs: dict,
    recorder: TraceRecorder,
) -> Any:
    bound = bind_arguments(func, args, kwargs)
    signature = signature_for(func, bound)
    identity = identity_for(function_id, func, bound)
    cache_key = cache_key_for(func, bound) if recorder.memoize else None

    recorder.total_calls += 1
    recorder.depth += 1
    recorder.max_depth = max(recorder.max_depth, recorder.depth)

    if recorder.memoize and cache_key is not None and cache_key in recorder.cache:
        try:
            value = recorder.cache[cache_key]
            node = recorder.add_node(identity, signature, "cached")
            if node is not None:
                node.result = safe_repr(value)
            return value
        finally:
            recorder.depth -= 1

    node = recorder.add_node(identity, signature, "running")
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
            node.error = safe_exception(error)
        raise
    finally:
        recorder.stack.pop()
        recorder.depth -= 1


class RunConfiguration:
    def __init__(
        self,
        wrapper: Callable[..., Any],
        func: Callable[..., Any],
        function_id: int,
        memoize: bool,
        max_calls: int,
    ) -> None:
        self.wrapper = wrapper
        self.func = func
        self.function_id = function_id
        self.memoize = memoize
        self.max_calls = max_calls

    def run(self, *args: Any, **kwargs: Any) -> TraceReport:
        return _run(
            self.wrapper,
            self.func,
            self.function_id,
            args,
            kwargs,
            self.memoize,
            self.max_calls,
        )


def _run(
    wrapper: Callable[..., Any],
    func: Callable[..., Any],
    function_id: int,
    args: tuple,
    kwargs: dict,
    memoize: bool,
    max_calls: int,
) -> TraceReport:
    recorder = TraceRecorder(memoize=memoize, max_calls=max_calls)
    token = _ACTIVE.set(recorder)
    try:
        value = _invoke(function_id, func, args, kwargs, recorder)
    except BaseException:
        wrapper.last_report = _make_report(func, recorder, None, succeeded=False)
        raise
    else:
        report = _make_report(func, recorder, value, succeeded=True)
        wrapper.last_report = report
        return report
    finally:
        _ACTIVE.reset(token)


def trace(func: Callable[..., Any]) -> Callable[..., Any]:
    """Instrument a synchronous recursive function while preserving its call behavior."""

    function_id = next(_FUNCTION_IDS)

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        active = _ACTIVE.get()
        if active is not None:
            return _invoke(function_id, func, args, kwargs, active)

        recorder = TraceRecorder(memoize=False, max_calls=1000)
        token = _ACTIVE.set(recorder)
        try:
            value = _invoke(function_id, func, args, kwargs, recorder)
        except BaseException:
            wrapper.last_report = _make_report(func, recorder, None, succeeded=False)
            raise
        else:
            wrapper.last_report = _make_report(func, recorder, value, succeeded=True)
            return value
        finally:
            _ACTIVE.reset(token)

    def run(*args: Any, **kwargs: Any) -> TraceReport:
        return RunConfiguration(wrapper, func, function_id, False, 1000).run(*args, **kwargs)

    def with_options(*, memoize: bool = False, max_calls: int = 1000) -> RunConfiguration:
        return RunConfiguration(wrapper, func, function_id, memoize, max_calls)

    wrapper.run = run
    wrapper.with_options = with_options
    wrapper.last_report = None
    wrapper.__recursionlens_original__ = func
    return wrapper


def _make_report(
    func: Callable[..., Any], recorder: TraceRecorder, value: Any, succeeded: bool
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
        succeeded=succeeded,
    )
