"""Independent byte-oriented checksum oracle and known/boundary vectors."""

import pytest

from combhdl import CompileError, Component, Const, Output, compile, evaluate
from examples.combinational.ipv4_checksum import component, fold_sum16, wide_sum
from tools.check_checksum import cases, reference


def test_known_checksums():
    ipv4 = int("450000730000400040110000c0a80001c0a800c7", 16)
    rfc = int.from_bytes(bytes.fromhex("0001f203f4f5f6f7") + bytes(12), "big")
    assert evaluate(component, {"header": ipv4}) == {"checksum": 0xB861, "valid": 0}
    assert evaluate(component, {"header": rfc})["checksum"] == 0x220D


def test_header_vectors():
    for inputs, outputs in cases():
        assert evaluate(component, inputs) == outputs


@pytest.mark.parametrize(
    "value", [0, 1, 0xFFFF, 0x10000, 0x1FFFF, 0xFFFF0000, 0xFFFFFFFF]
)
def test_end_around_carry(value):
    circuit = Component("fold", [], [Output("result", fold_sum16(Const(value, 32)))])
    folded = evaluate(circuit, {})["result"]
    oracle = 0xFFFF ^ reference(value.to_bytes(4, "big"))
    assert folded == oracle


def test_helper_reuse_and_sharing():
    report = compile(component).report
    assert report["operation_counts"]["Input"] == 1
    assert report["node_count"] > 50
    assert any(
        node["kind"] == "Add" and node["fanout"] == 3 for node in report["nodes"]
    )
    for width in (15, 33):
        with pytest.raises(CompileError):
            fold_sum16(Const(0, width))
    with pytest.raises(CompileError):
        wide_sum([])
    with pytest.raises(CompileError):
        wide_sum([Const(0, 8), Const(0, 16)])
