"""Tracing infrastructure for RecursionLens.

This module provides the :func:`trace` decorator, the :class:`TraceRecorder`
that collects call-tree data at runtime, and :class:`RunConfiguration` for
configuring memoized or size-limited runs.

The decorator wraps a synchronous recursive function so that every invocation
— including cache-only hits — is recorded as a :class:`~recursionlens._model.CallNode`.
When the wrapped function is called normally, it returns the original value and
stores a :class:`~recursionlens._report.TraceReport` on ``wrapper.last_report``.
When ``wrapper.run(...)`` is called instead, it returns the report directly.

Module boundaries: this is the only module that executes user code. It imports
from :mod:`recursionlens._model` and :mod:`recursionlens._report` but not from
:mod:`recursionlens._render` or :mod:`recursionlens._doctor`.
"""

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
    """Return the full ``repr(value)`` without truncation.

    If ``repr()`` itself raises (for example, a broken ``__repr__``),
    a placeholder string is returned instead of propagating the exception.
    """
    try:
        return repr(value)
    except Exception as error:
        return f"<unrepresentable {type(value).__name__}: {type(error).__name__}>"


def safe_repr(value: Any) -> str:
    """Return a bounded representation suitable for display and JSON.

    The result is at most ``_MAX_REPR`` characters long. Values exceeding the
    limit are truncated with an ellipsis.
    """

    text = full_repr(value)
    if len(text) > _MAX_REPR:
        return text[: _MAX_REPR - 3] + "..."
    return text


def safe_exception(error: BaseException) -> str:
    """Format an exception as ``"TypeName: message"`` without raising.

    Some exception classes raise inside ``__str__``; this function catches
    that and falls back to a placeholder message.
    """
    try:
        message = str(error)
    except BaseException:
        message = "<exception message unavailable>"
    return f"{type(error).__name__}: {message}"


def bind_arguments(func: Callable[..., Any], args: tuple, kwargs: dict) -> inspect.BoundArguments:
    """Bind ``args`` and ``kwargs`` to ``func``'s signature, applying defaults.

    This normalizes positional/keyword/mixed calls so that the same logical
    invocation always produces the same bound arguments, regardless of how
    the caller passed them.
    """
    bound = inspect.signature(func).bind(*args, **kwargs)
    bound.apply_defaults()
    return bound


def signature_for(func: Callable[..., Any], bound: inspect.BoundArguments) -> str:
    """Build a human-readable call signature from bound arguments.

    Example: ``fib(n=5)``
    """
    arguments = ", ".join(
        f"{name}={safe_repr(value)}" for name, value in bound.arguments.items()
    )
    return f"{func.__qualname__}({arguments})"


def identity_for(
    function_id: int, func: Callable[..., Any], bound: inspect.BoundArguments
) -> str:
    """Build an untruncated internal identity independent of display formatting.

    The identity includes the function ID, module, qualified name, and the
    *type* and *value* of each argument. This ensures that two calls with
    equal-but-different-typed arguments (e.g. ``1`` and ``1.0``) are treated
    as distinct subproblems, which is critical for correct memoization of
    type-sensitive pure functions.
    """

    arguments = ", ".join(
        f"{name}:{type(value).__module__}.{type(value).__qualname__}={full_repr(value)}"
        for name, value in bound.arguments.items()
    )
    return f"{function_id}:{func.__module__}:{func.__qualname__}({arguments})"


def cache_key_for(
    func: Callable[..., Any], bound: inspect.BoundArguments
) -> Optional[Tuple[Any, ...]]:
    """Build a hashable cache key for memoization, or ``None`` if unhashable.

    The key includes the function object, the parameter name, the argument
    *type*, and the argument *value* for every bound argument. Including the
    type prevents ``1``, ``1.0``, and ``True`` from sharing a cache entry,
    which matters for functions whose results depend on argument type.

    Returns ``None`` when any argument is unhashable (e.g. a list), so the
    caller can emit a warning instead of crashing.
    """
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
    """Collects call-tree data during a single traced top-level invocation.

    The recorder is set as the active recorder via a :class:`contextvars.ContextVar`
    so that recursive calls inside the traced function can find it without it
    being passed as an argument.

    Attributes:
        memoize: Whether memoization is enabled for this run.
        max_calls: Maximum number of call nodes to store.
        nodes: All recorded :class:`CallNode` objects in creation order.
        roots: Top-level call nodes (those with no parent).
        stack: Current call stack (``None`` entries appear when a node was
            truncated and could not be stored).
        identities: Counter of how many times each identity has been seen.
        cache: Memoization cache mapping cache keys to return values.
        total_calls: Total observed calls (including truncated ones).
        executed_calls: Calls where the function body actually ran.
        cached_calls: Calls served from a cache without running the body,
            either a ``functools.lru_cache`` hit in the code or RecursionLens
            memoization when it is enabled.
        depth: Current recursion depth.
        max_depth: Maximum depth reached during this run.
        truncated: Whether the ``max_calls`` limit was reached.
        warnings: Human-readable warning messages for this run.
    """

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
        self.executed_calls = 0
        self.cached_calls = 0
        self.depth = 0
        self.max_depth = 0
        self.truncated = False
        self.warnings: List[str] = []

    def add_node(self, identity: str, signature: str, status: str) -> Optional[CallNode]:
        """Create and store a new :class:`CallNode`, or return ``None`` if truncated.

        When the ``max_calls`` limit is reached, ``self.truncated`` is set to
        ``True`` and ``None`` is returned. The caller still increments
        ``total_calls`` and ``depth``, so run-wide totals remain accurate.
        """
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
        """Add the unhashable-arguments warning, deduplicated."""
        message = "Arguments are unhashable; this run was not memoized for those calls."
        if message not in self.warnings:
            self.warnings.append(message)


def cache_hits(func: Callable[..., Any]) -> Optional[int]:
    """Return the hit counter of a ``functools.lru_cache`` (or ``cache``) wrapper.

    Returns ``None`` for plain functions, so callers can tell "not cached"
    apart from "cached, zero hits so far".
    """
    info = getattr(func, "cache_info", None)
    if not callable(info):
        return None
    try:
        return int(info().hits)
    except Exception:  # pragma: no cover - defensive for exotic wrappers
        return None


def _invoke(
    function_id: int,
    func: Callable[..., Any],
    args: tuple,
    kwargs: dict,
    recorder: TraceRecorder,
) -> Any:
    """Execute one invocation of ``func``, recording it in ``recorder``.

    This function handles three paths:
    1. **Cache hit**: either the caller's ``functools.lru_cache`` served the
       call, detected from ``cache_info().hits`` growing by exactly one while
       no nested call happened, or RecursionLens' own memoization already has
       the key. Either way the function body does not run.
    2. **Normal execution**: the function body runs, the result is stored in
       the cache (if memoization is enabled), and the node is marked "returned".
    3. **Exception**: the node is marked "error" and the exception is re-raised.

    In all cases, ``depth`` is decremented in a ``finally`` block.
    """
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
            recorder.cached_calls += 1
            node = recorder.add_node(identity, signature, "cached")
            if node is not None:
                node.result = safe_repr(value)
            return value
        finally:
            recorder.depth -= 1

    hits_before = cache_hits(func)
    calls_before = recorder.total_calls
    node = recorder.add_node(identity, signature, "running")
    recorder.stack.append(node)
    try:
        value = func(*args, **kwargs)
        hits_after = cache_hits(func)
        served_from_cache = (
            hits_before is not None
            and hits_after is not None
            and hits_after - hits_before == 1
            and recorder.total_calls == calls_before
        )
        if node is not None:
            node.status = "cached" if served_from_cache else "returned"
            node.result = safe_repr(value)
        if served_from_cache:
            recorder.cached_calls += 1
        else:
            recorder.executed_calls += 1

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
    """A deferred run with specific options (memoize, max_calls).

    Created by :meth:`trace_wrapper.with_options`. Calling ``.run(*args)``
    executes the traced function and returns a :class:`TraceReport`.
    """

    def __init__(
        self,
        wrapper: Callable[..., Any],
        func: Callable[..., Any],
        function_id: int,
        memoize: bool,
        max_calls: int,
        bypass_cache: bool = False,
    ) -> None:
        self.wrapper = wrapper
        self.func = func
        self.function_id = function_id
        self.memoize = memoize
        self.max_calls = max_calls
        self.bypass_cache = bypass_cache

    def run(self, *args: Any, **kwargs: Any) -> TraceReport:
        """Execute the traced function with the configured options and return a report."""
        return _run(
            self.wrapper,
            self.func,
            self.function_id,
            args,
            kwargs,
            self.memoize,
            self.max_calls,
            self.bypass_cache,
        )


def _run(
    wrapper: Callable[..., Any],
    func: Callable[..., Any],
    function_id: int,
    args: tuple,
    kwargs: dict,
    memoize: bool,
    max_calls: int,
    bypass_cache: bool = False,
) -> TraceReport:
    """Set up a fresh :class:`TraceRecorder`, invoke the function, and build a report.

    The recorder is activated via a context variable so that recursive calls
    inside ``func`` find it automatically. If the function raises, a report
    is still created (with ``succeeded=False``) before the exception propagates.
    """
    target, restore = _bypass_cache(func, function_id) if bypass_cache else (func, None)
    recorder = TraceRecorder(memoize=memoize, max_calls=max_calls)
    token = _ACTIVE.set(recorder)
    try:
        value = _invoke(function_id, target, args, kwargs, recorder)
    except BaseException:
        wrapper.last_report = _make_report(func, recorder, None, succeeded=False)
        raise
    else:
        report = _make_report(func, recorder, value, succeeded=True)
        wrapper.last_report = report
        return report
    finally:
        _ACTIVE.reset(token)
        if restore is not None:
            restore()


def _bypass_cache(
    func: Callable[..., Any], function_id: int
) -> Tuple[Callable[..., Any], Optional[Callable[[], None]]]:
    """Return an uncached target for ``func`` and a callback that restores it.

    ``functools.lru_cache`` keeps the original function in ``__wrapped__``, but
    recursive calls inside the body still resolve the *global* name, which points
    at the traced cache wrapper. Rebinding that name for the duration of the run
    makes the body call an uncached traced entry point instead, so the comparison
    measures the algorithm without the cache.
    """

    if not callable(getattr(func, "cache_info", None)):
        return func, None
    uncached = getattr(func, "__wrapped__", None)
    if uncached is None:
        return func, None

    name = getattr(uncached, "__name__", None)
    if name is None:
        return uncached, None

    def entry(*args: Any, **kwargs: Any) -> Any:
        active = _ACTIVE.get()
        if active is None:
            return uncached(*args, **kwargs)
        return _invoke(function_id, uncached, args, kwargs, active)

    # Module-level functions resolve the recursive name through their globals.
    namespace = getattr(uncached, "__globals__", None)
    if namespace is not None and name in namespace:
        previous = namespace[name]
        namespace[name] = entry

        def restore_global() -> None:
            namespace[name] = previous

        return uncached, restore_global

    # Nested functions resolve it through a closure cell instead.
    code = getattr(uncached, "__code__", None)
    closure = getattr(uncached, "__closure__", None)
    if code is not None and closure and name in code.co_freevars:
        cell = closure[code.co_freevars.index(name)]
        try:
            previous_cell = cell.cell_contents
            cell.cell_contents = entry
        except (AttributeError, ValueError):
            return uncached, None

        def restore_cell() -> None:
            cell.cell_contents = previous_cell

        return uncached, restore_cell

    return uncached, None


def trace(func: Callable[..., Any]) -> Callable[..., Any]:
    """Instrument a synchronous recursive function while preserving its call behavior.

    The returned wrapper behaves identically to ``func`` when called normally:
    it returns the same value and raises the same exceptions. The difference is
    that every invocation is recorded, and the wrapper gains three attributes:

    - ``run(*args, **kwargs)``: call the function and return a
      :class:`~recursionlens._report.TraceReport` instead of the raw value.
    - ``with_options(*, memoize=False, max_calls=1000)``: return a
      :class:`RunConfiguration` for a customized run.
    - ``last_report``: the :class:`~recursionlens._report.TraceReport` from the
      most recent call (whether normal or via ``run``).

    Example::

        @trace
        def fib(n):
            if n < 2:
                return n
            return fib(n - 1) + fib(n - 2)

        assert fib(5) == 5           # normal call
        report = fib.run(5)          # traced call → TraceReport
    """

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
        """Run the traced function and return a :class:`TraceReport`."""
        return RunConfiguration(wrapper, func, function_id, False, 1000).run(*args, **kwargs)

    def with_options(
        *,
        memoize: bool = False,
        max_calls: int = 1000,
        bypass_cache: bool = False,
    ) -> RunConfiguration:
        """Return a :class:`RunConfiguration` with the given options."""
        return RunConfiguration(wrapper, func, function_id, memoize, max_calls, bypass_cache)

    wrapper.run = run
    wrapper.with_options = with_options
    wrapper.last_report = None
    wrapper.has_cache = callable(getattr(func, "cache_info", None))
    if wrapper.has_cache:
        wrapper.cache_info = func.cache_info
        wrapper.cache_clear = func.cache_clear
    wrapper.__recursionlens_original__ = func
    return wrapper


def _make_report(
    func: Callable[..., Any], recorder: TraceRecorder, value: Any, succeeded: bool
) -> TraceReport:
    """Build a :class:`TraceReport` from the recorder's collected data."""
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
        _executed_calls=recorder.executed_calls,
        _cached_calls=recorder.cached_calls,
    )
