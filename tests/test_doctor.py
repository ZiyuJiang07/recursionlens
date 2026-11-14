import json

from recursionlens import trace
from recursionlens._doctor import diagnose


@trace
def fib(n):
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)


def test_repeated_subproblem_links_two_executions_in_separate_branches():
    report = fib.run(5)
    findings = diagnose(report)
    repeated = {finding["facts"]["signature"]: finding for finding in findings}

    assert set(repeated) == {"fib(n=0)", "fib(n=1)", "fib(n=2)", "fib(n=3)"}
    finding = repeated["fib(n=2)"]
    fib_four = report.roots[0].children[0]
    fib_three = fib_four.children[0]
    first = fib_three.children[0]
    second = fib_four.children[1]

    assert finding["kind"] == "repeated_subproblem"
    assert finding["call_ids"] == [first.call_id, second.call_id]
    assert finding["subproblem_id"] == first.identity == second.identity
    assert finding["facts"]["recorded_occurrences"] == 3
    assert json.loads(json.dumps(findings)) == findings


def test_a_cache_hit_does_not_count_as_repeated_execution():
    report = fib.with_options(memoize=True).run(5)

    assert report.cached_calls == 3
    assert diagnose(report) == []


def test_same_active_subproblem_can_reenter_and_still_return():
    remaining = 2

    @trace
    def descend():
        nonlocal remaining
        if remaining == 0:
            return 0
        remaining -= 1
        return 1 + descend()

    report = descend.run()
    finding, = diagnose(report)
    outer, inner = report.nodes[:2]

    assert report.value == 2
    assert finding["kind"] == "active_path_reentry"
    assert finding["call_ids"] == [outer.call_id, inner.call_id]
    assert finding["subproblem_id"] == outer.identity == inner.identity
    assert finding["facts"]["signature"] == inner.signature


def test_distinct_arguments_on_one_path_do_not_trigger_reentry():
    @trace
    def factorial(n):
        return 1 if n <= 1 else n * factorial(n - 1)

    assert diagnose(factorial.run(6)) == []


def test_partial_trace_reports_limits_beside_supported_findings():
    report = fib.with_options(max_calls=8).run(5)
    findings = diagnose(report)
    partial = findings[-1]

    assert findings[0]["kind"] == "repeated_subproblem"
    assert partial["kind"] == "partial_trace"
    assert partial["call_ids"] == []
    assert partial["subproblem_id"] is None
    assert partial["facts"] == {"recorded_calls": 8, "total_calls": 15}
