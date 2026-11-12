from __future__ import annotations

import html
from collections import defaultdict
from typing import Dict, List, Tuple

from ._model import DAGNode

_CSS = """
.rl-wrap{--rl-blue:#185fa5;--rl-blue-bg:#e6f1fb;--rl-coral:#d85a30;--rl-coral-bg:#faece7;--rl-green:#0f6e56;--rl-green-bg:#e1f5ee;--rl-text:#242424;--rl-muted:#66645f;--rl-border:#dedcd5;color:var(--rl-text);background:#fff;border:1px solid var(--rl-border);border-radius:12px;padding:18px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.5;box-sizing:border-box;margin:8px 0;max-width:100%;overflow:auto}
.rl-wrap *{box-sizing:border-box}.rl-title{font-size:18px;font-weight:600;margin:0 0 4px}.rl-subtitle{color:var(--rl-muted);font-size:13px;margin:0 0 16px}.rl-metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(105px,1fr));gap:8px;margin:12px 0 18px}.rl-metric{background:#f6f5f1;border-radius:8px;padding:10px}.rl-metric-label{font-size:11px;color:var(--rl-muted)}.rl-metric-value{font-size:21px;font-weight:600;margin-top:2px}.rl-section{font-size:14px;font-weight:600;margin:18px 0 8px}.rl-tree,.rl-tree ul{list-style:none;padding-left:20px}.rl-tree{padding-left:0}.rl-tree details{margin:4px 0}.rl-tree summary{cursor:pointer;padding:5px 8px;border-radius:6px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}.rl-tree summary:hover{background:var(--rl-blue-bg)}.rl-result{color:var(--rl-muted);font-size:11px;margin-left:6px}.rl-badge{display:inline-block;border-radius:4px;padding:1px 5px;margin-left:5px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:10px;font-weight:500}.rl-repeat{color:#993c1d;background:var(--rl-coral-bg)}.rl-cached{color:var(--rl-green);background:var(--rl-green-bg)}.rl-error{color:#a32d2d;background:#fcebeb}.rl-warning{color:#854f0b;background:#faeeda;border-radius:6px;padding:8px;margin:8px 0;font-size:12px}.rl-dag{max-width:100%;overflow:auto;background:#fafaf8;border-radius:8px;padding:8px}.rl-legend{font-size:11px;color:var(--rl-muted);margin:6px 0}.rl-table{border-collapse:collapse;width:100%;font-size:12px;margin:8px 0 16px}.rl-table th,.rl-table td{text-align:right;border-bottom:1px solid var(--rl-border);padding:8px}.rl-table th:first-child,.rl-table td:first-child{text-align:left}.rl-table th{color:var(--rl-muted);font-weight:500}.rl-delta-up{color:#a32d2d}.rl-delta-down{color:var(--rl-green)}.rl-columns{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}.rl-note{font-size:12px;color:var(--rl-muted)}
"""


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def short(value: str, limit: int = 34) -> str:
    return value if len(value) <= limit else value[: limit - 3] + "..."


def metric_cards(report) -> str:
    metrics = [
        ("Observed calls", report.total_calls),
        ("Executed bodies", report.executed_calls),
        ("Cache hits", report.cached_calls),
        ("Unique subproblems", report.unique_subproblems),
        ("Repeated calls", report.repeated_calls),
        ("Maximum depth", report.max_depth),
    ]
    cards = "".join(
        f'<div class="rl-metric"><div class="rl-metric-label">{esc(label)}</div>'
        f'<div class="rl-metric-value">{esc(value)}</div></div>'
        for label, value in metrics
    )
    return f'<div class="rl-metrics">{cards}</div>'


def report_header(report) -> str:
    mode = "memoized" if report.memoize else "naive"
    if report.succeeded:
        outcome = f"returned <code>{esc(report.result)}</code>"
    else:
        outcome = f"raised <code>{esc(report.error)}</code>"
    warnings = "".join(
        f'<div class="rl-warning">{esc(message)}</div>' for message in report.warnings
    )
    if report.truncated:
        warnings += (
            '<div class="rl-warning">The recording limit was reached. '
            "Tree and DAG metrics only include recorded nodes; observed calls still counts every call.</div>"
        )
    return (
        f'<h2 class="rl-title">RecursionLens · {esc(report.function_name)}</h2>'
        f'<p class="rl-subtitle">{mode} run · {outcome}</p>'
        + metric_cards(report)
        + warnings
    )


def render_tree_node(node) -> str:
    badges = ""
    if node.repeated:
        badges += '<span class="rl-badge rl-repeat">repeated</span>'
    if node.cached:
        badges += '<span class="rl-badge rl-cached">cache hit</span>'
    if node.status == "error":
        badges += '<span class="rl-badge rl-error">error</span>'

    outcome = ""
    if node.result is not None:
        outcome = f'<span class="rl-result">→ {esc(short(node.result, 60))}</span>'
    elif node.error is not None:
        outcome = f'<span class="rl-result">{esc(short(node.error, 60))}</span>'

    open_attr = " open" if node.depth <= 2 else ""
    children = ""
    if node.children:
        children = "<ul>" + "".join(render_tree_node(child) for child in node.children) + "</ul>"
    return (
        f"<li><details{open_attr}><summary>{esc(short(node.signature, 90))}"
        f"{badges}{outcome}</summary>{children}</details></li>"
    )


def render_tree(report) -> str:
    roots = "".join(render_tree_node(root) for root in report.roots)
    return (
        '<h3 class="rl-section">Call tree</h3>'
        '<div class="rl-legend">Each node is one invocation. Expand a node to inspect its children.</div>'
        f'<ul class="rl-tree">{roots}</ul>'
    )


def dag_depths(nodes: List[DAGNode]) -> Dict[str, int]:
    children = {node.identity: node.children for node in nodes}
    known = set(children)
    memo: Dict[str, int] = {}

    def depth(identity: str, visiting: set) -> int:
        if identity in memo:
            return memo[identity]
        if identity in visiting:
            return 0
        next_nodes = [child for child in children.get(identity, []) if child in known]
        value = 0 if not next_nodes else 1 + max(depth(child, visiting | {identity}) for child in next_nodes)
        memo[identity] = value
        return value

    return {node.identity: depth(node.identity, set()) for node in nodes}


def render_dag(report) -> str:
    nodes = report.dag_nodes
    omitted = max(0, len(nodes) - 40)
    nodes = nodes[:40]
    known = {node.identity for node in nodes}
    depths = dag_depths(nodes)
    layers: Dict[int, List[DAGNode]] = defaultdict(list)
    for node in nodes:
        layers[depths[node.identity]].append(node)

    box_width, box_height = 190, 52
    horizontal_gap, vertical_gap = 235, 74
    positions: Dict[str, Tuple[float, float]] = {}
    maximum_depth = max(layers, default=0)
    for depth, layer in layers.items():
        for index, node in enumerate(layer):
            positions[node.identity] = (
                20 + (maximum_depth - depth) * horizontal_gap,
                30 + index * vertical_gap,
            )

    width = max(600, 40 + (max(layers, default=0) + 1) * horizontal_gap)
    height = max(130, 60 + max((len(layer) for layer in layers.values()), default=1) * vertical_gap)
    parts = [
        f'<svg role="img" aria-label="Subproblem DAG for {esc(report.function_name)}" '
        f'viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        'xmlns="http://www.w3.org/2000/svg">',
        "<defs><marker id=\"rl-arrow\" viewBox=\"0 0 10 10\" refX=\"8\" refY=\"5\" "
        'markerWidth="6" markerHeight="6" orient="auto"><path d="M2 1L8 5L2 9" '
        'fill="none" stroke="#888780" stroke-width="1.5"/></marker></defs>',
    ]

    for edge in report.dag_edges:
        source, target = edge["source"], edge["target"]
        if source not in known or target not in known:
            continue
        sx, sy = positions[source]
        tx, ty = positions[target]
        parts.append(
            f'<path d="M{sx + box_width},{sy + box_height / 2} L{tx - 8},{ty + box_height / 2}" '
            'fill="none" stroke="#888780" stroke-width="1" marker-end="url(#rl-arrow)"/>'
        )

    for node in nodes:
        x, y = positions[node.identity]
        if node.cached:
            fill, stroke, text = "#e1f5ee", "#0f6e56", "#085041"
        elif node.calls > 1:
            fill, stroke, text = "#faece7", "#d85a30", "#993c1d"
        else:
            fill, stroke, text = "#e6f1fb", "#185fa5", "#042c53"
        label = esc(short(node.signature, 29))
        count = f"calls {node.calls} · executed {node.executed} · cached {node.cached}"
        parts.extend(
            [
                f'<rect x="{x}" y="{y}" width="{box_width}" height="{box_height}" rx="8" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="1"/>',
                f'<text x="{x + 10}" y="{y + 20}" font-family="monospace" font-size="11" fill="{text}">{label}</text>',
                f'<text x="{x + 10}" y="{y + 39}" font-family="sans-serif" font-size="10" fill="{text}">{esc(count)}</text>',
            ]
        )
    parts.append("</svg>")

    notice = f'<p class="rl-note">Showing the first 40 subproblems; {omitted} omitted.</p>' if omitted else ""
    return (
        '<h3 class="rl-section">Subproblem DAG</h3>'
        '<div class="rl-legend">Identical argument signatures are merged. Coral = repeated; green = contains cache hits.</div>'
        f'<div class="rl-dag">{"".join(parts)}</div>{notice}'
    )


def render_report(report, mode: str = "tree") -> str:
    if mode not in {"tree", "dag"}:
        raise ValueError("mode must be 'tree' or 'dag'")
    body = render_tree(report) if mode == "tree" else render_dag(report)
    return f'<style>{_CSS}</style><section class="rl-wrap">{report_header(report)}{body}</section>'


def render_comparison(comparison) -> str:
    left, right = comparison.left, comparison.right
    left_metrics, right_metrics = left.metrics(), right.metrics()
    rows = []
    labels = {
        "total_calls": "Observed calls",
        "executed_calls": "Executed bodies",
        "cached_calls": "Cache hits",
        "unique_subproblems": "Unique subproblems",
        "repeated_calls": "Repeated calls",
        "max_depth": "Maximum depth",
    }
    for key, label in labels.items():
        delta = right_metrics[key] - left_metrics[key]
        delta_class = "rl-delta-down" if delta < 0 else "rl-delta-up" if delta > 0 else ""
        delta_text = f"{delta:+d}"
        rows.append(
            f"<tr><td>{esc(label)}</td><td>{left_metrics[key]}</td>"
            f"<td>{right_metrics[key]}</td><td class=\"{delta_class}\">{delta_text}</td></tr>"
        )

    same_result = "yes" if comparison.same_result else "no"
    return (
        f'<style>{_CSS}</style><section class="rl-wrap">'
        '<h2 class="rl-title">RecursionLens · execution comparison</h2>'
        f'<p class="rl-subtitle">{esc(comparison.labels[0])} vs {esc(comparison.labels[1])} · same returned value: {same_result}</p>'
        '<table class="rl-table"><thead><tr><th>Metric</th>'
        f'<th>{esc(comparison.labels[0])}</th><th>{esc(comparison.labels[1])}</th><th>Change</th>'
        '</tr></thead><tbody>' + "".join(rows) + '</tbody></table>'
        '<div class="rl-columns"><div>' + report_header(left) + render_dag(left) + '</div>'
        '<div>' + report_header(right) + render_dag(right) + '</div></div></section>'
    )


def render_document(fragment: str) -> str:
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>RecursionLens report</title></head><body style="margin:20px;background:#f6f5f1">'
        + fragment
        + "</body></html>"
    )
