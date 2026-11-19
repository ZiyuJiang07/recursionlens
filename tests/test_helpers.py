"""Unit tests for internal helper functions in :mod:`recursionlens._trace`.

These tests exercise the utility functions (``safe_repr``, ``full_repr``,
``safe_exception``, ``bind_arguments``, ``cache_key_for``, etc.) directly,
without relying on the ``trace`` decorator.
"""

import inspect

import pytest

from recursionlens._trace import (
    TraceRecorder,
    bind_arguments,
    cache_key_for,
    full_repr,
    identity_for,
    safe_exception,
    safe_repr,
    signature_for,
)


# -- full_repr / safe_repr ----------------------------------------------------

def test_full_repr_returns_standard_repr():
    assert full_repr(42) == "42"
    assert full_repr("hello") == "'hello'"
    assert full_repr([1, 2]) == "[1, 2]"


def test_full_repr_handles_broken_repr():
    class BrokenRepr:
        def __repr__(self):
            raise RuntimeError("boom")

    result = full_repr(BrokenRepr())
    assert "unrepresentable" in result
    assert "BrokenRepr" in result


def test_safe_repr_truncates_long_values():
    long_string = "x" * 300
    result = safe_repr(long_string)
    assert len(result) <= 160
    assert result.endswith("...")


def test_safe_repr_preserves_short_values():
    assert safe_repr(42) == "42"
    assert safe_repr("hi") == "'hi'"


def test_safe_repr_handles_broken_repr():
    class Bad:
        def __repr__(self):
            raise ValueError("nope")

    result = safe_repr(Bad())
    assert "unrepresentable" in result


# -- safe_exception -----------------------------------------------------------

def test_safe_exception_formats_type_and_message():
    error = ValueError("bad value")
    result = safe_exception(error)
    assert result == "ValueError: bad value"


def test_safe_exception_handles_broken_str():
    class BadError(Exception):
        def __str__(self):
            raise RuntimeError("formatting failed")

    result = safe_exception(BadError("original"))
    assert "BadError" in result
    assert "message unavailable" in result


# -- bind_arguments ------------------------------------------------------------

def test_bind_arguments_positional():
    def func(a, b):
        return a + b

    bound = bind_arguments(func, (1, 2), {})
    assert bound.arguments == {"a": 1, "b": 2}


def test_bind_arguments_keyword():
    def func(a, b):
        return a + b

    bound = bind_arguments(func, (), {"a": 1, "b": 2})
    assert bound.arguments == {"a": 1, "b": 2}


def test_bind_arguments_applies_defaults():
    def func(a, b=10):
        return a + b

    bound = bind_arguments(func, (1,), {})
    assert bound.arguments == {"a": 1, "b": 10}


def test_bind_arguments_mixed():
    def func(a, b, c=3):
        return a + b + c

    bound = bind_arguments(func, (1,), {"b": 2})
    assert bound.arguments == {"a": 1, "b": 2, "c": 3}


# -- signature_for -------------------------------------------------------------

def test_signature_for_formats_arguments():
    def func(a, b):
        return a + b

    bound = bind_arguments(func, (1, "x"), {})
    sig = signature_for(func, bound)
    # __qualname__ includes the enclosing scope for local functions
    assert sig.endswith("func(a=1, b='x')")


# -- identity_for --------------------------------------------------------------

def test_identity_for_includes_function_id_and_types():
    def func(n):
        return n

    bound = bind_arguments(func, (1,), {})
    ident = identity_for(42, func, bound)
    assert ident.startswith("42:")
    assert "func" in ident
    assert "int" in ident  # type of 1 is int


def test_identity_for_distinguishes_int_and_float():
    def func(n):
        return n

    bound_int = bind_arguments(func, (1,), {})
    bound_float = bind_arguments(func, (1.0,), {})
    ident_int = identity_for(1, func, bound_int)
    ident_float = identity_for(1, func, bound_float)
    assert ident_int != ident_float


# -- cache_key_for -------------------------------------------------------------

def test_cache_key_for_returns_hashable_key():
    def func(n):
        return n

    bound = bind_arguments(func, (5,), {})
    key = cache_key_for(func, bound)
    assert key is not None
    hash(key)  # should not raise


def test_cache_key_for_returns_none_for_unhashable():
    def func(items):
        return len(items)

    bound = bind_arguments(func, ([1, 2],), {})
    key = cache_key_for(func, bound)
    assert key is None


def test_cache_key_for_distinguishes_equal_values_with_different_types():
    def func(n):
        return n

    bound_int = bind_arguments(func, (1,), {})
    bound_float = bind_arguments(func, (1.0,), {})
    key_int = cache_key_for(func, bound_int)
    key_float = cache_key_for(func, bound_float)
    assert key_int != key_float


def test_cache_key_for_distinguishes_true_and_one():
    def func(n):
        return n

    bound_true = bind_arguments(func, (True,), {})
    bound_one = bind_arguments(func, (1,), {})
    key_true = cache_key_for(func, bound_true)
    key_one = cache_key_for(func, bound_one)
    assert key_true != key_one


# -- TraceRecorder -------------------------------------------------------------

def test_trace_recorder_rejects_zero_max_calls():
    with pytest.raises(ValueError, match="max_calls"):
        TraceRecorder(memoize=False, max_calls=0)


def test_trace_recorder_rejects_negative_max_calls():
    with pytest.raises(ValueError, match="max_calls"):
        TraceRecorder(memoize=False, max_calls=-1)


def test_trace_recorder_warn_unhashable_is_deduplicated():
    recorder = TraceRecorder(memoize=True, max_calls=10)
    recorder.warn_unhashable()
    recorder.warn_unhashable()
    assert len(recorder.warnings) == 1
