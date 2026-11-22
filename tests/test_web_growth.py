import json
import re
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
    fit = payload["fit"]
    assert fit["model"] == "O(2^n)"
    assert fit["r2"] > 0.9
    assert len(fit["candidates"]) == 6


def test_growth_omits_the_estimate_for_too_few_samples():
    code = """def step(n):
    return 0 if n == 0 else step(n - 1) + 1
"""
    payload = json.loads(growth_payload(code, "step({n})", 0, 1))

    assert payload["fit"] is None
    assert len(payload["samples"]) == 2


def test_pyodide_package_files_cover_every_local_import():
    script = (ASSETS / "app.js").read_text(encoding="utf-8")
    block = script.split("const PACKAGE_FILES = [", 1)[1].split("];", 1)[0]
    shipped = set(re.findall(r'"([^"]+\.py)"', block))
    package_dir = ASSETS.parent / "src/recursionlens"
    imported = set()
    for source in package_dir.glob("*.py"):
        imported.update(
            re.findall(
                r"^from \.(\w+) import",
                source.read_text(encoding="utf-8"),
                flags=re.MULTILINE,
            )
        )

    assert {f"{module}.py" for module in imported} <= shipped
    assert "_complexity.py" in shipped


def test_web_page_displays_the_growth_estimate():
    markup = (ASSETS.parent / "index.html").read_text(encoding="utf-8")
    script = (ASSETS / "app.js").read_text(encoding="utf-8")

    assert 'id="growth-fit"' in markup
    assert 'aria-describedby="growth-summary growth-fit"' in markup
    assert "describeGrowthFit" in script
    assert "state.growthResult.fit" in script


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
