from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from ._model import CallNode, DAGNode, build_dag


@dataclass
class TraceReport:
    """A serializable record of one traced top-level invocation."""

    function_name: str
    value: Any
    nodes: List[CallNode]
    roots: List[CallNode]
    total_calls: int
    max_depth: int
    memoize: bool = False
    truncated: bool = False
    warnings: List[str] = field(default_factory=list)

    @property
    def recorded_calls(self) -> int:
        return len(self.nodes)

    @property
    def cached_calls(self) -> int:
        return sum(node.cached for node in self.nodes)

    @property
    def executed_calls(self) -> int:
        return self.recorded_calls - self.cached_calls

    @property
    def dag_nodes(self) -> List[DAGNode]:
        return build_dag(self.roots)[0]

    @property
    def dag_edges(self) -> List[Dict[str, str]]:
        return build_dag(self.roots)[1]

    @property
    def unique_subproblems(self) -> int:
        return len(self.dag_nodes)

    @property
    def repeated_calls(self) -> int:
        return self.recorded_calls - self.unique_subproblems

    @property
    def result(self) -> Optional[str]:
        if self.roots:
            return self.roots[0].result
        return None

    def metrics(self) -> Dict[str, Any]:
        return {
            "total_calls": self.total_calls,
            "recorded_calls": self.recorded_calls,
            "executed_calls": self.executed_calls,
            "cached_calls": self.cached_calls,
            "unique_subproblems": self.unique_subproblems,
            "repeated_calls": self.repeated_calls,
            "max_depth": self.max_depth,
            "memoize": self.memoize,
            "truncated": self.truncated,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": 1,
            "function_name": self.function_name,
            "result": self.result,
            "metrics": self.metrics(),
            "warnings": list(self.warnings),
            "roots": [root.to_dict() for root in self.roots],
            "dag": {
                "nodes": [node.to_dict() for node in self.dag_nodes],
                "edges": list(self.dag_edges),
            },
        }

    def export_json(self, path: Union[str, Path]) -> Path:
        destination = Path(path)
        destination.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return destination

    def to_html(self, mode: str = "tree") -> str:
        from ._render import render_report

        return render_report(self, mode=mode)

    def export_html(self, path: Union[str, Path], mode: str = "tree") -> Path:
        from ._render import render_document

        destination = Path(path)
        destination.write_text(render_document(self.to_html(mode=mode)), encoding="utf-8")
        return destination

    def _repr_html_(self) -> str:
        return self.to_html()

    def show(self, mode: str = "tree") -> Any:
        html = self.to_html(mode=mode)
        try:
            from IPython.display import HTML, display
        except ImportError:
            return html
        display(HTML(html))
        return None

    def compare(
        self,
        other: "TraceReport",
        labels: Tuple[str, str] = ("naive", "memoized"),
    ) -> "ComparisonReport":
        return ComparisonReport(self, other, labels)


@dataclass
class ComparisonReport:
    """Quantitative and visual comparison of two traced runs."""

    left: TraceReport
    right: TraceReport
    labels: Tuple[str, str] = ("naive", "memoized")

    def to_dict(self) -> Dict[str, Any]:
        left_metrics = self.left.metrics()
        right_metrics = self.right.metrics()
        keys = (
            "total_calls",
            "executed_calls",
            "cached_calls",
            "unique_subproblems",
            "repeated_calls",
            "max_depth",
        )
        return {
            "labels": list(self.labels),
            "left": left_metrics,
            "right": right_metrics,
            "delta": {key: right_metrics[key] - left_metrics[key] for key in keys},
        }

    def to_html(self) -> str:
        from ._render import render_comparison

        return render_comparison(self)

    def export_html(self, path: Union[str, Path]) -> Path:
        from ._render import render_document

        destination = Path(path)
        destination.write_text(render_document(self.to_html()), encoding="utf-8")
        return destination

    def _repr_html_(self) -> str:
        return self.to_html()

    def show(self) -> None:
        try:
            from IPython.display import HTML, display
        except ImportError:
            return None
        display(HTML(self.to_html()))
        return None
