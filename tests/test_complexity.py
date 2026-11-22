import json
import math

import pytest

import recursionlens
from recursionlens import GrowthFit, fit_growth, trace

SIZES = list(range(1, 13))


def test_growth_fit_is_part_of_the_public_api():
    assert "fit_growth" in recursionlens.__all__
    assert "GrowthFit" in recursionlens.__all__
    assert isinstance(fit_growth(SIZES, [2 * n for n in SIZES]), GrowthFit)


@pytest.mark.parametrize(
    ("model", "counts"),
    [
        ("O(n)", [2 * n for n in SIZES]),
        ("O(n log n)", [3 * n * math.log2(n + 1) for n in SIZES]),
        ("O(n^2)", [n * n for n in SIZES]),
        ("O(2^n)", [2**n for n in SIZES]),
    ],
)
def test_fit_growth_recovers_common_shapes(model, counts):
    fit = fit_growth(SIZES, counts)

    assert fit.model == model
    assert fit.r2 == pytest.approx(1.0)
    assert fit.warning is None
    assert len(fit.samples) == len(SIZES)


def test_fit_growth_prefers_the_simplest_model_for_constant_counts():
    fit = fit_growth(SIZES, [7] * len(SIZES))

    assert fit.model == "O(1)"
    assert fit.r2 == 1.0
    assert fit.candidates[0]["model"] == "O(1)"


@pytest.mark.parametrize("value", [0.1, 1 / 3, 7.0])
def test_fit_growth_treats_constant_float_counts_as_a_perfect_fit(value):
    fit = fit_growth(SIZES, [value] * len(SIZES))

    assert fit.model == "O(1)"
    assert fit.r2 == 1.0
    assert fit.warning is None


def test_fit_growth_recovers_logarithmic_counts():
    fit = fit_growth(SIZES, [4 * math.log2(n + 1) for n in SIZES])

    assert fit.model == "O(log n)"
    assert fit.r2 == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("model", "counts"),
    [
        ("O(log n)", [4 * math.log2(n) for n in SIZES]),
        ("O(n log n)", [3 * n * math.log2(n) for n in SIZES]),
    ],
)
def test_fit_growth_accepts_standard_logarithmic_definitions(model, counts):
    # Generated from the textbook formulas, not from the module's own
    # n + 1 shifted transforms, so a broken transform cannot hide here.
    fit = fit_growth(SIZES, counts)

    assert fit.model == model
    assert fit.r2 > 0.95


@pytest.mark.parametrize(
    "counts",
    [
        [10, 10, 11, 10, 10, 10],
        [100, 101, 99, 100, 102, 98],
    ],
)
def test_fit_growth_treats_noisy_constant_counts_as_constant(counts):
    fit = fit_growth(list(range(1, 7)), counts)

    assert fit.model == "O(1)"
    assert fit.r2 > 0.8
    assert fit.candidates[0]["model"] == "O(1)"
    assert "barely change" in fit.warning


def test_fit_growth_warns_about_short_samples():
    fit = fit_growth([1, 2, 3], [2, 4, 6])

    assert fit.model == "O(n)"
    assert "few measurements" in fit.warning


def test_fit_growth_warns_when_no_model_fits_well():
    fit = fit_growth(SIZES, [1, 90, 2, 80, 3, 70, 4, 60, 5, 50, 6, 40])

    assert fit.r2 < 0.8
    assert "No candidate model fits well" in fit.warning
    assert "barely change" not in fit.warning


def test_fit_growth_is_ordered_and_json_serializable():
    fit = fit_growth(SIZES, [n * n for n in SIZES])

    scores = [candidate["r2"] for candidate in fit.candidates]
    assert scores == sorted(scores, reverse=True)
    assert len(scores) == 6
    assert json.loads(json.dumps(fit.to_dict())) == fit.to_dict()


@pytest.mark.parametrize(
    ("sizes", "counts", "message"),
    [
        ([1, 2, 3], [1, 2], "one count for every input size"),
        ([1, 2], [1, 2], "at least three"),
        ([-1, 1, 2], [1, 2, 3], "non-negative integers"),
        ([1, 2.5, 3], [1, 2, 3], "non-negative integers"),
        ([1, 2, 3], [1, -2, 3], "must be finite and non-negative"),
        ([1, 2, 3], [1, float("nan"), 3], "must be finite and non-negative"),
        ([1, 2, 3], [1, float("inf"), 3], "must be finite and non-negative"),
    ],
)
def test_fit_growth_rejects_invalid_measurements(sizes, counts, message):
    with pytest.raises(ValueError, match=message):
        fit_growth(sizes, counts)


def test_fit_growth_handles_zero_counts_and_repeated_sizes():
    zero = fit_growth(SIZES, [0] * len(SIZES))

    assert zero.model == "O(1)"
    assert zero.r2 == 1.0

    repeated = fit_growth([5, 5, 5], [2, 2, 2])

    assert repeated.model == "O(1)"
    assert "few measurements" in repeated.warning


def test_fit_growth_accepts_tuples_of_measurements():
    fit = fit_growth(tuple(SIZES), tuple(2 * n for n in SIZES))

    assert fit.model == "O(n)"
    assert all(isinstance(sample["size"], int) for sample in fit.samples)


def test_fit_growth_identifies_measured_fibonacci_execution_counts():
    @trace
    def fib(n):
        return n if n < 2 else fib(n - 1) + fib(n - 2)

    sizes = list(range(1, 11))
    counts = [fib.with_options(max_calls=1).run(n).executed_calls for n in sizes]

    assert counts == [1, 3, 5, 9, 15, 25, 41, 67, 109, 177]
    assert fit_growth(sizes, counts).model == "O(2^n)"
