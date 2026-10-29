"""Graph artifacts retain AST identity, operand order, ports, and metadata."""

import json
import re
import xml.etree.ElementTree as ET

import pytest

from combhdl import (
    BitNot,
    CompileError,
    Component,
    Const,
    Expr,
    Input,
    Output,
    Xor,
    compile,
    emit_html,
)
from examples.combinational.ipv4_checksum import component as checksum
from examples.combinational.operations import operations
from examples.combinational.shared_logic import component as shared


def graph(component):
    text = emit_html(component)
    payload = re.search(
        r'<script type="application/json" id="graph-data">(.*?)</script>', text, re.S
    )
    svg = re.search(r"<svg .*?</svg>", text, re.S)
    assert payload and svg
    return text, json.loads(payload[1]), ET.fromstring(svg[0])


@pytest.mark.parametrize("component", [shared, checksum, operations(4)])
def test_nodes_and_connections_match_report(component):
    text, data, svg = graph(component)
    report = compile(component).report
    nodes = {node["id"]: node for node in data["nodes"]}
    for expected in report["nodes"]:
        actual = nodes[expected["id"]]
        for field in ("id", "kind", "width", "operands", "fanout"):
            assert actual[field] == expected[field]
        if actual["kind"] != "Input":
            assert actual["variable"] == "_combhdl_value_" + actual["id"][1:]
    assert len(nodes) == report["node_count"] + len(component.outputs)
    expected_edges = [
        (source, node["id"], i)
        for node in report["nodes"]
        for i, source in enumerate(node["operands"])
    ]
    expected_edges += [
        (output["node"], f"out{i}", 0) for i, output in enumerate(report["outputs"])
    ]
    assert [
        (edge["source"], edge["target"], edge["operand"]) for edge in data["edges"]
    ] == expected_edges
    ids = [element.attrib["id"] for element in svg.iter() if "id" in element.attrib]
    assert len(ids) == len(set(ids))
    assert set(nodes).issubset(ids)
    assert {edge["id"] for edge in data["edges"]}.issubset(ids)
    assert all(
        edge["source"] in nodes and edge["target"] in nodes for edge in data["edges"]
    )
    assert emit_html(component) == text
    assert text.endswith("\n")
    assert "@@" not in text
    assert "<script src=" not in text and "<link " not in text


def test_sharing_distinct_nodes_and_repeated_operand_edges():
    a = Input("a", 1)
    first, second = BitNot(a), BitNot(a)
    component = Component(
        "sharing", [a], [Output("x", Xor(first, first)), Output("y", second)]
    )
    _, data, _ = graph(component)
    assert sum(node["kind"] == "BitNot" for node in data["nodes"]) == 2
    xor = next(node for node in data["nodes"] if node["kind"] == "Xor")
    edges = [edge for edge in data["edges"] if edge["target"] == xor["id"]]
    assert len(edges) == 2
    assert edges[0]["source"] == edges[1]["source"]
    assert [edge["role"] for edge in edges] == ["a", "b"]


def test_unused_inputs_direct_outputs_and_constant_only():
    a, unused = Input("a$b", 3), Input("unused", 1)
    _, data, _ = graph(Component("ports$", [a, unused], [Output("direct$", a)]))
    assert [(node["variable"], node["kind"]) for node in data["nodes"]] == [
        ("a$b", "Input"),
        ("unused", "Unused input"),
        ("direct$", "Output"),
    ]
    assert data["nodes"][1]["fanout"] == 0
    assert len(data["edges"]) == 1
    _, data, _ = graph(
        Component("constant_only", [], [Output("result", Const(255, 8))])
    )
    assert [node["kind"] for node in data["nodes"]] == ["Const", "Output"]


def test_operand_roles_and_parameters():
    _, data, _ = graph(operations(4))
    select = next(node for node in data["nodes"] if node["kind"] == "If")
    assert select["roles"] == ["condition", "true", "false"]
    concat = next(node for node in data["nodes"] if node["kind"] == "Concat")
    assert concat["roles"] == ["bits 8:5", "bits 4:1", "bits 0:0"]
    # All operation parameters, including large constants, are lossless strings.
    _, data, _ = graph(
        Component("wide", [], [Output("result", Const(1 << 16000, 16001))])
    )
    assert hex(1 << 16000) in data["nodes"][0]["expression"]


def test_deep_graph_is_iterative():
    a = Input("a", 1)
    result = a
    for _ in range(5000):
        result = BitNot(result)
    text, data, _ = graph(Component("deep", [a], [Output("result", result)]))
    assert len(data["nodes"]) == 5002
    assert len(data["edges"]) == 5001
    assert len(text) < 10_000_000


def test_invalid_graphs():
    a = Input("a", 1)
    loop = BitNot(a)
    object.__setattr__(loop, "operands", (loop,))
    for expression in (loop, Input("other", 1), Expr("Register", (), (), 1)):
        with pytest.raises(CompileError):
            emit_html(Component("invalid", [a], [Output("result", expression)]))
