from dataclasses import FrozenInstanceError
import itertools
import json
from pathlib import Path
import subprocess
import sys

import pytest

from combhdl import (
    Add,
    And,
    Bit,
    BitNot,
    CompileError,
    Component,
    Concat,
    Const,
    Eq,
    Expr,
    If,
    Input,
    Not,
    Output,
    Shl,
    Shr,
    Slice,
    Truncate,
    Xor,
    ZeroExtend,
    compile,
    evaluate,
)
from examples.combinational.operations import expected, operations


@pytest.mark.parametrize("width", [1, 4, 11])
def test_semantics(width):
    circuit = operations(width)
    values = range(1 << width) if width <= 4 else [0, 1, 1023, 1024, 2046, 2047]
    for a, b, c in itertools.product(values, values, range(2)):
        assert evaluate(circuit, {"a": a, "b": b, "c": c}) == expected(width, a, b, c)


@pytest.mark.parametrize("width", [0, -1, True, 1.5, "8"])
def test_bad_width(width):
    with pytest.raises(CompileError):
        Input("a", width)


@pytest.mark.parametrize(
    "value,width", [(-1, 8), (256, 8), (True, 1), (1.2, 2), (0, 0)]
)
def test_bad_constant(value, width):
    with pytest.raises(CompileError):
        Const(value, width)


@pytest.mark.parametrize(
    "name", ["", "1a", "a-b", "module", "wire", "always_comb", "_combhdl_0", "a\\b"]
)
def test_bad_name(name):
    with pytest.raises(CompileError):
        Input(name, 1)


@pytest.mark.parametrize(
    "make",
    [
        lambda a, b: Add(a, b),
        lambda a, b: And(a, b),
        lambda a, b: Eq(a, b),
        lambda a, b: If(a, a, a),
        lambda a, b: If(Const(0, 1), a, b),
        lambda a, b: Not(a),
        lambda a, b: Bit(a, 4),
        lambda a, b: Bit(a, -1),
        lambda a, b: Slice(a, 3, 2),
        lambda a, b: Slice(a, 0, 0),
        lambda a, b: Shl(a, -1),
        lambda a, b: Shr(a, True),
        lambda a, b: ZeroExtend(a, 3),
        lambda a, b: Truncate(a, 5),
        lambda a, b: Concat(),
        lambda a, b: Xor(a, 1),
    ],
)
def test_bad_operations(make):
    with pytest.raises(CompileError):
        make(Input("a", 4), Input("b", 5))


def test_interface_validation():
    a, unused = Input("a", 1), Input("unused", 1)
    cases = [
        Component("empty", [a], []),
        Component("module", [a], [Output("out", a)]),
        Component("case1", [a, a], [Output("out", a)]),
        Component("case1", [a], [Output("a", a)]),
        Component("case1", [a], [Output("out", a), Output("out", a)]),
        Component("case1", [Const(0, 1)], [Output("out", a)]),
        Component("case1", [a], [Output("wire", a)]),
        Component("case1", [], [Output("out", a)]),
        Component("case1", [a], [Output("out", Input("a", 1))]),
        Component("case1", [a], [Output("out", object())]),
        Component("case1", [a], [Output("out", Expr("Register", (), (), 1))]),
        # A constant condition cannot hide undeclared or unsupported branches.
        Component("case1", [a], [Output("out", If(Const(1, 1), a, unused))]),
    ]
    for circuit in cases:
        with pytest.raises(CompileError, match="component"):
            compile(circuit)
    object.__setattr__(unused, "name", "wire")
    with pytest.raises(CompileError, match="input"):
        compile(Component("valid", [a, unused], [Output("out", a)]))


def test_cycles_and_forged_widths():
    a = Input("a", 1)
    loop = BitNot(a)
    object.__setattr__(loop, "operands", (loop,))
    with pytest.raises(CompileError, match="output 'out'.*cyclic"):
        compile(Component("cyclic", [a], [Output("out", loop)]))
    broken = BitNot(a)
    object.__setattr__(broken, "width", 2)
    with pytest.raises(CompileError, match="width"):
        compile(Component("broken", [a], [Output("out", broken)]))


def test_immutable_sharing_helpers_and_deep_graph():
    a, unused = Input("a", 1), Input("unused", 1)
    with pytest.raises(FrozenInstanceError):
        a.width = 2
    with pytest.raises(CompileError, match="truth"):
        bool(a)
    ports, outputs = [a, unused], [Output("out", Xor(a, a))]
    circuit = Component("test", ports, outputs)
    ports.clear()
    outputs.clear()
    result = compile(circuit)
    assert len(circuit.inputs) == 2 and len(circuit.outputs) == 1
    assert result.warnings[0]["port"] == "unused"
    assert result.report["operation_counts"] == {"Input": 1, "Xor": 1}
    assert result.report["nodes"][0]["fanout"] == 2

    def helper(value):
        return BitNot(value)

    same = helper(a)
    both = Component(
        "sharing", [a], [Output("x", Xor(same, same)), Output("y", helper(a))]
    )
    assert compile(both).report["operation_counts"]["BitNot"] == 2
    deep = a
    for _ in range(5000):
        deep = BitNot(deep)
    circuit = Component("deep", [a], [Output("out", deep)])
    assert evaluate(circuit, {"a": 1}) == {"out": 1}
    assert compile(circuit).report["node_count"] == 5001


def test_input_ranges_and_constant_only():
    a = Input("a", 3)
    circuit = Component("range_test", [a], [Output("out", a)])
    for inputs in ({}, {"b": 0}, {"a": -1}, {"a": 8}, {"a": True}, {"a": 0, "b": 0}):
        with pytest.raises(CompileError):
            evaluate(circuit, inputs)
    constant = Component("constant_test", [], [Output("out", Const(513, 10))])
    assert evaluate(constant, {}) == {"out": 513}
    assert "10'h201" in compile(constant).verilog


def test_cli_deterministic(tmp_path):
    root = Path(__file__).resolve().parents[2]
    for dest in ("first", "second"):
        subprocess.run(
            [
                sys.executable,
                "-m",
                "combhdl",
                "examples/combinational/shared_logic.py",
                "--output",
                str(tmp_path / dest),
            ],
            cwd=root,
            check=True,
        )
    for file in ("example.v", "interface.json", "report.json", "ast.txt", "model.py"):
        assert (tmp_path / "first" / file).read_bytes() == (
            tmp_path / "second" / file
        ).read_bytes()
    stdout = subprocess.run(
        [
            sys.executable,
            "-m",
            "combhdl",
            "examples/combinational/shared_logic.py",
            "--stdout",
        ],
        cwd=root,
        check=True,
        capture_output=True,
    )
    assert stdout.stdout == (tmp_path / "first/example.v").read_bytes()
    assert stdout.stderr == b""
    assert (
        json.loads((tmp_path / "first/report.json").read_text())["operation_counts"][
            "Xor"
        ]
        == 1
    )


def test_no_implicit_optimization():
    a = Input("a", 4)
    first, second = Xor(a, a), Xor(a, a)
    unreachable = BitNot(a)
    circuit = Component(
        "unoptimized", [a], [Output("out", If(Const(1, 1), first, second))]
    )
    result = compile(circuit)
    assert result.report["operation_counts"] == {
        "Const": 1,
        "If": 1,
        "Input": 1,
        "Xor": 2,
    }
    assert unreachable.kind not in result.report["operation_counts"]
    assert result.verilog.count(" ^ ") == 2
    assert " ? " in result.verilog
