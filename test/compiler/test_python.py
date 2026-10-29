"""Execute standalone generated models against independent functional evidence."""

import ast
import builtins
import inspect
import keyword
import runpy

import pytest

from combhdl import (
    Add,
    BitNot,
    CompileError,
    Component,
    Const,
    Expr,
    If,
    Input,
    Output,
    Shl,
    Shr,
    Xor,
    compile,
    emit_python,
    evaluate,
)
from examples.combinational.ipv4_checksum import component as checksum
from examples.combinational.ipv4_checksum import fold_sum16
from examples.combinational.operations import expected, operations
from tools.check_checksum import cases, reference
from tools.check_simulation import vectors


def load(component):
    source = emit_python(component)
    namespace = {}
    exec(source, namespace)
    name = component.name
    if not name.isidentifier() or keyword.iskeyword(name) or name in vars(builtins):
        name = "_combhdl_model"
    return namespace[name]


@pytest.mark.parametrize("width", [1, 4, 17, 160])
def test_operations(width):
    component = operations(width)
    model = load(component)
    for a, b, c in vectors(width):
        inputs = {"a": a, "b": b, "c": c}
        assert (
            model(**inputs) == evaluate(component, inputs) == expected(width, a, b, c)
        )
        assert all(type(value) is int for value in model(**inputs).values())


def test_checksum_vectors():
    model = load(checksum)
    evidence = cases()
    assert len(evidence) == 2508
    for inputs, expected_outputs in evidence:
        assert model(**inputs) == evaluate(checksum, inputs) == expected_outputs


@pytest.mark.parametrize(
    "value", [0, 1, 0xFFFF, 0x10000, 0x1FFFF, 0xFFFF0000, 0xFFFFFFFF]
)
def test_carry_folding(value):
    component = Component("fold", [], [Output("result", fold_sum16(Const(value, 32)))])
    assert load(component)() == {"result": 0xFFFF ^ reference(value.to_bytes(4, "big"))}


def test_sharing_and_order():
    a, unused, choose = Input("a", 3), Input("unused", 2), Input("choose", 1)
    shared = BitNot(a)
    equivalent = BitNot(a)
    selection = If(choose, shared, equivalent)
    component = Component(
        "sharing",
        [unused, a, choose],
        [Output("selected", selection), Output("shared", shared), Output("direct", a)],
    )
    source = emit_python(component)
    tree = ast.parse(source)
    assignments = [node for node in tree.body[-1].body if isinstance(node, ast.Assign)]
    report = compile(component).report
    expected_names = [
        "_combhdl_value_" + node["id"][1:]
        for node in report["nodes"]
        if node["kind"] != "Input"
    ]
    assert [node.targets[0].id for node in assignments] == expected_names
    assert source.count(" = ~a & ") == 2
    assert source.count(" if choose else ") == 1
    assert source.index(" = ~a & ") < source.index(" if choose else ")
    assert list(inspect.signature(load(component)).parameters) == [
        "unused",
        "a",
        "choose",
    ]
    for choose_value in (0, 1):
        result = load(component)(a=3, unused=0, choose=choose_value)
        assert result == {"selected": 4, "shared": 4, "direct": 3}
        assert list(result) == ["selected", "shared", "direct"]
    assert emit_python(component) == source
    assert source.endswith("\n")


@pytest.mark.parametrize("name", ["normal", "lambda", "len", "ValueError", "a$b"])
def test_function_names(name):
    component = Component(name, [], [Output("a$b", Const(5, 3))])
    assert load(component)() == {"a$b": 5}
    assert repr(name) in ast.get_docstring(ast.parse(emit_python(component)))


def test_parameter_aliases_and_standalone_import(tmp_path):
    names = ["normal", "lambda", "len", "abs", "ValueError", "a$b", "dict"]
    ports = [Input(name, 3) for name in names]
    component = Component("len", ports, [Output("result", Add(ports[0], ports[1]))])
    path = tmp_path / "model.py"
    path.write_text(emit_python(component))
    namespace = runpy.run_path(str(path))
    model = namespace["_combhdl_model"]
    parameters = list(inspect.signature(model).parameters)
    assert parameters == ["normal"] + [f"_combhdl_input_{i}" for i in range(1, 7)]
    assert model(**dict.fromkeys(parameters, 1)) == {"result": 2}
    for original, parameter in zip(names[1:], parameters[1:]):
        assert repr(original) in namespace["__doc__"]
        assert parameter in namespace["__doc__"]
    with pytest.raises(TypeError):
        model(**dict.fromkeys(names, 1))


@pytest.mark.parametrize("value", [True, False, -1, 8, 1.0, "1", None, object()])
@pytest.mark.parametrize("port", ["a", "unused"])
def test_invalid_inputs(value, port):
    a, unused = Input("a", 3), Input("unused", 3)
    model = load(Component("ranges", [a, unused], [Output("result", a)]))
    inputs = {"a": 0, "unused": 0, port: value}
    with pytest.raises(ValueError):
        model(**inputs)


def test_signature_errors():
    a, unused = Input("a", 1), Input("unused", 1)
    model = load(Component("signature", [a, unused], [Output("result", a)]))
    for args, kwargs in [
        ((0, 0), {}),
        ((), {"a": 0}),
        ((), {"a": 0, "unused": 0, "extra": 0}),
    ]:
        with pytest.raises(TypeError):
            model(*args, **kwargs)


def test_huge_shifts_and_constants():
    a = Input("a", 3)
    component = Component(
        "shifts",
        [a],
        [
            Output("left_shift", Shl(a, 10**100)),
            Output("right_shift", Shr(a, 10**100)),
        ],
    )
    assert load(component)(a=7) == {"left_shift": 0, "right_shift": 0}
    assert str(10**100) not in emit_python(component)
    # Hex literals also avoid Python's decimal integer conversion limit.
    constant = Component("huge", [], [Output("result", Const(1 << 16000, 16001))])
    assert load(constant)() == {"result": 1 << 16000}


def test_deep_graph():
    a = Input("a", 1)
    result = a
    for _ in range(5000):
        result = BitNot(result)
    component = Component("deep", [a], [Output("result", result)])
    source = emit_python(component)
    assert source.count(" = ~") == 5000
    assert load(component)(a=1) == evaluate(component, {"a": 1}) == {"result": 1}


def test_invalid_graphs():
    a = Input("a", 1)
    loop = BitNot(a)
    object.__setattr__(loop, "operands", (loop,))
    wrong_width = BitNot(a)
    object.__setattr__(wrong_width, "width", 2)
    for expression in (
        loop,
        wrong_width,
        Input("other", 1),
        Expr("Register", (), (), 1),
    ):
        with pytest.raises(CompileError):
            emit_python(Component("invalid", [a], [Output("result", expression)]))
    with pytest.raises(CompileError):
        emit_python(Component("empty", [], []))
    # A constant condition must not hide an invalid branch.
    with pytest.raises(CompileError):
        emit_python(
            Component("invalid", [a], [Output("result", If(Const(1, 1), a, loop))])
        )
