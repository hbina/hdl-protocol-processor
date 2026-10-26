"""Typed ISA for the autonomous pin processor; no historical ISA compatibility."""

from __future__ import annotations
import argparse
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Literal


class IsaError(ValueError):
    pass


@dataclass(frozen=True)
class Reg:
    index: int

    def __post_init__(self) -> None:
        if isinstance(self.index, bool) or not 0 <= self.index <= 3:
            raise IsaError("register must be r0..r3")

    def __str__(self) -> str:
        return f"r{self.index}"


r0, r1, r2, r3 = (Reg(i) for i in range(4))


class Label:
    """A program location.

    A named label is its name: two ``Label("loop")`` objects are equal, so
    fragments built separately can refer to the same location. An anonymous
    label is equal only to itself, so a fragment can create private labels
    that never collide.
    """

    __slots__ = ("name",)

    def __init__(self, name: str | None = None) -> None:
        self.name = name

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Label):
            return NotImplemented
        if self.name is None or other.name is None:
            return self is other
        return self.name == other.name

    def __hash__(self) -> int:
        return hash(self.name) if self.name is not None else id(self)

    def __repr__(self) -> str:
        return f"Label({self.name!r})" if self.name else f"Label(<{id(self):x}>)"


type Target = Label | int


class RegImmOp(Enum):
    LDI = "LDI"
    CMPI = "CMPI"
    CMPLTI = "CMPLTI"
    ADDI = "ADDI"
    ANDI = "ANDI"
    ORI = "ORI"
    XORI = "XORI"


class RegRegOp(Enum):
    MOV = "MOV"
    XOR = "XOR"
    OR = "OR"
    AND = "AND"
    CMPLT = "CMPLT"
    LOAD = "LOAD"
    STORE = "STORE"


class UnaryOp(Enum):
    SHL = "SHL"
    SHR = "SHR"
    ROL = "ROL"
    ROR = "ROR"


class ImmOp(Enum):
    WAIT = "WAIT"


class JumpOp(Enum):
    JMP = "JMP"
    JFAIL = "JFAIL"


class CondJumpOp(Enum):
    JZ = "JZ"
    DJNZ = "DJNZ"


class PinOp(Enum):
    OUTBIT = "OUTBIT"
    INBIT = "INBIT"
    OEBIT = "OEBIT"
    OEBITN = "OEBITN"


def _check_reg(*regs: Reg) -> None:
    for reg in regs:
        if not isinstance(reg, Reg):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise IsaError(f"expected a register, not {reg!r}")


def _check_target(target: Target) -> None:
    if not isinstance(target, Label):
        _check_range(target, 255, "address")


def _check_range(value: int, maximum: int, kind: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise IsaError(f"{kind} must be an integer: {value!r}")
    if not 0 <= value <= maximum:
        raise IsaError(f"{kind} must be in the range 0..{maximum}: {value}")


@dataclass(frozen=True)
class Nop:
    pass


@dataclass(frozen=True)
class Halt:
    pass


@dataclass(frozen=True)
class RegImm:
    op: RegImmOp
    rd: Reg
    imm: int

    def __post_init__(self) -> None:
        _check_reg(self.rd)
        _check_range(self.imm, 0xFF, "immediate")


@dataclass(frozen=True)
class RegReg:
    op: RegRegOp
    rd: Reg
    rs: Reg

    def __post_init__(self) -> None:
        _check_reg(self.rd, self.rs)


@dataclass(frozen=True)
class Unary:
    op: UnaryOp
    rd: Reg

    def __post_init__(self) -> None:
        _check_reg(self.rd)


@dataclass(frozen=True)
class Imm:
    op: ImmOp
    imm: int

    def __post_init__(self) -> None:
        _check_range(self.imm, 0xFF, "immediate")


@dataclass(frozen=True)
class Jump:
    op: JumpOp
    target: Target

    def __post_init__(self) -> None:
        _check_target(self.target)


@dataclass(frozen=True)
class CondJump:
    op: CondJumpOp
    rd: Reg
    target: Target

    def __post_init__(self) -> None:
        _check_reg(self.rd)
        _check_target(self.target)


@dataclass(frozen=True)
class RegPin:
    op: PinOp
    rd: Reg
    pin: int | Reg

    def __post_init__(self) -> None:
        _check_reg(self.rd)
        _check_pin(self.pin)


@dataclass(frozen=True)
class WaitPin:
    pin: int | Reg
    value: int

    def __post_init__(self) -> None:
        _check_pin(self.pin)
        _check_range(self.value, 1, "pin value")


class BankOp(Enum):
    IN = "IN"
    OUT = "OUT"
    OE = "OE"


@dataclass(frozen=True)
class Bank:
    op: BankOp
    rd: Reg
    bank: int

    def __post_init__(self) -> None:
        _check_reg(self.rd)
        _check_range(self.bank, 31, "bank")


def _check_pin(pin: int | Reg) -> None:
    if isinstance(pin, Reg):
        _check_reg(pin)
    else:
        _check_range(pin, 255, "pin")


type Instruction = (
    Nop
    | Halt
    | RegImm
    | RegReg
    | Unary
    | Imm
    | Jump
    | CondJump
    | RegPin
    | WaitPin
    | Bank
)


@dataclass(frozen=True)
class IsaConfig:
    input_pins: int = 15
    output_pins: int = 16
    name: str = "pin-v1"
    program_words: Literal[256] = 256
    registers: Literal[4] = 4
    word_bits: Literal[16] = 16

    def __post_init__(self) -> None:
        _check_range(self.input_pins, 256, "input count")
        _check_range(self.output_pins, 256, "output count")
        if self.input_pins == 0 or self.output_pins == 0:
            raise IsaError("pin counts must be 1..256")
        if (self.program_words, self.registers, self.word_bits) != (256, 4, 16):
            raise IsaError(
                "pin-v1 requires 256 words, four registers and 16-bit instructions"
            )


BASE = IsaConfig()
REG_IMM_CODES = {
    RegImmOp.LDI: (1, 0),
    RegImmOp.CMPI: (1, 1),
    RegImmOp.CMPLTI: (1, 3),
    RegImmOp.ADDI: (12, 0),
    RegImmOp.ANDI: (12, 1),
    RegImmOp.ORI: (12, 2),
    RegImmOp.XORI: (12, 3),
}
REG_REG_CODES = {
    RegRegOp.MOV: (11, 0),
    RegRegOp.XOR: (11, 1),
    RegRegOp.OR: (11, 2),
    RegRegOp.AND: (11, 3),
    RegRegOp.CMPLT: (1, 2),
    RegRegOp.LOAD: (2, 1),
    RegRegOp.STORE: (3, 1),
}
UNARY_CODES = {op: (13, i) for i, op in enumerate(UnaryOp)}
PIN_CODES = {op: i for i, op in enumerate(PinOp)}
BANK_CODES = {op: i for i, op in enumerate(BankOp)}
type Resolver = Callable[[Label], int]


def _no_labels(label: Label) -> int:
    raise IsaError(f"unresolved label {label!r}")


def _fields(opcode: int, select: int, rd: Reg, imm: int) -> int:
    return opcode << 12 | select << 10 | rd.index << 8 | imm


def encode(
    insn: Instruction, cfg: IsaConfig = BASE, resolve: Resolver = _no_labels
) -> int:
    match insn:
        case Nop():
            return 0
        case Halt():
            return 0xF000
        case RegImm(op=op, rd=rd, imm=imm):
            major, select = REG_IMM_CODES[op]
            return _fields(major, select, rd, imm)
        case RegReg(op=op, rd=rd, rs=rs):
            major, select = REG_REG_CODES[op]
            return _fields(major, select, rd, rs.index)
        case Unary(op=op, rd=rd):
            major, select = UNARY_CODES[op]
            return _fields(major, select, rd, 0)
        case Imm(imm=imm):
            return 0x7000 | imm
        case Jump(op=op, target=t) | CondJump(op=op, target=t):
            address = resolve(t) if isinstance(t, Label) else t
            _check_range(address, 255, "address")
            if isinstance(insn, CondJump):
                return (
                    (9 if insn.op == CondJumpOp.JZ else 10) << 12
                    | insn.rd.index << 8
                    | address
                )
            return 0x8000 | (0x800 if op == JumpOp.JFAIL else 0) | address
        case RegPin(op=op, rd=rd, pin=pin):
            if isinstance(pin, Reg):
                return _fields(5, PIN_CODES[op], rd, pin.index)
            limit = cfg.input_pins if op == PinOp.INBIT else cfg.output_pins
            _check_range(pin, limit - 1, "pin")
            return _fields(14, PIN_CODES[op], rd, pin)
        case WaitPin(pin=pin, value=value):
            if isinstance(pin, Reg):
                return 0xF800 | value << 8 | pin.index
            _check_range(pin, cfg.input_pins - 1, "pin")
            return 0xF400 | value << 8 | pin
        case Bank(op=op, rd=rd, bank=bank):
            limit = cfg.input_pins if op == BankOp.IN else cfg.output_pins
            _check_range(bank, (limit - 1) // 8, "bank")
            return _fields(4, BANK_CODES[op], rd, bank)
    raise IsaError(f"unsupported instruction {insn!r}")


def decode(word: int, cfg: IsaConfig = BASE) -> Instruction:
    _check_range(word, 65535, "word")
    major, select, rd, imm = (
        word >> 12,
        (word >> 10) & 3,
        Reg((word >> 8) & 3),
        word & 255,
    )
    insn: Instruction | None = None
    if word == 0:
        insn = Nop()
    elif word == 0xF000:
        insn = Halt()
    elif major == 7:
        insn = Imm(ImmOp.WAIT, imm)
    elif major == 8:
        insn = Jump(JumpOp.JFAIL if word & 0x800 else JumpOp.JMP, imm)
    elif major in (9, 10):
        insn = CondJump(CondJumpOp.JZ if major == 9 else CondJumpOp.DJNZ, rd, imm)
    elif major == 4 and select < 3:
        insn = Bank(list(BankOp)[select], rd, imm)
    elif major in (5, 14):
        insn = RegPin(list(PinOp)[select], rd, Reg(imm & 3) if major == 5 else imm)
    elif major == 15 and select in (1, 2):
        insn = WaitPin(Reg(imm & 3) if select == 2 else imm, (word >> 8) & 1)
    else:
        for op, code in REG_IMM_CODES.items():
            if code == (major, select):
                insn = RegImm(op, rd, imm)
        for reg_op, code in REG_REG_CODES.items():
            if code == (major, select):
                insn = RegReg(reg_op, rd, Reg(imm & 3))
        for unary_op, code in UNARY_CODES.items():
            if code == (major, select):
                insn = Unary(unary_op, rd)
    if insn is None or encode(insn, cfg) != word:
        raise IsaError(f"noncanonical or reserved instruction {word:#06x}")
    return insn


def mnemonic(insn: Instruction) -> str:
    if isinstance(insn, Nop):
        return "NOP"
    if isinstance(insn, Halt):
        return "HALT"
    if isinstance(insn, WaitPin):
        return "WAITPIN"
    return insn.op.value


def format_instruction(
    insn: Instruction, label_name: Callable[[Label], str] = repr
) -> str:
    def target(t: Target) -> str:
        return label_name(t) if isinstance(t, Label) else str(t)

    name = mnemonic(insn)
    match insn:
        case Nop() | Halt():
            return name
        case RegImm(rd=rd, imm=imm):
            return f"{name} {rd}, {imm}"
        case RegReg(rd=rd, rs=rs):
            return f"{name} {rd}, {rs}"
        case Unary(rd=rd):
            return f"{name} {rd}"
        case Imm(imm=imm):
            return f"{name} {imm}"
        case Jump(target=t):
            return f"{name} {target(t)}"
        case CondJump(rd=rd, target=t):
            return f"{name} {rd}, {target(t)}"
        case RegPin(rd=rd, pin=pin):
            return f"{name} {rd}, {pin}"
        case WaitPin(pin=pin, value=value):
            return f"{name} {pin}, {value}"
        case Bank(rd=rd, bank=bank):
            return f"{name} {rd}, {bank}"


def cycles(insn: Instruction) -> int:
    if isinstance(insn, Imm):
        return insn.imm + 1
    if isinstance(insn, RegReg) and insn.op in (RegRegOp.LOAD, RegRegOp.STORE):
        return 2
    return 1


# Explicit constructors keep Python-generated programs readable.
def NOP() -> Nop:
    return Nop()


def HALT() -> Halt:
    return Halt()


def LDI(rd: Reg, imm: int) -> RegImm:
    return RegImm(RegImmOp.LDI, rd, imm)


def CMPI(rd: Reg, imm: int) -> RegImm:
    return RegImm(RegImmOp.CMPI, rd, imm)


def CMPLTI(rd: Reg, imm: int) -> RegImm:
    return RegImm(RegImmOp.CMPLTI, rd, imm)


def CMPLT(rd: Reg, rs: Reg) -> RegReg:
    return RegReg(RegRegOp.CMPLT, rd, rs)


def ADDI(rd: Reg, imm: int) -> RegImm:
    return RegImm(RegImmOp.ADDI, rd, imm)


def ANDI(rd: Reg, imm: int) -> RegImm:
    return RegImm(RegImmOp.ANDI, rd, imm)


def ORI(rd: Reg, imm: int) -> RegImm:
    return RegImm(RegImmOp.ORI, rd, imm)


def XORI(rd: Reg, imm: int) -> RegImm:
    return RegImm(RegImmOp.XORI, rd, imm)


def MOV(rd: Reg, rs: Reg) -> RegReg:
    return RegReg(RegRegOp.MOV, rd, rs)


def XOR(rd: Reg, rs: Reg) -> RegReg:
    return RegReg(RegRegOp.XOR, rd, rs)


def OR(rd: Reg, rs: Reg) -> RegReg:
    return RegReg(RegRegOp.OR, rd, rs)


def AND(rd: Reg, rs: Reg) -> RegReg:
    return RegReg(RegRegOp.AND, rd, rs)


def LOAD(rd: Reg, address: Reg) -> RegReg:
    return RegReg(RegRegOp.LOAD, rd, address)


def STORE(rs: Reg, address: Reg) -> RegReg:
    return RegReg(RegRegOp.STORE, rs, address)


def SHL(rd: Reg) -> Unary:
    return Unary(UnaryOp.SHL, rd)


def SHR(rd: Reg) -> Unary:
    return Unary(UnaryOp.SHR, rd)


def ROL(rd: Reg) -> Unary:
    return Unary(UnaryOp.ROL, rd)


def ROR(rd: Reg) -> Unary:
    return Unary(UnaryOp.ROR, rd)


def WAIT(imm: int) -> Imm:
    return Imm(ImmOp.WAIT, imm)


def JMP(target: Target) -> Jump:
    return Jump(JumpOp.JMP, target)


def JFAIL(target: Target) -> Jump:
    return Jump(JumpOp.JFAIL, target)


def JZ(rd: Reg, target: Target) -> CondJump:
    return CondJump(CondJumpOp.JZ, rd, target)


def DJNZ(rd: Reg, target: Target) -> CondJump:
    return CondJump(CondJumpOp.DJNZ, rd, target)


def OUTBIT(rs: Reg, pin: int | Reg) -> RegPin:
    return RegPin(PinOp.OUTBIT, rs, pin)


def INBIT(rd: Reg, pin: int | Reg) -> RegPin:
    return RegPin(PinOp.INBIT, rd, pin)


def OEBIT(rs: Reg, pin: int | Reg) -> RegPin:
    return RegPin(PinOp.OEBIT, rs, pin)


def OEBITN(rs: Reg, pin: int | Reg) -> RegPin:
    return RegPin(PinOp.OEBITN, rs, pin)


def WAITPIN(pin: int | Reg, value: int) -> WaitPin:
    return WaitPin(pin, value)


def IN(rd: Reg, bank: int) -> Bank:
    return Bank(BankOp.IN, rd, bank)


def OUT(rd: Reg, bank: int) -> Bank:
    return Bank(BankOp.OUT, rd, bank)


def OE(rd: Reg, bank: int) -> Bank:
    return Bank(BankOp.OE, rd, bank)


def instruction_table() -> str:
    rows = ["| Instruction | Major opcode | Selector |", "|---|---|---|"]
    for op, (major, select) in {
        **REG_IMM_CODES,
        **REG_REG_CODES,
        **UNARY_CODES,
    }.items():
        rows.append(f"| {op.value} | 0x{major:x} | {select} |")
    for op, select in PIN_CODES.items():
        rows.append(f"| {op.value} immediate / register | 0xe / 0x5 | {select} |")
    for op, select in BANK_CODES.items():
        rows.append(f"| {op.value} bank | 0x4 | {select} |")
    rows.extend(
        [
            "| NOP | 0x0 | canonical word 0x0000 |",
            "| WAIT | 0x7 | operand A = 0 |",
            "| JMP / JFAIL | 0x8 | operand A = 0 / 8 |",
            "| JZ / DJNZ | 0x9 / 0xa | A = register |",
            "| HALT | 0xf | canonical word 0xf000 |",
            "| WAITPIN immediate / register | 0xf | A = 4+value / 8+value |",
        ]
    )
    return "\n".join(rows) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--doc", action="store_true")
    parser.parse_args()
    print(instruction_table(), end="")


if __name__ == "__main__":
    main()
