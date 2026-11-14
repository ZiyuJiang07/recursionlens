from __future__ import annotations

from collections import Counter
from typing import Literal, Optional, TypedDict, Union

from ._model import CallNode
from ._report import TraceReport


class Finding(TypedDict):
    kind: Literal["repeated_subproblem", "active_path_reentry", "partial_trace"]
    title: str
    message: str
    call_ids: list[int]
    subproblem_id: Optional[str]
    facts: dict[str, Union[str, int]]


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
