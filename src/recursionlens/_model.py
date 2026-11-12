from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple


@dataclass
class CallNode:
    """One observed function invocation, including cache-only invocations."""

    call_id: int
    signature: str
    depth: int
    status: str = "running"
    result: Optional[str] = None
    error: Optional[str] = None
    repeated: bool = False
    children: List["CallNode"] = field(default_factory=list)

    @property
    def cached(self) -> bool:
        return self.status == "cached"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "call_id": self.call_id,
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
    """All invocations with one canonical argument signature, merged together."""

    signature: str
    calls: int = 0
    executed: int = 0
    cached: int = 0
    result: Optional[str] = None
    children: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signature": self.signature,
            "calls": self.calls,
            "executed": self.executed,
            "cached": self.cached,
            "result": self.result,
            "children": list(self.children),
        }


def build_dag(nodes: Iterable[CallNode]) -> Tuple[List[DAGNode], List[Dict[str, str]]]:
    """Compress a call forest into a deterministic subproblem DAG."""

    merged: Dict[str, DAGNode] = {}
    edges = set()

    def visit(node: CallNode) -> None:
        dag_node = merged.get(node.signature)
        if dag_node is None:
            dag_node = DAGNode(signature=node.signature)
            merged[node.signature] = dag_node

        dag_node.calls += 1
        if node.cached:
            dag_node.cached += 1
        else:
            dag_node.executed += 1
        if dag_node.result is None and node.result is not None:
            dag_node.result = node.result

        for child in node.children:
            if child.signature not in dag_node.children:
                dag_node.children.append(child.signature)
            edges.add((node.signature, child.signature))
            visit(child)

    for root in nodes:
        visit(root)

    edge_dicts = [{"source": source, "target": target} for source, target in sorted(edges)]
    return list(merged.values()), edge_dicts
