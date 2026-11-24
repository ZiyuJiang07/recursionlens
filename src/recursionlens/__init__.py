"""RecursionLens: recursive execution analysis for JupyterLab."""

from ._complexity import GrowthFit, fit_growth
from ._model import CallNode, DAGNode
from ._report import ComparisonReport, TraceReport
from ._trace import trace
from ._tutor import TutorStep, TutorTrace, record_tutor, tutor

__version__ = "0.2.2"

__all__ = [
    "CallNode",
    "ComparisonReport",
    "DAGNode",
    "GrowthFit",
    "TraceReport",
    "TutorStep",
    "TutorTrace",
    "fit_growth",
    "record_tutor",
    "trace",
    "tutor",
    "__version__",
]
