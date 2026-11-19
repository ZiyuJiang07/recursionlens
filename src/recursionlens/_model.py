"""Data models for RecursionLens.

This module defines the core data structures used throughout the package:

- :class:`CallNode` — one observed function invocation (including cache-only hits).
- :class:`DAGNode` — all invocations with the same argument identity, merged together.
- :func:`build_dag` — compresses a call forest into a deterministic subproblem DAG.

The models are pure data classes with no dependencies on other RecursionLens
modules, so they can be imported safely from anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple


@dataclass
class CallNode:
    """One observed function invocation, including cache-only invocations.

    A call node records the invocation's identity, display signature, depth in
    the call tree, status (``"running"``, ``"returned"``, ``"cached"``, or
    ``"error"``), result or error string, whether the same subproblem was seen
    before, and the node's children in the call tree.

    The ``call_id`` is a zero-based index into the recorder's ``nodes`` list
    and is stable within a single run.
    """

    call_id: int
    identity: str
    signature: str
    depth: int
    status: str = "running"
    result: Optional[str] = None
    error: Optional[str] = None
    repeated: bool = False
    children: List["CallNode"] = field(default_factory=list)

    @property
    def cached(self) -> bool:
        """Whether this invocation was served from the memoization cache."""
        return self.status == "cached"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize this node and its children to a JSON-compatible dict."""
        return {
            "call_id": self.call_id,
            "identity": self.identity,
            "signature": self.signature,
            "depth": self.depth,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "repeated": self.repeated,
            "children": [child.to_dict() for child in self.children],
        }


@dataclass
class DAGNode:
    """All invocations with one internal argument identity, merged together.

    A DAG node aggregates every call that shares the same ``identity`` string.
    It records how many times the subproblem was called, how many of those
    calls actually executed the function body, how many were cache hits, and
    the first non-None result seen. The ``children`` list contains the
    identities of distinct child subproblems, deduplicated and in first-seen
    order.
    """

    identity: str
    signature: str
    calls: int = 0
    executed: int = 0
    cached: int = 0
    result: Optional[str] = None
    children: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize this DAG node to a JSON-compatible dict."""
        return {
            "identity": self.identity,
            "signature": self.signature,
            "calls": self.calls,
            "executed": self.executed,
            "cached": self.cached,
            "result": self.result,
            "children": list(self.children),
        }


def build_dag(nodes: Iterable[CallNode]) -> Tuple[List[DAGNode], List[Dict[str, str]]]:
    """Compress a call forest into a deterministic subproblem DAG.

    Given the root nodes of a call tree, this function merges all invocations
    that share the same ``identity`` into a single :class:`DAGNode`, counts
    executions and cache hits, and builds the set of distinct parent-child edges.

    Returns a tuple of ``(dag_nodes, edges)`` where ``edges`` is a list of
    ``{"source": identity, "target": identity}`` dicts sorted lexicographically
    for deterministic output.

    The traversal is depth-first and safe against cycles (though a well-formed
    call tree should not contain any): a node is visited once per occurrence
    in the tree, and edges are deduplicated via a set.
    """

    merged: Dict[str, DAGNode] = {}
    edges = set()

    def visit(node: CallNode) -> None:
        dag_node = merged.get(node.identity)
        if dag_node is None:
            dag_node = DAGNode(identity=node.identity, signature=node.signature)
            merged[node.identity] = dag_node

        dag_node.calls += 1
        if node.cached:
            dag_node.cached += 1
        else:
            dag_node.executed += 1
        if dag_node.result is None and node.result is not None:
            dag_node.result = node.result

        for child in node.children:
            if child.identity not in dag_node.children:
                dag_node.children.append(child.identity)
            edges.add((node.identity, child.identity))
            visit(child)

    for root in nodes:
        visit(root)

    edge_dicts = [{"source": source, "target": target} for source, target in sorted(edges)]
    return list(merged.values()), edge_dicts
