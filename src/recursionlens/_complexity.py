"""Fit simple growth models to measured recursion counts.

This module implements the Big-O estimate used by the browser playground and
available directly in Python. It is deliberately small and dependency-free:
given input sizes and the number of function bodies executed for each size, it
fits a scaled straight line to several candidate shapes and reports the best
one with quality diagnostics.

The estimate is observational. It never runs user code and it cannot prove a
complexity class; a short or noisy sample is reported with a warning.

Module boundaries: pure Python and standard library only. Imports nothing from
other RecursionLens modules.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

# Ordered from simplest to fastest growing. The order is used as the
# deterministic tie-break when two models fit equally well.
Model = Tuple[str, Callable[[int, int], float]]
_MODELS: Tuple[Model, ...] = (
    ("O(1)", lambda n, base: 1.0),
    ("O(log n)", lambda n, base: math.log2(n + 1)),
    ("O(n)", lambda n, base: float(n)),
    ("O(n log n)", lambda n, base: n * math.log2(n + 1)),
    ("O(n^2)", lambda n, base: float(n * n)),
    ("O(2^n)", lambda n, base: float(2 ** min(n - base, 30))),
)


@dataclass
class GrowthFit:
    """The result of fitting growth models to measured execution counts.

    Attributes:
        model: Label of the best-fitting candidate, for example ``"O(n log n)"``.
        r2: Fit quality between 0 and 1. Normally the coefficient of
            determination (it can be negative when a fit is worse than a
            constant prediction); for samples that are nearly constant, it
            reports ``1 - relative spread`` instead, so a flat noisy sample
            scores close to 1 rather than being called exponential.
        rmse: Root-mean-square error in the original count units.
        samples: Input sizes with observed and fitted counts.
        candidates: Quality scores for every model, best first.
        warning: Optional caution about sample size or fit quality.
    """

    model: str
    r2: float
    rmse: float
    samples: List[Dict[str, object]] = field(default_factory=list)
    candidates: List[Dict[str, object]] = field(default_factory=list)
    warning: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        """Serialize the fit to a JSON-compatible dictionary."""
        return {
            "model": self.model,
            "r2": self.r2,
            "rmse": self.rmse,
            "samples": [dict(sample) for sample in self.samples],
            "candidates": [dict(candidate) for candidate in self.candidates],
            "warning": self.warning,
        }


def _validate(
    sizes: Sequence[int], counts: Sequence[float]
) -> Tuple[List[int], List[float]]:
    """Normalize inputs or raise a clear ``ValueError``."""
    if len(sizes) != len(counts):
        raise ValueError("Growth fitting needs one count for every input size.")
    if len(sizes) < 3:
        raise ValueError("Growth fitting needs at least three measurements.")

    try:
        normalized_sizes = [int(size) for size in sizes]
        normalized_counts = [float(count) for count in counts]
    except (TypeError, ValueError) as exc:
        raise ValueError("Sizes and counts must be numbers.") from exc
    if any(size != raw for size, raw in zip(normalized_sizes, sizes)) or any(
        size < 0 for size in normalized_sizes
    ):
        raise ValueError("Input sizes must be non-negative integers.")
    if any(not math.isfinite(count) or count < 0 for count in normalized_counts):
        raise ValueError("Execution counts must be finite and non-negative.")
    return normalized_sizes, normalized_counts


def _fit_line(xs: Sequence[float], ys: Sequence[float]) -> Tuple[float, float, List[float]]:
    """Least-squares fit of ``y = slope * x + intercept`` with a zero-variance guard."""
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    variance_x = sum((value - mean_x) ** 2 for value in xs)
    if variance_x == 0:
        slope = 0.0
    else:
        covariance = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
        slope = covariance / variance_x
    intercept = mean_y - slope * mean_x
    predicted = [slope * x + intercept for x in xs]
    return slope, intercept, predicted


def fit_growth(sizes: Sequence[int], counts: Sequence[float]) -> GrowthFit:
    """Fit candidate complexity models to measured execution counts.

    Args:
        sizes: Non-negative integer input sizes, in the same order as ``counts``.
        counts: Function body executions observed for each input size.

    Returns:
        A :class:`GrowthFit` containing the best model, its quality scores,
        fitted values for each sample, and a warning when the evidence is weak.

    Raises:
        ValueError: If the inputs have different lengths, contain fewer than
            three points, or include invalid sizes or counts.
    """
    normalized_sizes, normalized_counts = _validate(sizes, counts)
    base = min(normalized_sizes)
    mean_y = sum(normalized_counts) / len(normalized_counts)
    total_variance = sum((value - mean_y) ** 2 for value in normalized_counts)
    # Floating-point sums of identical values can leave a tiny nonzero
    # variance. Treat anything this small as zero to keep constant samples
    # from being reported as a poor fit.
    scale = max(1.0, max(abs(count) for count in normalized_counts))
    epsilon = 1e-12 * scale * scale

    results = []
    for order, (label, transform) in enumerate(_MODELS):
        xs = [float(transform(size, base)) for size in normalized_sizes]
        _, _, predicted = _fit_line(xs, normalized_counts)
        sse = sum(
            (observed - estimate) ** 2
            for observed, estimate in zip(normalized_counts, predicted)
        )
        if total_variance <= epsilon:
            r2 = 1.0 if sse <= epsilon else 0.0
        else:
            r2 = 1.0 - sse / total_variance
        rmse = math.sqrt(sse / len(normalized_counts))
        results.append((round(r2, 6), round(rmse, 6), order, label, predicted))

    results.sort(key=lambda item: (-item[0], item[1], item[2]))
    best_r2, best_rmse, _, best_label, best_predicted = results[0]

    # A genuinely constant-time algorithm still produces noisy counts in
    # practice. Standard R2 is always zero for a constant prediction, so any
    # sloped model can win by "explaining" a little of that noise. When the
    # counts barely change relative to their mean and nothing fits well,
    # report O(1) explicitly instead of a misleading exponential label.
    weak_fit = best_r2 < 0.8
    mean_count = sum(normalized_counts) / len(normalized_counts)
    relative_spread = (
        (max(normalized_counts) - min(normalized_counts)) / mean_count
        if mean_count > 0
        else 0.0
    )
    quasi_constant = relative_spread <= 0.1
    if weak_fit and quasi_constant:
        best_label = "O(1)"
        best_r2 = round(1.0 - relative_spread, 6)
        best_rmse = round(math.sqrt(total_variance / len(normalized_counts)), 6)
        best_predicted = [mean_count] * len(normalized_counts)
        results = [
            (best_r2, best_rmse, 0, "O(1)", best_predicted)
            if item[3] == "O(1)"
            else item
            for item in results
        ]
        results.sort(key=lambda item: (-item[0], item[1], item[2]))

    warnings: List[str] = []
    if len(normalized_sizes) < 5:
        warnings.append("Only a few measurements: treat this estimate as tentative.")
    if weak_fit and quasi_constant:
        warnings.append(
            "Counts barely change with input size; treating the growth as constant."
        )
    elif weak_fit:
        warnings.append("No candidate model fits well; the sample may be noisy or mixed.")

    return GrowthFit(
        model=best_label,
        r2=best_r2,
        rmse=best_rmse,
        samples=[
            {
                "size": size,
                "observed": observed,
                "fitted": round(estimate, 3),
            }
            for size, observed, estimate in zip(normalized_sizes, normalized_counts, best_predicted)
        ],
        candidates=[
            {"model": label, "r2": r2, "rmse": rmse}
            for r2, rmse, _, label, _ in results
        ],
        warning=" ".join(warnings) or None,
    )
