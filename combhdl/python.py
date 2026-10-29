"""Standalone imperative Python emission from validated expression graphs."""

import builtins
import keyword

from .compiler import validate
from .model import Component, Expr, PREFIX


def _python_name(name: str) -> bool:
    return (
        name.isidentifier()
        and not keyword.iskeyword(name)
        and name not in vars(builtins)
    )


def python_rhs(node: Expr, refs: dict[Expr, str]) -> str:
    """Format an unsigned operation for Python emission and graph inspection."""
    args = [refs[operand] for operand in node.operands]
    kind, params = node.kind, node.params
    mask = hex((1 << node.width) - 1)
    binary = {"And": "&", "Or": "|", "Xor": "^", "Add": "+", "Sub": "-"}
    if kind in binary:
        expression = f"{args[0]} {binary[kind]} {args[1]}"
        return f"({expression}) & {mask}" if kind in ("Add", "Sub") else expression
    if kind == "Const":
        return hex(params[0])
    if kind == "BitNot":
        return f"~{args[0]} & {mask}"
    if kind == "Not":
        return f"int(not {args[0]})"
    if kind in ("Eq", "Lt"):
        return f"int({args[0]} {'==' if kind == 'Eq' else '<'} {args[1]})"
    if kind == "If":
        return f"{args[1]} if {args[0]} else {args[2]}"
    if kind in ("Bit", "Slice"):
        return f"({args[0]} >> {params[0]}) & {mask}"
    if kind in ("Shl", "Shr"):
        if params[0] >= node.width:
            return "0"
        if kind == "Shl":
            return f"({args[0]} << {params[0]}) & {mask}"
        return f"{args[0]} >> {params[0]}"
    if kind == "Truncate":
        return f"{args[0]} & {mask}"
    if kind == "Concat":
        shift = node.width
        parts: list[str] = []
        for operand, arg in zip(node.operands, args):
            shift -= operand.width
            parts.append(f"({arg} << {shift})" if shift else arg)
        return " | ".join(parts)
    # Validation leaves only ZeroExtend, which preserves the unsigned value.
    return args[0]


def emit_python(component: Component) -> str:
    """Emit a dependency-free model with required keyword-only unsigned inputs."""
    order = validate(component)
    names = {
        port: port.name if _python_name(port.name) else f"{PREFIX}input_{i}"
        for i, port in enumerate(component.inputs)
    }
    function = component.name if _python_name(component.name) else f"{PREFIX}model"
    description = f"Generated Python model for component {component.name!r}."
    if function != component.name:
        description += f"\nFunction: {function}."
    for port in component.inputs:
        if names[port] != port.name:
            description += f"\nInput {port.name!r} uses parameter {names[port]!r}."
    lines = [repr(description), "", ""]
    if component.inputs:
        lines += [f"def {function}(", "    *,"]
        lines += [f"    {names[port]}: int," for port in component.inputs]
        lines += [") -> dict[str, int]:"]
    else:
        lines += [f"def {function}() -> dict[str, int]:"]
    for port in component.inputs:
        arg = names[port]
        lines += [
            f"    if type({arg}) is not int or {arg} < 0 or {arg}.bit_length() > {port.width}:",
            f"        raise ValueError({f'Input {port.name!r}: expected unsigned {port.width}-bit integer'!r})",
        ]
    refs = {
        node: names[node] if node.kind == "Input" else f"{PREFIX}value_{i}"
        for i, node in enumerate(order)
    }
    for node in order:
        if node.kind != "Input":
            lines.append(f"    {refs[node]} = {python_rhs(node, refs)}")
    lines.append("    return {")
    lines += [
        f"        {out.name!r}: {refs[out.expression]}," for out in component.outputs
    ]
    lines += ["    }", ""]
    return "\n".join(lines)
