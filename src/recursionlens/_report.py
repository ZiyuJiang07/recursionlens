"""Serializable report objects for RecursionLens.

This module defines two data classes:

- :class:`TraceReport` — a complete record of one traced top-level invocation,
  including the call tree, DAG, metrics, and export methods.
- :class:`ComparisonReport` — a quantitative and visual comparison of two
  traced runs (typically naive vs. memoized).

Both classes support JSON serialization, standalone HTML export, and
JupyterLab rendering via ``_repr_html_``.

Module boundaries: imports from :mod:`recursionlens._model`. Lazily imports
:mod:`recursionlens._render` inside methods to avoid a circular dependency
(render imports model, but not report).
"""

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
    succeeded: bool = True
    # Reports constructed without runtime counts can still use their recorded nodes.
    _executed_calls: Optional[int] = field(default=None, repr=False, compare=False)
    _cached_calls: Optional[int] = field(default=None, repr=False, compare=False)

    @property
    def recorded_calls(self) -> int:
        """Number of call nodes actually stored (may be less than ``total_calls`` if truncated)."""
        return len(self.nodes)

    @property
    def cached_calls(self) -> int:
        """Invocations served from a cache: the code's own ``functools.lru_cache``
        (or ``functools.cache``), or RecursionLens memoization when enabled."""
        if self._cached_calls is not None:
            return self._cached_calls
        return sum(node.cached for node in self.nodes)

    @property
    def executed_calls(self) -> int:
        """Number of invocations where the function body actually ran."""
        if self._executed_calls is not None:
            return self._executed_calls
        return self.recorded_calls - self.cached_calls

    @property
    def dag_nodes(self) -> List[DAGNode]:
        """The compressed subproblem DAG nodes, computed once and cached."""
        if not hasattr(self, "_dag_nodes_cache"):
            self._dag_nodes_cache = build_dag(self.roots)[0]
        return self._dag_nodes_cache

    @property
    def dag_edges(self) -> List[Dict[str, str]]:
        """The edges of the compressed subproblem DAG, computed once and cached."""
        if not hasattr(self, "_dag_edges_cache"):
            self._dag_edges_cache = build_dag(self.roots)[1]
        return self._dag_edges_cache

    @property
    def unique_subproblems(self) -> int:
        """Number of distinct subproblems in the DAG."""
        return len(self.dag_nodes)

    @property
    def repeated_calls(self) -> int:
        """Number of recorded calls that hit a previously seen subproblem."""
        return self.recorded_calls - self.unique_subproblems

    @property
    def result(self) -> Optional[str]:
        """The display representation of the root call's return value, or ``None``."""
        if self.roots:
            return self.roots[0].result
        return None

    @property
    def error(self) -> Optional[str]:
        """The error string of the root call if it raised, or ``None``."""
        if self.roots:
            return self.roots[0].error
        return None

    def metrics(self) -> Dict[str, Any]:
        """Return all metrics as a flat dictionary suitable for JSON serialization."""
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
            "succeeded": self.succeeded,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the full report (tree, DAG, metrics, warnings) to a JSON-compatible dict."""
        return {
            "schema_version": 1,
            "function_name": self.function_name,
            "result": self.result,
            "error": self.error,
            "metrics": self.metrics(),
            "warnings": list(self.warnings),
            "roots": [root.to_dict() for root in self.roots],
            "dag": {
                "nodes": [node.to_dict() for node in self.dag_nodes],
                "edges": list(self.dag_edges),
            },
        }

    def export_json(self, path: Union[str, Path]) -> Path:
        """Write the serialized report to ``path`` as UTF-8 JSON and return the path."""
        destination = Path(path)
        destination.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return destination

    def to_html(self, mode: str = "tree") -> str:
        """Render this report as an HTML fragment (call tree, DAG, or expanded tree)."""
        from ._render import render_report

        return render_report(self, mode=mode)

    def export_html(self, path: Union[str, Path], mode: str = "tree") -> Path:
        """Write a standalone HTML document to ``path`` and return the path."""
        from ._render import render_document

        destination = Path(path)
        destination.write_text(render_document(self.to_html(mode=mode)), encoding="utf-8")
        return destination

    def _repr_html_(self) -> str:
        """JupyterLab rich display: render as an HTML fragment."""
        return self.to_html()

    def show(self, mode: str = "tree") -> Any:
        """Display the report in a JupyterLab notebook, or return HTML if not in a notebook."""
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
        """Build a :class:`ComparisonReport` comparing this run with ``other``."""
        return ComparisonReport(self, other, labels)


@dataclass
class ComparisonReport:
    """Quantitative and visual comparison of two traced runs."""

    left: TraceReport
    right: TraceReport
    labels: Tuple[str, str] = ("naive", "memoized")

    @property
    def same_result(self) -> bool:
        """Whether both runs succeeded and returned equal values."""
        if not self.left.succeeded or not self.right.succeeded:
            return False
        try:
            return bool(self.left.value == self.right.value)
        except Exception:
            return False

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the comparison (metrics, deltas, same_result) to a JSON-compatible dict."""
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
            "same_result": self.same_result,
        }

    def to_html(self) -> str:
        """Render the comparison as an HTML fragment with a metrics table and side-by-side DAGs."""
        from ._render import render_comparison

        return render_comparison(self)

    def export_html(self, path: Union[str, Path]) -> Path:
        """Write a standalone HTML comparison document to ``path`` and return the path."""
        from ._render import render_document

        destination = Path(path)
        destination.write_text(render_document(self.to_html()), encoding="utf-8")
        return destination

    def _repr_html_(self) -> str:
        """JupyterLab rich display: render as an HTML fragment."""
        return self.to_html()

    def show(self) -> Any:
        """Display the comparison in a JupyterLab notebook, or return HTML if not in a notebook."""
        html = self.to_html()
        try:
            from IPython.display import HTML, display
        except ImportError:
            return html
        display(HTML(html))
        return None
