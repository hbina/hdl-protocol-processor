"""All language operations, reused by differential simulation and synthesis."""

from combhdl import (
    Add,
    And,
    Bit,
    BitNot,
    Component,
    Concat,
    Const,
    Eq,
    If,
    Input,
    Lt,
    Not,
    Or,
    Output,
    Shl,
    Shr,
    Slice,
    Sub,
    Truncate,
    Xor,
    ZeroExtend,
)


def operations(width: int) -> Component:
    a, b, c = Input("a", width), Input("b", width), Input("c", 1)
    shared = Xor(a, b)
    expressions = {
        "bit_and": And(a, b),
        "bit_or": Or(a, b),
        "bit_xor": shared,
        "complement": BitNot(a),
        "logical_not": Not(c),
        "equal": Eq(a, b),
        "less": Lt(a, b),
        "select_value": If(c, shared, If(Not(c), b, a)),
        "sum_wrap": Add(a, b),
        "difference": Sub(a, b),
        "first_bit": Bit(a, 0),
        "last_bit": Bit(a, width - 1),
        "slice_low": Slice(a, 0, width),
        "slice_high": Slice(a, width - 1, 1),
        "joined": Concat(a, b, c),
        "single_concat": Concat(a),
        "extended": ZeroExtend(a, width + 1),
        "carry": Add(ZeroExtend(a, width + 1), ZeroExtend(b, width + 1)),
        "extended_same": ZeroExtend(a, width),
        "truncated": Truncate(a, 1),
        "truncated_same": Truncate(a, width),
        "literal": Const((1 << width) - 1, width),
        # Narrow arithmetic must wrap before being consumed by wider expressions.
        "wrapped_extended": ZeroExtend(Add(a, b), width + 1),
        "wrapped_joined": Concat(Sub(a, b), c),
        "wrapped_compare": Lt(Add(a, b), b),
    }
    for amount in (0, width - 1, width, width + 1):
        expressions[f"left_{amount}"] = Shl(a, amount)
        expressions[f"right_{amount}"] = Shr(a, amount)
    return Component(
        f"operations_{width}", [a, b, c], [Output(k, v) for k, v in expressions.items()]
    )


def expected(width: int, a: int, b: int, c: int) -> dict[str, int]:
    """Independent integer oracle, with explicit wrapping at arithmetic boundaries."""
    mask = (1 << width) - 1
    result = {
        "bit_and": a & b,
        "bit_or": a | b,
        "bit_xor": a ^ b,
        "complement": mask ^ a,
        "logical_not": 1 - c,
        "equal": int(a == b),
        "less": int(a < b),
        "select_value": (a ^ b) if c else b,
        "sum_wrap": (a + b) % (1 << width),
        "difference": (a - b) % (1 << width),
        "first_bit": a % 2,
        "last_bit": a // (1 << (width - 1)),
        "slice_low": a,
        "slice_high": a // (1 << (width - 1)),
        "joined": a * (1 << (width + 1)) + b * 2 + c,
        "single_concat": a,
        "extended": a,
        "carry": a + b,
        "extended_same": a,
        "truncated": a % 2,
        "truncated_same": a,
        "literal": mask,
        "wrapped_extended": (a + b) % (1 << width),
        "wrapped_joined": ((a - b) % (1 << width)) * 2 + c,
        "wrapped_compare": int(((a + b) % (1 << width)) < b),
    }
    for amount in (0, width - 1, width, width + 1):
        result[f"left_{amount}"] = (a * 2**amount) % (1 << width)
        result[f"right_{amount}"] = a // 2**amount
    return result
