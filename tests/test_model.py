"""Unit tests for the data models in :mod:`recursionlens._model`.

These tests exercise :class:`CallNode`, :class:`DAGNode`, and :func:`build_dag`
directly, without going through the ``trace`` decorator.
"""

from recursionlens._model import CallNode, DAGNode, build_dag


# -- CallNode -----------------------------------------------------------------

def test_call_node_cached_property_reflects_status():
    node = CallNode(call_id=0, identity="id", signature="fib(n=5)", depth=0, status="cached")
    assert node.cached is True

    node.status = "returned"
    assert node.cached is False


def test_call_node_to_dict_round_trips_children():
    parent = CallNode(call_id=0, identity="a", signature="f(0)", depth=0, status="returned", result="1")
    child = CallNode(call_id=1, identity="b", signature="f(1)", depth=1, status="returned", result="2")
    parent.children.append(child)

    data = parent.to_dict()
    assert data["call_id"] == 0
    assert data["identity"] == "a"
    assert data["status"] == "returned"
    assert data["result"] == "1"
    assert data["children"][0]["call_id"] == 1


def test_call_node_defaults():
    node = CallNode(call_id=0, identity="x", signature="x()", depth=0)
    assert node.status == "running"
    assert node.result is None
    assert node.error is None
    assert node.repeated is False
    assert node.children == []


# -- DAGNode ------------------------------------------------------------------

def test_dag_node_to_dict_includes_counts():
    node = DAGNode(identity="id", signature="fib(n=3)", calls=3, executed=2, cached=1, result="2")
    node.children.append("child_id")

    data = node.to_dict()
    assert data["identity"] == "id"
    assert data["calls"] == 3
    assert data["executed"] == 2
    assert data["cached"] == 1
    assert data["result"] == "2"
    assert data["children"] == ["child_id"]


def test_dag_node_defaults():
    node = DAGNode(identity="id", signature="sig")
    assert node.calls == 0
    assert node.executed == 0
    assert node.cached == 0
    assert node.result is None
    assert node.children == []


# -- build_dag ----------------------------------------------------------------

def _make_tree():
    """Build a small call tree: fib(2) → fib(1), fib(0).

    fib(2) and fib(1) each appear once; fib(0) appears once.
    Returns the root node.
    """
    root = CallNode(call_id=0, identity="0:fib(2)", signature="fib(n=2)", depth=0, status="returned", result="1")
    child_a = CallNode(call_id=1, identity="1:fib(1)", signature="fib(n=1)", depth=1, status="returned", result="1")
    child_b = CallNode(call_id=2, identity="2:fib(0)", signature="fib(n=0)", depth=1, status="returned", result="0")
    root.children = [child_a, child_b]
    return root


def test_build_dag_merges_repeated_subproblems():
    root = _make_tree()
    # Add a second fib(1) call under a new root
    root2 = CallNode(call_id=3, identity="0:fib(2)", signature="fib(n=2)", depth=0, status="returned", result="1")
    repeat_child = CallNode(call_id=4, identity="1:fib(1)", signature="fib(n=1)", depth=1, status="returned", result="1")
    root2.children = [repeat_child]

    dag_nodes, edges = build_dag([root, root2])

    node_map = {n.identity: n for n in dag_nodes}
    assert node_map["1:fib(1)"].calls == 2
    assert node_map["1:fib(1)"].executed == 2
    assert node_map["0:fib(2)"].calls == 2


def test_build_dag_edges_are_sorted_and_deduplicated():
    root = _make_tree()
    dag_nodes, edges = build_dag([root])

    # Edges should be sorted lexicographically by (source, target)
    pairs = [(e["source"], e["target"]) for e in edges]
    assert pairs == sorted(pairs)
    assert len(pairs) == len(set(pairs))  # no duplicates


def test_build_dag_empty_input():
    dag_nodes, edges = build_dag([])
    assert dag_nodes == []
    assert edges == []


def test_build_dag_single_node():
    root = CallNode(call_id=0, identity="a", signature="f()", depth=0, status="returned", result="42")
    dag_nodes, edges = build_dag([root])

    assert len(dag_nodes) == 1
    assert dag_nodes[0].calls == 1
    assert dag_nodes[0].executed == 1
    assert edges == []


def test_build_dag_counts_cached_calls():
    root = CallNode(call_id=0, identity="a", signature="f(n=3)", depth=0, status="returned", result="2")
    child_cached = CallNode(call_id=1, identity="b", signature="f(n=1)", depth=1, status="cached", result="1")
    child_executed = CallNode(call_id=2, identity="b", signature="f(n=1)", depth=1, status="returned", result="1")
    root.children = [child_cached, child_executed]

    dag_nodes, _ = build_dag([root])
    b = next(n for n in dag_nodes if n.identity == "b")
    assert b.calls == 2
    assert b.cached == 1
    assert b.executed == 1


def test_build_dag_preserves_first_result():
    root = CallNode(call_id=0, identity="a", signature="f()", depth=0, status="returned", result="first")
    root2 = CallNode(call_id=1, identity="a", signature="f()", depth=0, status="returned", result="second")
    dag_nodes, _ = build_dag([root, root2])

    assert dag_nodes[0].result == "first"


def test_build_dag_children_are_deduplicated():
    root = CallNode(call_id=0, identity="a", signature="f(n=2)", depth=0, status="returned", result="1")
    c1 = CallNode(call_id=1, identity="b", signature="f(n=1)", depth=1, status="returned", result="1")
    c2 = CallNode(call_id=2, identity="b", signature="f(n=1)", depth=1, status="returned", result="1")
    c3 = CallNode(call_id=3, identity="c", signature="f(n=0)", depth=1, status="returned", result="0")
    root.children = [c1, c2, c3]

    dag_nodes, _ = build_dag([root])
    a = next(n for n in dag_nodes if n.identity == "a")
    assert a.children == ["b", "c"]  # b appears once despite two children
