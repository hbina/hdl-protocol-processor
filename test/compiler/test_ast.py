import combhdl
from combhdl import BitNot, Component, Input, Output, evaluate
from combhdl.ast import format_ast
from examples.combinational.operations import operations
from examples.combinational.shared_logic import component


def rebuild(text):
    # The unrolled display repeats input declarations; restore port identity.
    ports = {}

    def input_port(name, width):
        return ports.setdefault((name, width), Input(name, width))

    return eval(text, {**vars(combhdl), "Input": input_port})


def test_ast_fully_expands_shared_expressions():
    text = format_ast(component)
    assert text.count("Xor(") == 2
    assert "_combhdl_" not in text
    assert "            If(\n" in text
    rebuilt = rebuild(text)
    for choose in (0, 1):
        inputs = {"a": 37, "b": 129, "choose": choose}
        assert evaluate(rebuilt, inputs) == evaluate(component, inputs)


def test_ast_preserves_all_operation_parameters():
    circuit = operations(4)
    rebuilt = rebuild(format_ast(circuit))
    inputs = {port.name: (1 << port.width) - 1 for port in circuit.inputs}
    assert evaluate(rebuilt, inputs) == evaluate(circuit, inputs)


def test_ast_handles_deep_expressions_without_truncation():
    source = Input("source", 1)
    expression = source
    for _ in range(1100):
        expression = BitNot(expression)
    text = format_ast(Component("deep", [source], [Output("result", expression)]))
    assert text.count("BitNot(") == 1100
    assert "..." not in text
