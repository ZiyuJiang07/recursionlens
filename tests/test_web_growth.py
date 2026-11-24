import json
import re
import runpy
import sys
from pathlib import Path

import pytest


ASSETS = Path(__file__).resolve().parents[1] / "assets"
bridge = runpy.run_path(str(ASSETS / "bridge.py"))
growth_payload = bridge["growth_payload"]
suggest_growth_call = bridge["suggest_growth_call"]


@pytest.mark.parametrize(
    ("example_id", "template", "sizes", "last_call", "naive", "memoized"),
    [
        ("fibonacci", "fibonacci({n})", range(1, 13), "fibonacci(12)", 465, 13),
        ("grid-paths", "paths({n}, {n})", range(7), "paths(6, 6)", 1847, 48),
    ],
)
def test_growth_counts_include_calls_outside_the_stored_tree(
    example_id, template, sizes, last_call, naive, memoized
):
    source = (ASSETS / "examples.js").read_text(encoding="utf-8")
    examples = json.loads(source.partition("=")[2].strip().removesuffix(";"))
    example = next(item for item in examples if item["id"] == example_id)
    payload = json.loads(
        growth_payload(example["code"], template, sizes[0], sizes[-1])
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
    assert len(payload["memoized_fit"]["samples"]) == len(sizes)


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
    assert 'aria-describedby="growth-summary growth-fit growth-fit-cached"' in markup
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

    assert payload["error"] == "ValueError: The runs returned different results for count(1)."
    assert payload["failed_call"] == "count(1)"


def test_growth_measures_custom_code_with_keywords_and_dictionary_arguments():
    code = """def descend(n, *, options):
    if n == 0:
        return options["base"]
    return 1 + descend(n - 1, options=options)
"""
    payload = json.loads(
        growth_payload(code, 'descend({n}, options={"base": 0})', 0, 8, 2)
    )

    assert [sample["size"] for sample in payload["samples"]] == [0, 2, 4, 6, 8]
    assert [sample["naive"] for sample in payload["samples"]] == [1, 3, 5, 7, 9]
    assert payload["fit"]["model"] == "O(n)"
    assert payload["memoized_fit"]["model"] == "O(n)"


def test_growth_resets_custom_state_between_every_measured_run():
    code = """visits = []
def countdown(n):
    visits.append(n)
    return len(visits) if n == 0 else countdown(n - 1)
"""
    payload = json.loads(growth_payload(code, "countdown({n})", 1, 4))

    assert [sample["naive"] for sample in payload["samples"]] == [2, 3, 4, 5]
    assert [sample["memoized"] for sample in payload["samples"]] == [2, 3, 4, 5]


@pytest.mark.parametrize(
    ("call", "template"),
    [
        ("factorial(6)", "factorial({n})"),
        ("paths(3, 3)", "paths({n}, 3)"),
        ("factorial(n=-3)", "factorial(n={n})"),
        ("函数(5, tag='中文')", "函数({n}, tag='中文')"),
        ("consume([1, 2, 3])", ""),
        ("consume(True)", ""),
        ("consume(", ""),
    ],
)
def test_growth_suggests_an_input_template_from_the_current_call(call, template):
    assert suggest_growth_call(call) == template


@pytest.mark.parametrize(
    ("template", "start", "stop", "step", "message"),
    [
        ("f(2)", 1, 3, 1, "Put {n}"),
        ("f({n})", 5, 2, 1, "start <= stop"),
        ("f({n})", 1, 3, 0, "positive step"),
        ("f({n})", -1, 3, 1, "non-negative"),
        ("f({n})", 1, 100, 1, "at most 30"),
        ("f({n})", 1.5, 3, 1, "must be integers"),
    ],
)
def test_growth_rejects_invalid_input_before_executing_code(template, start, stop, step, message):
    payload = json.loads(growth_payload("raise AssertionError('executed')", template, start, stop, step))

    assert message in payload["error"]
    assert payload["failed_call"] is None


def test_growth_limit_stops_a_nonterminating_input_and_restores_tracing(monkeypatch):
    monkeypatch.setitem(growth_payload.__globals__, "MAX_GROWTH_STEPS", 100)
    previous = sys.gettrace()
    code = """def stuck(n):
    if n:
        while True:
            pass
    return 0
"""
    payload = json.loads(growth_payload(code, "stuck({n})", 0, 1))

    assert "measurement limit reached" in payload["error"]
    assert payload["failed_call"] == "stuck(1)"
    assert sys.gettrace() is previous
