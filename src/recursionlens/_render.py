from __future__ import annotations

import html
import re
from collections import defaultdict
from typing import Dict, List, Tuple

from ._model import DAGNode

_CSS = """
.rl-wrap{--rl-blue:#185fa5;--rl-blue-bg:#e6f1fb;--rl-coral:#d85a30;--rl-coral-bg:#faece7;--rl-green:#0f6e56;--rl-green-bg:#e1f5ee;--rl-text:#242424;--rl-muted:#66645f;--rl-border:#dedcd5;color:var(--rl-text);background:#fff;border:1px solid var(--rl-border);border-radius:12px;padding:18px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.5;box-sizing:border-box;margin:8px 0;max-width:100%;overflow:auto}
.rl-wrap *{box-sizing:border-box}.rl-title{font-size:18px;font-weight:600;margin:0 0 4px}.rl-subtitle{color:var(--rl-muted);font-size:13px;margin:0 0 16px}.rl-metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(105px,1fr));gap:8px;margin:12px 0 18px}.rl-metric{background:#f6f5f1;border-radius:8px;padding:10px}.rl-metric-label{font-size:11px;color:var(--rl-muted)}.rl-metric-value{font-size:21px;font-weight:600;margin-top:2px}.rl-section{font-size:14px;font-weight:600;margin:18px 0 8px}.rl-tree,.rl-tree ul{list-style:none;padding-left:18px}.rl-tree{padding-left:0}.rl-tree ul{border-left:1px solid #eae7de;margin-left:8px}.rl-tree details{margin:2px 0}.rl-tree summary{cursor:pointer;padding:6px 9px;border-radius:7px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px;color:#2b2a26}.rl-tree summary:hover{background:#f4f2ec}.rl-result{color:var(--rl-muted);font-size:11px;margin-left:6px}.rl-badge{display:inline-block;border-radius:4px;padding:1px 5px;margin-left:5px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:10px;font-weight:500}.rl-repeat{color:#993c1d;background:var(--rl-coral-bg)}.rl-cached{color:var(--rl-green);background:var(--rl-green-bg)}.rl-error{color:#a32d2d;background:#fcebeb}.rl-warning{color:#854f0b;background:#faeeda;border-radius:6px;padding:8px;margin:8px 0;font-size:12px}.rl-dag{max-width:100%;overflow:auto;background:#fafaf8;border-radius:8px;padding:8px}.rl-legend{font-size:11px;color:var(--rl-muted);margin:6px 0}.rl-table{border-collapse:collapse;width:100%;font-size:12px;margin:8px 0 16px}.rl-table th,.rl-table td{text-align:right;border-bottom:1px solid var(--rl-border);padding:8px}.rl-table th:first-child,.rl-table td:first-child{text-align:left}.rl-table th{color:var(--rl-muted);font-weight:500}.rl-delta-up{color:#a32d2d}.rl-delta-down{color:var(--rl-green)}.rl-columns{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}.rl-note{font-size:12px;color:var(--rl-muted)}.rl-expanded{max-width:100%;overflow:auto;background:#fbfaf6;border:1px solid #efede5;border-radius:10px;padding:12px}.rl-expanded svg{display:block;margin:auto}
"""


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def short(value: str, limit: int = 34) -> str:
    return value if len(value) <= limit else value[: limit - 3] + "..."


def compact_call(signature: str, limit: int = 18) -> str:
    """Remove parameter names for the compact SVG tree while keeping values."""

    if "(" not in signature or not signature.endswith(")"):
        return short(signature, limit)
    name, arguments = signature.split("(", 1)
    arguments = arguments[:-1]
    arguments = re.sub(r"(^|, )([A-Za-z_]\w*)=", r"\1", arguments)
    return short(f"{name}({arguments})", limit)


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


def _call_attributes(node) -> str:
    return f' data-call-id="{node.call_id}" data-subproblem-id="{esc(node.identity)}"'


def render_tree_node(node, *, interactive: bool = False) -> str:
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
        children = "<ul>" + "".join(
            render_tree_node(child, interactive=interactive) for child in node.children
        ) + "</ul>"
    selection = _call_attributes(node) if interactive else ""
    return (
        f"<li><details{open_attr}><summary{selection}>{esc(short(node.signature, 90))}"
        f"{badges}{outcome}</summary>{children}</details></li>"
    )


def render_tree(report, *, interactive: bool = False) -> str:
    roots = "".join(render_tree_node(root, interactive=interactive) for root in report.roots)
    return (
        '<h3 class="rl-section">Call tree</h3>'
        '<div class="rl-legend">Each node is one invocation. Expand a node to inspect its children.</div>'
        f'<ul class="rl-tree">{roots}</ul>'
    )


def _mono_width(text: str, size: float = 12.0) -> float:
    """Approximate the advance width of monospace text at a given size."""

    return len(text) * size * 0.6


def _node_style(node) -> Tuple[str, str, str, str, str]:
    """Return fill, stroke, dot colour, label colour, and dash pattern."""

    if node.cached:
        return "#eaf6f0", "#9ecbb9", "#0f6e56", "#0b5c48", ""
    if node.status == "error":
        return "#fdecec", "#e3a6a6", "#a32d2d", "#a32d2d", ""
    if node.repeated:
        return "#fdf1ec", "#e4b3a2", "#d85a30", "#993c1d", ' stroke-dasharray="4 3"'
    return "#ffffff", "#d8d5cc", "#185fa5", "#242424", ""


def render_expanded_tree(report, limit: int = 120, *, interactive: bool = False) -> str:
    """Render every selected invocation as a compact, fully visible SVG tree."""

    selected = []
    child_lists = {}
    remaining = [limit]

    def collect(node) -> bool:
        if remaining[0] <= 0:
            return False
        selected.append(node)
        remaining[0] -= 1
        child_lists[id(node)] = []
        for child in node.children:
            if collect(child):
                child_lists[id(node)].append(child)
        return True

    for root in report.roots:
        collect(root)

    labels = {id(node): compact_call(node.signature) for node in selected}
    widths = {
        id(node): max(62.0, min(210.0, _mono_width(labels[id(node)]) + 30))
        for node in selected
    }

    node_height = 38.0
    level_gap = 92.0
    sibling_gap = 26.0
    positions: Dict[int, Tuple[float, float]] = {}
    cursor = [0.0]
    maximum_depth = 0

    def place(node, depth: int) -> None:
        nonlocal maximum_depth
        maximum_depth = max(maximum_depth, depth)
        children = child_lists[id(node)]
        if not children:
            x = cursor[0] + widths[id(node)] / 2
            cursor[0] = x + widths[id(node)] / 2 + sibling_gap
        else:
            for child in children:
                place(child, depth + 1)
            first_x = positions[id(children[0])][0]
            last_x = positions[id(children[-1])][0]
            x = (first_x + last_x) / 2
        positions[id(node)] = (x, 30 + depth * level_gap)

    for root in report.roots:
        if id(root) in child_lists:
            place(root, 0)

    content_width = max(0.0, cursor[0] - sibling_gap)
    width = max(640.0, content_width + 64)
    shift = (width - content_width) / 2
    if shift:
        positions = {
            node_id: (x + shift, y) for node_id, (x, y) in positions.items()
        }
    height = max(140.0, 30 + maximum_depth * level_gap + node_height / 2 + 28)
    role = "group" if interactive else "img"
    parts = [
        f'<svg role="{role}" aria-label="Fully expanded recursion tree for {esc(report.function_name)}" '
        f'viewBox="0 0 {width:.0f} {height:.0f}" width="{width:.0f}" height="{height:.0f}" '
        'xmlns="http://www.w3.org/2000/svg">',
        f"<title>{esc(report.function_name)} expanded call tree</title>",
    ]

    for parent in selected:
        parent_x, parent_y = positions[id(parent)]
        for child in child_lists[id(parent)]:
            child_x, child_y = positions[id(child)]
            start_y = parent_y + node_height / 2
            end_y = child_y - node_height / 2
            middle = (start_y + end_y) / 2
            selection = ""
            if interactive:
                selection = (
                    f' data-parent-call-id="{parent.call_id}" data-child-call-id="{child.call_id}"'
                )
            parts.append(
                f'<path class="rl-expanded-edge"{selection} d="M{parent_x:.1f},{start_y:.1f} '
                f'C{parent_x:.1f},{middle:.1f} {child_x:.1f},{middle:.1f} '
                f'{child_x:.1f},{end_y:.1f}" fill="none" stroke="#c6c3ba" '
                'stroke-width="1.2"/>'
            )

    for node in selected:
        x, y = positions[id(node)]
        fill, stroke, dot, ink, dash = _node_style(node)
        note = [node.signature]
        if node.cached:
            note.append("cache hit")
        elif node.status == "error":
            note.append(node.error or "error")
        elif node.repeated:
            note.append("repeated")
        if node.result is not None:
            note.append(f"returned {node.result}")

        if node.status == "error":
            value = "error"
        elif node.result is not None:
            value = f"→ {node.result}"
        else:
            value = ""

        left = x - widths[id(node)] / 2
        if value:
            label_y = y - 2
            value_y = y + 12
        else:
            label_y = y + 4.3
            value_y = None

        selection = _call_attributes(node) if interactive else ""
        parts.append(f'<g class="rl-expanded-node"{selection}><title>{esc(" · ".join(note))}</title>')
        parts.append(
            f'<rect x="{left:.1f}" y="{y - node_height / 2:.1f}" '
            f'width="{widths[id(node)]:.1f}" height="{node_height:.1f}" rx="9" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="1"{dash}/>'
        )
        parts.append(
            f'<circle cx="{left + 11:.1f}" cy="{y:.1f}" r="3" fill="{dot}"/>'
        )
        parts.append(
            f'<text x="{left + 20:.1f}" y="{label_y:.1f}" '
            f'font-family="ui-monospace,SFMono-Regular,Menlo,monospace" font-size="12" '
            f'fill="{ink}">{esc(labels[id(node)])}</text>'
        )
        if value_y is not None:
            parts.append(
                f'<text x="{left + 20:.1f}" y="{value_y:.1f}" '
                'font-family="-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif" '
                f'font-size="10" fill="#7a776e">{esc(short(value, 22))}</text>'
            )
        parts.append("</g>")
    parts.append("</svg>")

    omitted = report.recorded_calls - len(selected)
    notice = (
        f'<p class="rl-note">Showing the first {limit} calls; {omitted} omitted.</p>'
        if omitted > 0
        else ""
    )
    return (
        '<h3 class="rl-section">Expanded call tree</h3>'
        f'<div class="rl-legend">All {len(selected)} calls are visible. '
        "White = executed · dashed coral = repeated · green = cache hit · red = error.</div>"
        f'<div class="rl-expanded">{"".join(parts)}</div>{notice}'
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


def render_dag(report, *, interactive: bool = False) -> str:
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
    role = "group" if interactive else "img"
    arrow = "rl-explorer-arrow" if interactive else "rl-arrow"
    parts = [
        f'<svg role="{role}" aria-label="Subproblem DAG for {esc(report.function_name)}" '
        f'viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        'xmlns="http://www.w3.org/2000/svg">',
        f'<defs><marker id="{arrow}" viewBox="0 0 10 10" refX="8" refY="5" '
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
            f'fill="none" stroke="#888780" stroke-width="1" marker-end="url(#{arrow})"/>'
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
        if interactive:
            parts.append(
                f'<g data-subproblem-id="{esc(node.identity)}"><title>{esc(node.signature)}</title>'
            )
        parts.extend(
            [
                f'<rect x="{x}" y="{y}" width="{box_width}" height="{box_height}" rx="8" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="1"/>',
                f'<text x="{x + 10}" y="{y + 20}" font-family="monospace" font-size="11" fill="{text}">{label}</text>',
                f'<text x="{x + 10}" y="{y + 39}" font-family="sans-serif" font-size="10" fill="{text}">{esc(count)}</text>',
            ]
        )
        if interactive:
            parts.append("</g>")
    parts.append("</svg>")

    notice = f'<p class="rl-note">Showing the first 40 subproblems; {omitted} omitted.</p>' if omitted else ""
    return (
        '<h3 class="rl-section">Subproblem DAG</h3>'
        '<div class="rl-legend">Identical argument signatures are merged. Coral = repeated; green = contains cache hits.</div>'
        f'<div class="rl-dag">{"".join(parts)}</div>{notice}'
    )


def render_report(report, mode: str = "tree", *, interactive: bool = False) -> str:
    views = {"tree": render_tree, "dag": render_dag, "expanded": render_expanded_tree}
    if mode not in views:
        raise ValueError("mode must be 'tree', 'dag', or 'expanded'")
    body = views[mode](report, interactive=interactive)
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
        f'<div class="rl-compare-block"><h3 class="rl-section">{esc(comparison.labels[0])}</h3>'
        + report_header(left)
        + render_dag(left)
        + '</div>'
        f'<div class="rl-compare-block"><h3 class="rl-section">{esc(comparison.labels[1])}</h3>'
        + report_header(right)
        + render_dag(right)
        + '</div></section>'
    )


def render_document(fragment: str) -> str:
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>RecursionLens report</title></head><body style="margin:20px;background:#f6f5f1">'
        + fragment
        + "</body></html>"
    )
