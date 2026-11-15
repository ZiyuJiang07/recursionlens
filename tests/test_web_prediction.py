import json
from pathlib import Path
import runpy

import pytest


ASSETS = Path(__file__).resolve().parents[1] / "assets"
run_payload = runpy.run_path(str(ASSETS / "bridge.py"))["run_payload"]


@pytest.mark.parametrize(
    ("name", "value", "original", "memoized", "hits"),
    [("Grid paths", "20", 39, 15, 4), ("gcd", "6", 4, 4, 0)],
)
def test_examples_expose_measured_cache_savings(name, value, original, memoized, hits):
    source = (ASSETS / "examples.js").read_text(encoding="utf-8")
    examples = json.loads(source.partition("=")[2].strip().removesuffix(";"))
    example = next(item for item in examples if item["name"] == name)

    payload = json.loads(run_payload(example["code"], example["call"]))
    comparison = payload["comparison"]

    assert payload["result"] == value
    assert comparison["same_result"]
    assert not comparison["left"]["truncated"]
    assert not comparison["right"]["truncated"]
    assert comparison["left"]["executed_calls"] == original
    assert comparison["right"]["executed_calls"] == memoized
    assert comparison["right"]["cached_calls"] == hits


def test_failed_run_does_not_provide_a_prediction_answer():
    payload = json.loads(run_payload("def fail(n):\n    return 1 // n\n", "fail(0)"))

    assert "ZeroDivisionError" in payload["run_error"]
    assert payload["comparison"] is None
