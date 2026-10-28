"""Immutable, unsigned expression construction. Python executes only at build time."""

from dataclasses import dataclass
import re
from typing import Iterable


class CompileError(ValueError):
    """Invalid hardware construction or component."""


# IEEE Verilog and SystemVerilog keywords are excluded, including escaped-name alternatives.
KEYWORDS = frozenset(
    """
accept_on alias always always_comb always_ff always_latch and assert assign assume
 automatic before begin bind bins binsof bit break buf bufif0 bufif1 byte case
 casex casez cell chandle checker class clocking cmos config const constraint
 context continue cover covergroup coverpoint cross deassign default defparam
 design disable dist do edge else end endcase endchecker endclass endclocking
 endconfig endfunction endgenerate endgroup endinterface endmodule endpackage
 endprimitive endprogram endproperty endspecify endsequence endtable endtask enum
 event eventually expect export extends extern final first_match for force foreach
 forever fork forkjoin function generate genvar global highz0 highz1 if iff ifnone
 ignore_bins illegal_bins implements implies import incdir include initial inout
 input inside int integer interconnect interface intersect join join_any join_none
 large let liblist library local localparam logic longint macromodule matches medium
 modport module nand negedge nettype new nexttime nmos nor noshowcancelled not notif0
 notif1 null or output package packed parameter pmos posedge primitive priority
 program property protected pull0 pull1 pulldown pullup pulsestyle_ondetect
 pulsestyle_onevent pure rand randc randcase randsequence rcmos real realtime ref
 reg reject_on release repeat restrict return rnmos rpmos rtran rtranif0 rtranif1
 s_always s_eventually s_nexttime s_until s_until_with scalared sequence shortint
 shortreal showcancelled signed small soft solve specify specparam static string
 strong strong0 strong1 struct super supply0 supply1 sync_accept_on sync_reject_on
 table tagged task this throughout time timeprecision timeunit tran tranif0 tranif1
 tri tri0 tri1 triand trior trireg type typedef union unique unique0 unsigned until
 until_with untyped use uwire var vectored virtual void wait wait_order wand weak
 weak0 weak1 while wildcard wire with within wor xnor xor
""".split()
)
PREFIX = "_combhdl_"


def name_check(name: str) -> None:
    if (
        not isinstance(name, str)  # pyright: ignore[reportUnnecessaryIsInstance]
        or re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_$]*", name) is None
        or name in KEYWORDS
        or name.startswith(PREFIX)
    ):
        raise CompileError(
            f"name {name!r}: expected nonreserved Verilog identifier (reserved prefix {PREFIX})"
        )


def integer(value: int, label: str, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise CompileError(f"{label}: expected integer >= {minimum}, got {value!r}")


@dataclass(frozen=True, eq=False, slots=True)
class Expr:
    kind: str
    operands: tuple["Expr", ...]
    params: tuple[int, ...]
    width: int
    name: str = ""

    def __bool__(self) -> bool:
        raise CompileError(
            "expression cannot be converted to Python truth; use If or Not"
        )


def infer(kind: str, args: tuple[Expr, ...], params: tuple[int, ...]) -> int:
    for arg in args:
        if type(arg) is not Expr:
            raise CompileError(
                f"{kind}: operands must be supported expressions, got {type(arg).__name__}"
            )
        integer(arg.width, f"{kind} operand width", 1)
    arities = {
        "And": 2,
        "Or": 2,
        "Xor": 2,
        "Eq": 2,
        "Lt": 2,
        "Add": 2,
        "Sub": 2,
        "BitNot": 1,
        "Not": 1,
        "If": 3,
        "Bit": 1,
        "Slice": 1,
        "Shl": 1,
        "Shr": 1,
        "ZeroExtend": 1,
        "Truncate": 1,
        "Input": 0,
        "Const": 0,
    }
    if kind != "Concat" and kind not in arities:
        raise CompileError(f"unsupported expression kind {kind!r}")
    if (kind == "Concat" and not args) or (
        kind != "Concat" and len(args) != arities[kind]
    ):
        raise CompileError(f"{kind}: invalid operand count {len(args)}")
    param_counts = {
        "Input": 1,
        "Const": 2,
        "Bit": 1,
        "Slice": 2,
        "Shl": 1,
        "Shr": 1,
        "ZeroExtend": 1,
        "Truncate": 1,
    }
    if len(params) != param_counts.get(kind, 0):
        raise CompileError(f"{kind}: invalid parameter count")
    for p in params:
        integer(p, f"{kind} parameter")
    if kind in ("Input", "Const"):
        width = params[-1]
        integer(width, f"{kind} width", 1)
        if kind == "Const" and params[0].bit_length() > width:
            raise CompileError(f"Const: value {params[0]} does not fit width {width}")
        return width
    w = args[0].width
    if kind in ("And", "Or", "Xor", "Eq", "Lt", "Add", "Sub"):
        if w != args[1].width:
            raise CompileError(f"{kind}: operand widths must match")
        return 1 if kind in ("Eq", "Lt") else w
    if kind == "If":
        if w != 1 or args[1].width != args[2].width:
            raise CompileError(
                "If: condition must be one bit and branch widths must match"
            )
        return args[1].width
    if kind == "Not" and w != 1:
        raise CompileError("Not: operand must be one bit")
    if kind == "Bit":
        if params[0] >= w:
            raise CompileError("Bit: index outside operand")
        return 1
    if kind == "Slice":
        integer(params[1], "Slice width", 1)
        if params[0] + params[1] > w:
            raise CompileError("Slice: bounds outside operand")
        return params[1]
    if kind == "Concat":
        return sum(a.width for a in args)
    if kind in ("ZeroExtend", "Truncate"):
        dest = params[0]
        integer(dest, f"{kind} width", 1)
        if (kind == "ZeroExtend" and dest < w) or (kind == "Truncate" and dest > w):
            raise CompileError(
                f"{kind}: invalid destination width {dest} for operand width {w}"
            )
        return dest
    return w


def node(kind: str, *args: Expr, params: tuple[int, ...] = (), name: str = "") -> Expr:
    return Expr(kind, args, params, infer(kind, args, params), name)


def Input(name: str, width: int) -> Expr:
    name_check(name)
    return node("Input", params=(width,), name=name)


def Const(value: int, width: int) -> Expr:
    return node("Const", params=(value, width))


def And(a: Expr, b: Expr) -> Expr:
    return node("And", a, b)


def Or(a: Expr, b: Expr) -> Expr:
    return node("Or", a, b)


def Xor(a: Expr, b: Expr) -> Expr:
    return node("Xor", a, b)


def Eq(a: Expr, b: Expr) -> Expr:
    return node("Eq", a, b)


def Lt(a: Expr, b: Expr) -> Expr:
    return node("Lt", a, b)


def Add(a: Expr, b: Expr) -> Expr:
    return node("Add", a, b)


def Sub(a: Expr, b: Expr) -> Expr:
    return node("Sub", a, b)


def BitNot(value: Expr) -> Expr:
    return node("BitNot", value)


def Not(value: Expr) -> Expr:
    return node("Not", value)


def If(condition: Expr, a: Expr, b: Expr) -> Expr:
    return node("If", condition, a, b)


def Bit(value: Expr, index: int) -> Expr:
    return node("Bit", value, params=(index,))


def Slice(value: Expr, low: int, width: int) -> Expr:
    return node("Slice", value, params=(low, width))


def Concat(*values: Expr) -> Expr:
    return node("Concat", *values)


def Shl(value: Expr, amount: int) -> Expr:
    return node("Shl", value, params=(amount,))


def Shr(value: Expr, amount: int) -> Expr:
    return node("Shr", value, params=(amount,))


def ZeroExtend(value: Expr, width: int) -> Expr:
    return node("ZeroExtend", value, params=(width,))


def Truncate(value: Expr, width: int) -> Expr:
    return node("Truncate", value, params=(width,))


@dataclass(frozen=True, slots=True)
class Output:
    name: str
    expression: Expr

    @property
    def width(self) -> int:
        return self.expression.width


@dataclass(frozen=True, slots=True, init=False)
class Component:
    name: str
    inputs: tuple[Expr, ...]
    outputs: tuple[Output, ...]

    def __init__(self, name: str, inputs: Iterable[Expr], outputs: Iterable[Output]):
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "inputs", tuple(inputs))
        object.__setattr__(self, "outputs", tuple(outputs))
