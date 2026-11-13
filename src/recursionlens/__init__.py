"""RecursionLens: recursive execution analysis for JupyterLab."""

from ._model import CallNode, DAGNode
from ._report import ComparisonReport, TraceReport
from ._trace import trace
from ._tutor import TutorStep, TutorTrace, record_tutor, tutor

__version__ = "0.2.0"

__all__ = [
    "CallNode",
    "ComparisonReport",
    "DAGNode",
    "TraceReport",
    "TutorStep",
    "TutorTrace",
    "record_tutor",
    "trace",
    "tutor",
    "__version__",
]
