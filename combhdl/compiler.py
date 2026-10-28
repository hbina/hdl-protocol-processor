"""Iterative validation, evaluation, and deterministic Verilog emission."""

from collections import Counter
from dataclasses import dataclass
from typing import Any, Mapping

from .model import (
    Component,
    CompileError,
    Expr,
    Output,
    PREFIX,
    infer,
    integer,
    name_check,
)

VERSION = "0.1.0"


@dataclass(frozen=True)
class CompileResult:
    verilog: str
    interface: dict[str, Any]
    report: dict[str, Any]
    warnings: tuple[dict[str, str], ...]


def validate(component: Component) -> list[Expr]:
    """Return identity-based postorder, with explicit stack cycle detection."""
    label = getattr(component, "name", "<unknown>")
    context = "interface"
    try:
        if type(component) is not Component:
            raise CompileError("expected Component")
        name_check(component.name)
        names: set[str] = set()
        declared: set[Expr] = set()
        for port in component.inputs:
            context = f"input {getattr(port, 'name', '?')!r}"
            if type(port) is not Expr or port.kind != "Input":
                raise CompileError("input declaration must be an Input")
            name_check(port.name)
            integer(port.width, "input width", 1)
            if infer(port.kind, port.operands, port.params) != port.width:
                raise CompileError("invalid input width")
            if port.name in names:
                raise CompileError("duplicate port name")
            names.add(port.name)
            declared.add(port)
        if not component.outputs:
            raise CompileError("component must have at least one output")
        for out in component.outputs:
            context = f"output {getattr(out, 'name', '?')!r}"
            if type(out) is not Output:
                raise CompileError("expected Output declaration")
            name_check(out.name)
            if out.name in names:
                raise CompileError("duplicate port name")
            names.add(out.name)
        done: set[Expr] = set()
        active: set[Expr] = set()
        order: list[Expr] = []
        for out in component.outputs:
            # Each stack entry carries its operand position, permitting deep graphs.
            stack: list[tuple[Expr, int]] = [(out.expression, -1)]
            while stack:
                current, index = stack[-1]
                context = f"output {out.name!r} path " + " -> ".join(
                    str(getattr(n, "kind", type(n).__name__)) for n, _ in stack[-12:]
                )
                if type(current) is not Expr:
                    raise CompileError("unsupported node type")
                if index == -1:
                    if current in active:
                        raise CompileError("cyclic dependency")
                    if current in done:
                        stack.pop()
                        continue
                    integer(current.width, f"{current.kind} width", 1)
                    if (
                        infer(current.kind, current.operands, current.params)
                        != current.width
                    ):
                        raise CompileError("stored width disagrees with inferred width")
                    if current.kind == "Input" and current not in declared:
                        raise CompileError(f"undeclared input {current.name!r}")
                    active.add(current)
                    index = 0
                if index < len(current.operands):
                    stack[-1] = (current, index + 1)
                    stack.append((current.operands[index], -1))
                else:
                    active.remove(current)
                    done.add(current)
                    order.append(current)
                    stack.pop()
        return order
    except CompileError as exc:
        raise CompileError(f"component {label!r}, {context}: {exc}") from exc


def evaluate(component: Component, inputs: Mapping[str, int]) -> dict[str, int]:
    order = validate(component)
    expected = {p.name for p in component.inputs}
    if set(inputs) != expected:
        raise CompileError(
            f"component {component.name!r}: input names must be {sorted(expected)}; got {sorted(inputs)}"
        )
    values: dict[Expr, int] = {}
    for p in component.inputs:
        value = inputs[p.name]
        integer(value, f"component {component.name!r} input {p.name}")
        if value.bit_length() > p.width:
            raise CompileError(
                f"component {component.name!r} input {p.name}: value outside width {p.width}"
            )
        values[p] = value
    for n in order:
        a = [values[x] for x in n.operands]
        k, p = n.kind, n.params
        match k:
            case "Input":
                v = values[n]
            case "Const":
                v = p[0]
            case "And":
                v = a[0] & a[1]
            case "Or":
                v = a[0] | a[1]
            case "Xor":
                v = a[0] ^ a[1]
            case "BitNot":
                v = ~a[0]
            case "Not":
                v = int(not a[0])
            case "Eq":
                v = int(a[0] == a[1])
            case "Lt":
                v = int(a[0] < a[1])
            case "If":
                v = a[1] if a[0] else a[2]
            case "Add":
                v = a[0] + a[1]
            case "Sub":
                v = a[0] - a[1]
            case "Bit" | "Slice":
                v = a[0] >> p[0]
            case "Shl":
                v = 0 if p[0] >= n.width else a[0] << p[0]
            case "Shr":
                v = 0 if p[0] >= n.width else a[0] >> p[0]
            case "ZeroExtend" | "Truncate":
                v = a[0]
            case "Concat":
                v = 0
                for operand, value in zip(n.operands, a):
                    v = (v << operand.width) | value
            case _:
                raise CompileError(f"unsupported expression {k}")
        values[n] = v & ((1 << n.width) - 1)
    return {o.name: values[o.expression] for o in component.outputs}


def rhs(n: Expr, refs: dict[Expr, str]) -> str:
    a = [refs[x] for x in n.operands]
    k, p = n.kind, n.params
    binary = {
        "And": "&",
        "Or": "|",
        "Xor": "^",
        "Eq": "==",
        "Lt": "<",
        "Add": "+",
        "Sub": "-",
    }
    if k in binary:
        return f"{a[0]} {binary[k]} {a[1]}"
    if k == "Const":
        return f"{n.width}'h{p[0]:x}"
    if k in ("Not", "BitNot"):
        return f"{'!' if k == 'Not' else '~'}{a[0]}"
    if k == "If":
        return f"{a[0]} ? {a[1]} : {a[2]}"
    if k == "Bit":
        return f"{a[0]}[{p[0]}]"
    if k == "Slice":
        return f"{a[0]}[{p[0] + p[1] - 1}:{p[0]}]"
    if k == "Concat":
        return "{" + ", ".join(a) + "}"
    if k in ("Shl", "Shr"):
        if p[0] >= n.width:
            return f"{n.width}'h0"
        return (
            f"{a[0]} {'<<' if k == 'Shl' else '>>'} {max(1, p[0].bit_length())}'d{p[0]}"
        )
    if k == "ZeroExtend" and n.width > n.operands[0].width:
        return "{" + f"{n.width - n.operands[0].width}'h0, {a[0]}" + "}"
    if k == "Truncate" and n.width < n.operands[0].width:
        return f"{a[0]}[{n.width - 1}:0]"
    return a[0]


def compile(component: Component) -> CompileResult:
    order = validate(component)
    refs = {
        n: n.name if n.kind == "Input" else f"{PREFIX}{i}" for i, n in enumerate(order)
    }
    ids = {n: f"n{i}" for i, n in enumerate(order)}
    lines = [
        "// Generated by combhdl " + VERSION,
        "`default_nettype none",
        f"module {component.name} (",
    ]
    ports = [f"    input wire [{p.width - 1}:0] {p.name}" for p in component.inputs]
    ports += [f"    output wire [{p.width - 1}:0] {p.name}" for p in component.outputs]
    lines += [",\n".join(ports), ");"]
    for n in order:
        if n.kind != "Input":
            lines += [
                f"wire [{n.width - 1}:0] {refs[n]};",
                f"assign {refs[n]} = {rhs(n, refs)};",
            ]
    lines += [f"assign {o.name} = {refs[o.expression]};" for o in component.outputs]
    lines += ["endmodule", "`default_nettype wire", ""]
    warnings = tuple(
        {
            "code": "unused-input",
            "port": p.name,
            "message": f"Input {p.name!r} is unused",
        }
        for p in component.inputs
        if p not in refs
    )
    fanout: Counter[Expr] = Counter(o.expression for o in component.outputs)
    for n in order:
        fanout.update(n.operands)
    interface = {
        "compiler_version": VERSION,
        "component": component.name,
        "inputs": [{"name": p.name, "width": p.width} for p in component.inputs],
        "outputs": [{"name": p.name, "width": p.width} for p in component.outputs],
    }
    report = {
        "compiler_version": VERSION,
        "component": component.name,
        "node_count": len(order),
        "operation_counts": dict(sorted(Counter(n.kind for n in order).items())),
        "nodes": [
            {
                "id": ids[n],
                "kind": n.kind,
                "width": n.width,
                "name": n.name or refs[n],
                "parameters": list(n.params),
                "operands": [ids[x] for x in n.operands],
                "fanout": fanout[n],
            }
            for n in order
        ],
        "outputs": [
            {"port": o.name, "node": ids[o.expression]} for o in component.outputs
        ],
        "shared_nodes": [ids[n] for n in order if fanout[n] > 1],
        "warnings": list(warnings),
    }
    return CompileResult("\n".join(lines), interface, report, warnings)
