"""Deterministic, self-contained HTML visualization of an expression DAG."""

from collections import Counter
from dataclasses import dataclass
from html import escape
import json
from pathlib import Path

from .compiler import validate
from .model import Component, Expr
from .python import python_rhs


@dataclass
class _Node:
    id: str
    kind: str
    width: int
    variable: str
    expression: str
    operands: list[str]
    roles: list[str]
    level: int
    x: float = 0
    y: int = 0
    fanout: int = 0


def _roles(node: Expr) -> list[str]:
    if node.kind == "If":
        return ["condition", "true", "false"]
    if node.kind == "Concat":
        low = node.width
        roles: list[str] = []
        for operand in node.operands:
            low -= operand.width
            roles.append(f"bits {low + operand.width - 1}:{low}")
        return roles
    if len(node.operands) == 2:
        return ["a", "b"]
    return ["value"] * len(node.operands)


def emit_html(component: Component) -> str:
    """Render a validated graph with shared nodes, ports, and ordered edges."""
    order = validate(component)
    ids = {node: f"n{i}" for i, node in enumerate(order)}
    refs = {
        node: node.name if node.kind == "Input" else f"_combhdl_value_{i}"
        for i, node in enumerate(order)
    }
    levels: dict[Expr, int] = {}
    nodes: list[_Node] = []
    for node in order:
        level = 1 + max((levels[operand] for operand in node.operands), default=-1)
        levels[node] = level
        expression = (
            f"{refs[node]} = {python_rhs(node, refs)}" if node.kind != "Input" else ""
        )
        if node.params and node.kind not in ("Input", "Const"):
            expression += "\nParameters: " + ", ".join(
                str(value) if value.bit_length() <= 64 else hex(value)
                for value in node.params
            )
        if node.kind == "Input":
            expression = f"Input({node.name!r}, width={node.width})"
        nodes.append(
            _Node(
                ids[node],
                node.kind,
                node.width,
                refs[node],
                expression,
                [ids[operand] for operand in node.operands],
                _roles(node),
                level,
            )
        )
    for i, port in enumerate(component.inputs):
        if port not in ids:
            nodes.append(
                _Node(
                    f"unused{i}",
                    "Unused input",
                    port.width,
                    port.name,
                    f"Input({port.name!r}, width={port.width}); unused",
                    [],
                    [],
                    0,
                )
            )
    output_level = 1 + max(node.level for node in nodes)
    for i, output in enumerate(component.outputs):
        nodes.append(
            _Node(
                f"out{i}",
                "Output",
                output.width,
                output.name,
                f"{output.name} = {refs[output.expression]}",
                [ids[output.expression]],
                ["result"],
                output_level,
            )
        )
    by_id = {node.id: node for node in nodes}
    fanout = Counter(operand for node in nodes for operand in node.operands)
    layers: dict[int, list[_Node]] = {}
    for node in nodes:
        node.fanout = fanout[node.id]
        layers.setdefault(node.level, []).append(node)
    columns = max(len(layer) for layer in layers.values())
    width = columns * 264 + 48
    height = (output_level + 1) * 172 + 48
    for level, layer in layers.items():
        # Place consumers near their producers, preserving deterministic ties.
        layer.sort(
            key=lambda node: (
                sum(by_id[operand].x for operand in node.operands)
                / max(1, len(node.operands))
            )
        )
        offset = (width - len(layer) * 264) / 2
        for i, node in enumerate(layer):
            node.x = offset + i * 264 + 20
            node.y = level * 172 + 24
    edges: list[dict[str, str | int]] = []
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" id="graph" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="group" aria-label="Expression dependency graph">',
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="context-stroke"/></marker></defs>',
    ]
    for node in nodes:
        for i, operand in enumerate(node.operands):
            source = by_id[operand]
            x1, y1 = source.x + 112, source.y + 96
            x2, y2 = node.x + (i + 1) * 224 / (len(node.operands) + 1), node.y
            mid = (y1 + y2) / 2
            edge_id = f"edge{len(edges)}"
            role = node.roles[i]
            edges.append(
                {
                    "id": edge_id,
                    "source": operand,
                    "target": node.id,
                    "operand": i,
                    "role": role,
                }
            )
            svg.append(
                f'<g class="edge" id="{edge_id}"><title>'
                f"{escape(source.variable)} → {escape(node.variable)}: {escape(role)}</title>"
                f'<path d="M {x1:g} {y1} C {x1:g} {mid:g}, {x2:g} {mid:g}, {x2:g} {y2}" '
                'marker-end="url(#arrow)"/>'
                f'<text x="{x2:g}" y="{y2 - 8}" text-anchor="middle">{escape(role)}</text></g>'
            )
    for node in nodes:
        category = (
            "input"
            if node.kind in ("Input", "Unused input")
            else (
                "output"
                if node.kind == "Output"
                else "constant"
                if node.kind == "Const"
                else "operation"
            )
        )
        svg.append(
            f'<g class="node {category}" id="{node.id}" transform="translate({node.x:g},{node.y})" '
            f'tabindex="0" role="button" aria-label="{escape(node.variable, quote=True)}: '
            f'{escape(node.kind)} {node.width} bits">'
            f"<title>{escape(node.variable)}: {escape(node.expression)}; {node.width} bits</title>"
            '<rect width="224" height="96" rx="12"/>'
            f'<text class="meta" x="14" y="22">{node.id} · {node.width} bits'
            f"{' · shared' if node.fanout > 1 else ''}</text>"
            f'<text class="kind" x="14" y="49">{escape(node.kind)}</text>'
            f'<text class="variable" x="14" y="76">{escape(node.variable)}</text></g>'
        )
    svg.append("</svg>")
    data = {
        "width": width,
        "height": height,
        "nodes": [
            dict(
                id=node.id,
                kind=node.kind,
                width=node.width,
                variable=node.variable,
                expression=node.expression,
                operands=node.operands,
                roles=node.roles,
                fanout=node.fanout,
            )
            for node in nodes
        ],
        "edges": edges,
    }
    # Keep embedded JSON inert even if a future naming rule permits HTML delimiters.
    payload = (
        json.dumps(data, ensure_ascii=True, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    template = Path(__file__).with_name("graph.html").read_text(encoding="utf-8")
    return (
        template.replace("@@TITLE@@", escape(component.name))
        .replace(
            "@@SUMMARY@@",
            f"{len(order)} expression nodes · {len(component.inputs)} inputs · {len(component.outputs)} outputs · {len(edges)} connections",
        )
        .replace("@@SVG@@", "\n".join(svg))
        .replace("@@DATA@@", payload)
    )
