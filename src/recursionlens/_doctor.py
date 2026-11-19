"""Recursion Doctor: automatic pattern detection for traced runs.

This module analyzes a :class:`~recursionlens._report.TraceReport` and produces
a list of :class:`Finding` dictionaries, each describing a pattern observed in
the recorded call tree. The findings are purely observational — the doctor does
not execute user code or modify the trace.

Supported finding kinds:

- ``repeated_subproblem``: the same subproblem was executed in separate branches
  of the call tree. This is the classic memoization opportunity signal.
- ``active_path_reentry``: a subproblem was entered while a call to the same
  subproblem was still on the stack. This may indicate a missing or incorrect
  base case.
- ``failed_call``: the run raised an exception. The finding links to the deepest
  recorded call on the error path.
- ``partial_trace``: the recording was truncated, so other patterns may exist
  outside the recorded calls.

Module boundaries: imports from :mod:`recursionlens._model` and
:mod:`recursionlens._report`. Does not execute user code.
"""

from __future__ import annotations

from collections import Counter
from typing import Literal, Optional, TypedDict, Union

from ._model import CallNode
from ._report import TraceReport


class Finding(TypedDict):
    """One diagnostic observation produced by :func:`diagnose`.

    Fields:
        kind: One of ``"repeated_subproblem"``, ``"active_path_reentry"``,
            ``"failed_call"``, or ``"partial_trace"``.
        title: Short human-readable heading.
        message: Detailed explanation with guidance.
        call_ids: IDs of the relevant call nodes (empty for ``partial_trace``).
        subproblem_id: The identity string of the relevant subproblem, or ``None``.
        facts: Structured key-value pairs for the browser playground.
    """
    kind: Literal["repeated_subproblem", "active_path_reentry", "failed_call", "partial_trace"]
    title: str
    message: str
    call_ids: list[int]
    subproblem_id: Optional[str]
    facts: dict[str, Union[str, int]]


def _failed_call(report: TraceReport) -> Optional[Finding]:
    """Locate the deepest recorded call on the error path and build a finding.

    Walks down the tree from the root, always following the last child whose
    error matches the root's error, to find the deepest call that carries the
    error. For ``RecursionError``, the message includes guidance about the
    stopping condition.
    """
    error = report.error
    if report.succeeded or error is None:
        return None

    node = report.roots[0]
    while True:
        child = next((child for child in reversed(node.children) if child.error == error), None)
        if child is None:
            break
        node = child

    message = f"{node.signature} is the deepest recorded call on this path with the error {error}."
    if error.startswith("RecursionError:"):
        message += " Check the stopping condition and how the arguments change."
    return {
        "kind": "failed_call",
        "title": "Follow the recorded error",
        "message": message,
        "call_ids": [node.call_id],
        "subproblem_id": None,
        "facts": {"signature": node.signature, "error": error, "depth": node.depth},
    }


def diagnose(report: TraceReport) -> list[Finding]:
    """Find patterns supported by the recorded call tree without running user code."""
    active: dict[str, list[CallNode]] = {}
    finished: dict[str, CallNode] = {}
    executions: Counter[str] = Counter()
    branch_pairs: dict[str, tuple[CallNode, CallNode]] = {}
    reentry_pairs: dict[str, tuple[CallNode, CallNode]] = {}
    pending = [(root, False) for root in reversed(report.roots)]

    while pending:
        node, leaving = pending.pop()
        if node.cached:
            continue

        identity = node.identity
        if leaving:
            active[identity].pop()
            finished.setdefault(identity, node)
            continue

        executions[identity] += 1
        path = active.setdefault(identity, [])
        if path:
            reentry_pairs.setdefault(identity, (path[-1], node))
        # A call that finished before this one started cannot be its ancestor.
        if identity in finished:
            branch_pairs.setdefault(identity, (finished[identity], node))
        path.append(node)

        pending.append((node, True))
        pending.extend((child, False) for child in reversed(node.children))

    findings: list[Finding] = []
    failed = _failed_call(report)
    if failed is not None:
        findings.append(failed)

    for identity, (outer, inner) in reentry_pairs.items():
        findings.append(
            {
                "kind": "active_path_reentry",
                "title": "Same subproblem still active",
                "message": (
                    f"{inner.signature} started while a call to the same recorded "
                    "subproblem was still active. Check how the arguments and state "
                    "change toward a base case."
                ),
                "call_ids": [outer.call_id, inner.call_id],
                "subproblem_id": identity,
                "facts": {"signature": inner.signature},
            }
        )
    for identity, (earlier, later) in branch_pairs.items():
        count = executions[identity]
        findings.append(
            {
                "kind": "repeated_subproblem",
                "title": "Repeated work across branches",
                "message": (
                    f"The trace recorded {count} executions of {later.signature}, "
                    "including two in separate branches. If the arguments represent "
                    "the same input, the result depends only on those arguments, "
                    "and there are no side effects, memoization may help."
                ),
                "call_ids": [earlier.call_id, later.call_id],
                "subproblem_id": identity,
                "facts": {"signature": later.signature, "recorded_occurrences": count},
            }
        )
    if report.truncated:
        findings.append(
            {
                "kind": "partial_trace",
                "title": "Partial trace",
                "message": (
                    f"The trace recorded {report.recorded_calls} of {report.total_calls} "
                    "observed calls. Other patterns may be outside the recording."
                ),
                "call_ids": [],
                "subproblem_id": None,
                "facts": {
                    "recorded_calls": report.recorded_calls,
                    "total_calls": report.total_calls,
                },
            }
        )
    return findings
