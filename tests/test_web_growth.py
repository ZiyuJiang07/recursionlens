import json
import runpy
from pathlib import Path

import pytest


ASSETS = Path(__file__).resolve().parents[1] / "assets"
growth_payload = runpy.run_path(str(ASSETS / "bridge.py"))["growth_payload"]


@pytest.mark.parametrize(
    ("example_id", "sizes", "last_call", "naive", "memoized"),
    [
        ("fibonacci", range(1, 13), "fibonacci(12)", 465, 13),
        ("grid-paths", range(7), "paths(6, 6)", 1847, 48),
    ],
)
def test_growth_counts_include_calls_outside_the_stored_tree(
    example_id, sizes, last_call, naive, memoized
):
    source = (ASSETS / "examples.js").read_text(encoding="utf-8")
    examples = json.loads(source.partition("=")[2].strip().removesuffix(";"))
    example = next(item for item in examples if item["id"] == example_id)
    spec = example["growth"]

    payload = json.loads(
        growth_payload(example["code"], spec["call"], spec["start"], spec["stop"])
    )
    samples = payload["samples"]

    assert [sample["size"] for sample in samples] == list(sizes)
    assert samples[-1] == {
        "size": sizes[-1],
        "call": last_call,
        "naive": naive,
        "memoized": memoized,
    }
    assert all(0 < sample["memoized"] <= sample["naive"] for sample in samples)


def test_growth_reports_when_memoization_changes_a_result():
    code = """visits = 0

def count(n):
    global visits
    visits += 1
    if n == 0:
        return visits
    return count(n - 1) + count(n - 1)
"""
    payload = json.loads(growth_payload(code, "count({n})", 0, 1))

    assert payload == {"error": "ValueError: The runs returned different results for count(1)."}
