"""Human-readable, fully expanded expression structure."""

from .compiler import validate
from .model import Component, Expr


def format_ast(component: Component) -> str:
    """Render constructor-style expressions, repeating every shared subtree."""
    validate(component)
    lines = [f"Component({component.name!r},", "    inputs=["]
    for port in component.inputs:
        lines.append(f"        Input({port.name!r}, width={port.width}),")
    lines += ["    ],", "    outputs=["]
    for output in component.outputs:
        lines.append(f"        Output({output.name!r},")
        # Explicit events avoid Python recursion limits without collapsing sharing.
        stack: list[tuple[Expr | str, int]] = [(output.expression, 3)]
        while stack:
            item, depth = stack.pop()
            indent = "    " * depth
            if isinstance(item, str):
                lines.append(indent + item)
            elif item.kind == "Input":
                lines.append(f"{indent}Input({item.name!r}, width={item.width}),")
            elif item.kind == "Const":
                lines.append(f"{indent}Const({item.params[0]}, width={item.width}),")
            else:
                lines.append(f"{indent}{item.kind}(")
                stack.append(("),", depth))
                stack.extend((str(p) + ",", depth + 1) for p in reversed(item.params))
                stack.extend(
                    (operand, depth + 1) for operand in reversed(item.operands)
                )
        lines.append("        ),")
    lines += ["    ],", ")", ""]
    return "\n".join(lines)
