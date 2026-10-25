#!/usr/bin/env python3
"""Typed model of the protocol core's instruction set.

Every instruction is a value of the ``Instruction`` sum type. ``encode`` and
``decode`` convert between those values and machine words for one
``IsaConfig``; the production core is ``BASE``, while the wider study models
add program words, registers, subroutine calls and carry operations.

The 16-bit base layout is ``opcode[15:12] | A[11:8] | immediate[7:0]``. Wider
models add bit 16 (high destination-register bit) and bit 17 (high source-
register bit, branch address bit 9, or carry variant), giving 18-bit words.
"""

from __future__ import annotations

import argparse
import dataclasses
import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, IntEnum
from pathlib import Path
from typing import Literal, assert_never


class IsaError(ValueError):
    """Raised when an instruction cannot be encoded or a word decoded."""


@dataclass(frozen=True)
class Reg:
    index: int

    def __post_init__(self) -> None:
        if not 0 <= self.index <= 7:
            raise IsaError(f"register index must be in the range 0..7: {self.index}")

    def __str__(self) -> str:
        return f"r{self.index}"


r0, r1, r2, r3, r4, r5, r6, r7 = (Reg(index) for index in range(8))


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


class Opcode(IntEnum):
    """Four-bit major opcodes; names match the ``OP_*`` localparams in RTL."""

    NOP = 0x0
    LDI = 0x1
    IN = 0x2
    OUT = 0x3
    OE = 0x4
    SETO = 0x5
    SETOE = 0x6
    WAIT = 0x7
    JMP = 0x8
    JZ = 0x9
    DJNZ = 0xA
    REG = 0xB
    IMM = 0xC
    SHIFT = 0xD
    BIT = 0xE
    SYSTEM = 0xF


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
    PREAD = "PREAD"
    PWRITE = "PWRITE"


class UnaryOp(Enum):
    IN = "IN"
    OUT = "OUT"
    OE = "OE"
    SHL = "SHL"
    SHR = "SHR"
    ROL = "ROL"
    ROR = "ROR"
    SHRC = "SHRC"
    RRC = "RRC"


class ImmOp(Enum):
    SETO = "SETO"
    SETOE = "SETOE"
    WAIT = "WAIT"


class JumpOp(Enum):
    JMP = "JMP"
    JFAIL = "JFAIL"
    JNC = "JNC"


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
        _check_range(target, 1023, "address")


def _check_range(value: int, maximum: int, kind: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):  # pyright: ignore[reportUnnecessaryIsInstance]
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
class Ret:
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
    pin: int

    def __post_init__(self) -> None:
        _check_reg(self.rd)
        _check_range(self.pin, 7, "pin")


@dataclass(frozen=True)
class WaitPin:
    pin: int
    value: int

    def __post_init__(self) -> None:
        _check_range(self.pin, 7, "pin")
        _check_range(self.value, 1, "pin value")


@dataclass(frozen=True)
class Call:
    target: Target

    def __post_init__(self) -> None:
        _check_target(self.target)


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
    | Call
    | Ret
)


@dataclass(frozen=True)
class IsaConfig:
    name: str
    program_words: int
    registers: int
    call: bool = False
    carry: bool = False

    def __post_init__(self) -> None:
        if self.program_words not in (128, 256, 512, 1024):
            raise IsaError(f"unsupported program size: {self.program_words}")
        if self.registers not in (4, 8):
            raise IsaError(f"unsupported register count: {self.registers}")

    @property
    def word_bits(self) -> Literal[16, 18]:
        wide = self.registers > 4 or self.program_words > 512 or self.carry
        return 18 if wide else 16


BASE = IsaConfig("base", 128, 4)
WIDE256 = IsaConfig("wide256", 256, 4)
WIDE512 = IsaConfig("wide512", 512, 4)
FRONTIER = IsaConfig("frontier", 1024, 8)
CALL_FRONTIER = dataclasses.replace(FRONTIER, name="call_frontier", call=True)
CARRY_FRONTIER = dataclasses.replace(CALL_FRONTIER, name="carry_frontier", carry=True)
CONFIGS = {
    c.name: c for c in (BASE, WIDE256, WIDE512, FRONTIER, CALL_FRONTIER, CARRY_FRONTIER)
}

# Major opcode and the two-bit selector stored in A[3:2] for each operation.
REG_IMM_CODES: dict[RegImmOp, tuple[Opcode, int]] = {
    RegImmOp.LDI: (Opcode.LDI, 0),
    RegImmOp.CMPI: (Opcode.LDI, 1),
    RegImmOp.CMPLTI: (Opcode.LDI, 3),
    RegImmOp.ADDI: (Opcode.IMM, 0),
    RegImmOp.ANDI: (Opcode.IMM, 1),
    RegImmOp.ORI: (Opcode.IMM, 2),
    RegImmOp.XORI: (Opcode.IMM, 3),
}
REG_REG_CODES: dict[RegRegOp, tuple[Opcode, int]] = {
    RegRegOp.MOV: (Opcode.REG, 0),
    RegRegOp.XOR: (Opcode.REG, 1),
    RegRegOp.OR: (Opcode.REG, 2),
    RegRegOp.AND: (Opcode.REG, 3),
    RegRegOp.CMPLT: (Opcode.LDI, 2),
    RegRegOp.LOAD: (Opcode.IN, 1),
    RegRegOp.PREAD: (Opcode.IN, 2),
    RegRegOp.STORE: (Opcode.OUT, 1),
    RegRegOp.PWRITE: (Opcode.OUT, 2),
}
UNARY_CODES: dict[UnaryOp, tuple[Opcode, int]] = {
    UnaryOp.IN: (Opcode.IN, 0),
    UnaryOp.OUT: (Opcode.OUT, 0),
    UnaryOp.OE: (Opcode.OE, 0),
    UnaryOp.SHL: (Opcode.SHIFT, 0),
    UnaryOp.SHR: (Opcode.SHIFT, 1),
    UnaryOp.ROL: (Opcode.SHIFT, 2),
    UnaryOp.ROR: (Opcode.SHIFT, 3),
    UnaryOp.SHRC: (Opcode.SHIFT, 1),
    UnaryOp.RRC: (Opcode.SHIFT, 3),
}
IMM_CODES: dict[ImmOp, Opcode] = {
    ImmOp.SETO: Opcode.SETO,
    ImmOp.SETOE: Opcode.SETOE,
    ImmOp.WAIT: Opcode.WAIT,
}
COND_JUMP_CODES: dict[CondJumpOp, Opcode] = {
    CondJumpOp.JZ: Opcode.JZ,
    CondJumpOp.DJNZ: Opcode.DJNZ,
}
PIN_CODES: dict[PinOp, int] = {
    PinOp.OUTBIT: 0,
    PinOp.INBIT: 1,
    PinOp.OEBIT: 2,
    PinOp.OEBITN: 3,
}
CARRY_UNARY = {UnaryOp.SHRC, UnaryOp.RRC}

RD_HIGH = 1 << 16
BIT17 = 1 << 17
JUMP_FAIL = 0x800
JUMP_LONG = 0x400
JUMP_BANK8 = 0x200
JUMP_CARRY = 0x100
COND_BANK8 = 0x800
CALL_FLAG = 0x400
RET_WORD = 0x800
WAITPIN_SELECT = 0b0100

type Resolver = Callable[[Label], int]


def _no_labels(label: Label) -> int:
    raise IsaError(f"unresolved label {label!r}")


def mnemonic(insn: Instruction) -> str:
    match insn:
        case Nop():
            return "NOP"
        case Halt():
            return "HALT"
        case Ret():
            return "RET"
        case Call():
            return "CALL"
        case WaitPin():
            return "WAITPIN"
        case RegImm(op=op) | RegReg(op=op) | Unary(op=op) | Imm(op=op):
            return op.value
        case Jump(op=op) | CondJump(op=op) | RegPin(op=op):
            return op.value
        case _:
            assert_never(insn)


def _register(reg: Reg, cfg: IsaConfig) -> tuple[int, int]:
    """Return the two low register bits and the high-bit flag for bit 16/17."""

    if reg.index >= cfg.registers:
        raise IsaError(f"expected register r0..r{cfg.registers - 1}: {reg}")
    return reg.index & 3, reg.index >> 2


def _fields(opcode: Opcode, select: int, low_register: int, low: int) -> int:
    return opcode << 12 | (select << 2 | low_register) << 8 | low


def _address(target: Target, cfg: IsaConfig, resolve: Resolver) -> int:
    address = resolve(target) if isinstance(target, Label) else target
    _check_range(address, cfg.program_words - 1, "address")
    return address


def _branch_bits(address: int, bank8: int) -> int:
    """Encode a branch target; short targets 0..63 need no extension bits."""

    if address <= 63:
        return address
    bits = JUMP_LONG | address & 0xFF
    if address & 0x100:
        bits |= bank8
    if address & 0x200:
        bits |= BIT17
    return bits


def encode(
    insn: Instruction, cfg: IsaConfig = BASE, resolve: Resolver = _no_labels
) -> int:
    """Return the machine word for one instruction under ``cfg``."""

    match insn:
        case Nop():
            return 0x0000
        case Halt():
            return Opcode.SYSTEM << 12
        case Ret():
            if not cfg.call:
                raise IsaError(f"RET requires a call-capable ISA, not {cfg.name}")
            return RET_WORD
        case Call(target=target):
            if not cfg.call:
                raise IsaError(f"CALL requires a call-capable ISA, not {cfg.name}")
            address = resolve(target) if isinstance(target, Label) else target
            _check_range(address, 1023, "call target")
            _check_range(address, cfg.program_words - 1, "address")
            return CALL_FLAG | address
        case RegImm(op=op, rd=rd, imm=imm):
            opcode, select = REG_IMM_CODES[op]
            low, high = _register(rd, cfg)
            return _fields(opcode, select, low, imm) | high * RD_HIGH
        case RegReg(op=op, rd=rd, rs=rs):
            opcode, select = REG_REG_CODES[op]
            low_d, high_d = _register(rd, cfg)
            low_s, high_s = _register(rs, cfg)
            return (
                _fields(opcode, select, low_d, low_s)
                | high_d * RD_HIGH
                | high_s * BIT17
            )
        case Unary(op=op, rd=rd):
            if op in CARRY_UNARY and not cfg.carry:
                raise IsaError(
                    f"{op.value} requires a carry-capable ISA, not {cfg.name}"
                )
            opcode, select = UNARY_CODES[op]
            low, high = _register(rd, cfg)
            carry = BIT17 if op in CARRY_UNARY else 0
            return _fields(opcode, select, low, 0) | high * RD_HIGH | carry
        case Imm(op=op, imm=imm):
            return IMM_CODES[op] << 12 | imm
        case Jump(op=op, target=target):
            if op is JumpOp.JNC and not cfg.carry:
                raise IsaError(f"JNC requires a carry-capable ISA, not {cfg.name}")
            address = _address(target, cfg, resolve)
            flags = 0 if op is JumpOp.JMP else JUMP_FAIL
            if op is JumpOp.JNC:
                flags |= JUMP_CARRY
            return Opcode.JMP << 12 | flags | _branch_bits(address, JUMP_BANK8)
        case CondJump(op=op, rd=rd, target=target):
            low, high = _register(rd, cfg)
            address = _address(target, cfg, resolve)
            word = COND_JUMP_CODES[op] << 12 | low << 8 | high * RD_HIGH
            return word | _branch_bits(address, COND_BANK8)
        case RegPin(op=op, rd=rd, pin=pin):
            low, high = _register(rd, cfg)
            return _fields(Opcode.BIT, PIN_CODES[op], low, pin) | high * RD_HIGH
        case WaitPin(pin=pin, value=value):
            return Opcode.SYSTEM << 12 | (WAITPIN_SELECT | value) << 8 | pin
        case _:
            assert_never(insn)


def _invert[K, V](table: dict[K, V]) -> dict[V, K]:
    return {value: key for key, value in table.items()}


_REG_IMM_BY_CODE = _invert(REG_IMM_CODES)
_REG_REG_BY_CODE = _invert(REG_REG_CODES)
_UNARY_BY_CODE = _invert(
    {op: code for op, code in UNARY_CODES.items() if op not in CARRY_UNARY}
)
_PIN_BY_CODE = _invert(PIN_CODES)
_IMM_BY_CODE = _invert(IMM_CODES)
_COND_BY_CODE = _invert(COND_JUMP_CODES)
_CARRY_OF = {UnaryOp.SHR: UnaryOp.SHRC, UnaryOp.ROR: UnaryOp.RRC}


def decode(word: int, cfg: IsaConfig = BASE) -> Instruction:
    """Return the instruction whose canonical encoding under ``cfg`` is ``word``.

    Non-canonical words that the core would still execute (for example a long
    branch to an address below 64) are rejected, so ``encode(decode(w)) == w``.
    """

    if not 0 <= word < 1 << cfg.word_bits:
        raise IsaError(f"word {word:#x} does not fit {cfg.name}")
    insn = _decode_fields(word, cfg)
    if insn is None or encode(insn, cfg) != word:
        raise IsaError(f"word {word:#07x} is not a canonical {cfg.name} instruction")
    return insn


def _decode_fields(word: int, cfg: IsaConfig) -> Instruction | None:
    opcode = Opcode(word >> 12 & 0xF)
    a = word >> 8 & 0xF
    imm = word & 0xFF
    select = a >> 2
    high_d = word >> 16 & 1
    bit17 = word >> 17 & 1
    rd_index = high_d << 2 | a & 3
    if rd_index >= cfg.registers:
        return None
    rd = Reg(rd_index)

    def rs() -> Reg | None:
        index = bit17 << 2 | imm & 3
        return Reg(index) if index < cfg.registers else None

    def target(bank8_set: bool) -> int:
        if not a & 0b0100:
            return imm & 0x3F
        return imm | int(bank8_set) << 8 | bit17 << 9

    match opcode:
        case Opcode.NOP:
            if cfg.call and word == RET_WORD:
                return Ret()
            if cfg.call and word & CALL_FLAG:
                return Call(word & 0x3FF)
            return Nop()
        case Opcode.SYSTEM:
            if select == 1:
                return WaitPin(imm & 7, a & 1)
            return Halt()
        case Opcode.SETO | Opcode.SETOE | Opcode.WAIT:
            return Imm(_IMM_BY_CODE[opcode], imm)
        case Opcode.JMP:
            if a & 0b1000:
                op = JumpOp.JNC if cfg.carry and a & 1 else JumpOp.JFAIL
            else:
                op = JumpOp.JMP
            return Jump(op, target(bool(a & 0b0010)))
        case Opcode.JZ | Opcode.DJNZ:
            return CondJump(
                _COND_BY_CODE[opcode],
                Reg(high_d << 2 | a & 3),
                target(bool(a & 0b1000)),
            )
        case Opcode.BIT:
            return RegPin(_PIN_BY_CODE[select], rd, imm & 7)
        case _:
            pass
    key = (opcode, select)
    if key in _REG_IMM_BY_CODE:
        return RegImm(_REG_IMM_BY_CODE[key], rd, imm)
    if key in _REG_REG_BY_CODE:
        source = rs()
        return None if source is None else RegReg(_REG_REG_BY_CODE[key], rd, source)
    if key in _UNARY_BY_CODE:
        op = _UNARY_BY_CODE[key]
        if bit17 and cfg.carry and op in _CARRY_OF:
            op = _CARRY_OF[op]
        return Unary(op, rd)
    return None


def _label_text(label: Label) -> str:
    return label.name if label.name is not None else repr(label)


def format_instruction(
    insn: Instruction, label_name: Callable[[Label], str] = _label_text
) -> str:
    """Return canonical assembly text, e.g. ``LDI r0, 0xa5`` or ``JMP loop``."""

    def target(value: Target) -> str:
        return label_name(value) if isinstance(value, Label) else str(value)

    name = mnemonic(insn)
    match insn:
        case Nop() | Halt() | Ret():
            return name
        case Call(target=t) | Jump(target=t):
            return f"{name} {target(t)}"
        case RegImm(rd=rd, imm=imm):
            return f"{name} {rd}, {imm}"
        case RegReg(rd=rd, rs=rs):
            return f"{name} {rd}, {rs}"
        case Unary(rd=rd):
            return f"{name} {rd}"
        case Imm(imm=imm):
            return f"{name} {imm}"
        case CondJump(rd=rd, target=t):
            return f"{name} {rd}, {target(t)}"
        case RegPin(rd=rd, pin=pin):
            return f"{name} {rd}, {pin}"
        case WaitPin(pin=pin, value=value):
            return f"{name} {pin}, {value}"
        case _:
            assert_never(insn)


def cycles(insn: Instruction) -> int:
    """Clock cycles one instruction occupies when it does not stall on a pin."""

    match insn:
        case Imm(op=ImmOp.WAIT, imm=imm):
            return imm + 1
        case RegReg(
            op=RegRegOp.LOAD | RegRegOp.STORE | RegRegOp.PREAD | RegRegOp.PWRITE
        ):
            return 2
        case _:
            return 1


# Smart constructors, one per mnemonic, so programs read like assembly.
def NOP() -> Nop:
    return Nop()


def HALT() -> Halt:
    return Halt()


def RET() -> Ret:
    return Ret()


def CALL(target: Target) -> Call:
    return Call(target)


def LDI(rd: Reg, imm: int) -> RegImm:
    return RegImm(RegImmOp.LDI, rd, imm)


def CMPI(rd: Reg, imm: int) -> RegImm:
    return RegImm(RegImmOp.CMPI, rd, imm)


def CMPLTI(rd: Reg, imm: int) -> RegImm:
    return RegImm(RegImmOp.CMPLTI, rd, imm)


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


def CMPLT(rd: Reg, rs: Reg) -> RegReg:
    return RegReg(RegRegOp.CMPLT, rd, rs)


def LOAD(rd: Reg, address: Reg) -> RegReg:
    return RegReg(RegRegOp.LOAD, rd, address)


def STORE(rs: Reg, address: Reg) -> RegReg:
    return RegReg(RegRegOp.STORE, rs, address)


def PREAD(rd: Reg, address: Reg) -> RegReg:
    return RegReg(RegRegOp.PREAD, rd, address)


def PWRITE(rs: Reg, address: Reg) -> RegReg:
    return RegReg(RegRegOp.PWRITE, rs, address)


def IN(rd: Reg) -> Unary:
    return Unary(UnaryOp.IN, rd)


def OUT(rs: Reg) -> Unary:
    return Unary(UnaryOp.OUT, rs)


def OE(rs: Reg) -> Unary:
    return Unary(UnaryOp.OE, rs)


def SHL(rd: Reg) -> Unary:
    return Unary(UnaryOp.SHL, rd)


def SHR(rd: Reg) -> Unary:
    return Unary(UnaryOp.SHR, rd)


def ROL(rd: Reg) -> Unary:
    return Unary(UnaryOp.ROL, rd)


def ROR(rd: Reg) -> Unary:
    return Unary(UnaryOp.ROR, rd)


def SHRC(rd: Reg) -> Unary:
    return Unary(UnaryOp.SHRC, rd)


def RRC(rd: Reg) -> Unary:
    return Unary(UnaryOp.RRC, rd)


def SETO(imm: int) -> Imm:
    return Imm(ImmOp.SETO, imm)


def SETOE(imm: int) -> Imm:
    return Imm(ImmOp.SETOE, imm)


def WAIT(imm: int) -> Imm:
    return Imm(ImmOp.WAIT, imm)


def JMP(target: Target) -> Jump:
    return Jump(JumpOp.JMP, target)


def JFAIL(target: Target) -> Jump:
    return Jump(JumpOp.JFAIL, target)


def JNC(target: Target) -> Jump:
    return Jump(JumpOp.JNC, target)


def JZ(rd: Reg, target: Target) -> CondJump:
    return CondJump(CondJumpOp.JZ, rd, target)


def DJNZ(rd: Reg, target: Target) -> CondJump:
    return CondJump(CondJumpOp.DJNZ, rd, target)


def OUTBIT(rs: Reg, pin: int) -> RegPin:
    return RegPin(PinOp.OUTBIT, rs, pin)


def INBIT(rd: Reg, pin: int) -> RegPin:
    return RegPin(PinOp.INBIT, rd, pin)


def OEBIT(rs: Reg, pin: int) -> RegPin:
    return RegPin(PinOp.OEBIT, rs, pin)


def OEBITN(rs: Reg, pin: int) -> RegPin:
    return RegPin(PinOp.OEBITN, rs, pin)


def WAITPIN(pin: int, value: int) -> WaitPin:
    return WaitPin(pin, value)


# --- Generated documentation -------------------------------------------------

DOC_BEGIN = "<!-- isa:begin (generated by `uv run python -m tools.isa --doc`) -->"
DOC_END = "<!-- isa:end -->"
DESIGN = Path(__file__).resolve().parents[1] / "docs/design.md"

_EFFECTS: dict[str, str] = {
    "NOP": "Advance without changing state",
    "LDI": "`rd = imm8`",
    "CMPI": "Flag = `rd == imm8`",
    "CMPLT": "Flag = `rd < rs` (unsigned)",
    "CMPLTI": "Flag = `rd < imm8` (unsigned)",
    "IN": "`rd` = synchronized inputs",
    "LOAD": "`rd` = memory[`rs`]; flag = success; two clocks",
    "PREAD": "`rd` = peripheral[`rs`]; flag = success; two clocks",
    "OUT": "Output-value latch = `rs`",
    "STORE": "memory[`rs`] = `rd`; flag = success; two clocks",
    "PWRITE": "peripheral[`rs`] = `rd`; flag = success; two clocks",
    "OE": "Output-enable latch = `rs`",
    "SETO": "Output-value latch = `imm8`",
    "SETOE": "Output-enable latch = `imm8`",
    "WAIT": "Delay for `imm8+1` clocks total",
    "JMP": "Unconditional branch",
    "JFAIL": "Branch when the flag is clear",
    "JZ": "Branch when `rd == 0`",
    "DJNZ": "Decrement `rd`; branch when the result is nonzero",
    "MOV": "`rd = rs`",
    "XOR": "`rd ^= rs`",
    "OR": "`rd \\|= rs`",
    "AND": "`rd &= rs`",
    "ADDI": "`rd += imm8` (modulo 256)",
    "ANDI": "`rd &= imm8`",
    "ORI": "`rd \\|= imm8`",
    "XORI": "`rd ^= imm8`",
    "SHL": "Logical shift left",
    "SHR": "Logical shift right",
    "ROL": "Rotate left; old bit 7 becomes bit 0",
    "ROR": "Rotate right; old bit 0 becomes bit 7",
    "OUTBIT": "`pin_out[pin] = rs[0]`",
    "INBIT": "`rd[0]` = synchronized `pin` input",
    "OEBIT": "`pin_oe[pin] = rs[0]`",
    "OEBITN": "`pin_oe[pin] = ~rs[0]` (open-drain helper)",
    "WAITPIN": "Hold the PC until the synchronized pin equals `value`",
    "HALT": "Stop fetching until reset or configuration mode",
}


def _doc_examples() -> list[Instruction]:
    a, b = Reg(2), Reg(3)
    return [
        Nop(),
        *(RegImm(op, a, 0xA5) for op in RegImmOp),
        *(RegReg(op, a, b) for op in RegRegOp),
        *(Unary(op, a) for op in UnaryOp if op not in CARRY_UNARY),
        *(Imm(op, 0xA5) for op in ImmOp),
        *(Jump(op, 100) for op in JumpOp if op is not JumpOp.JNC),
        *(CondJump(op, a, 100) for op in CondJumpOp),
        *(RegPin(op, a, 5) for op in PinOp),
        WaitPin(5, 1),
        Halt(),
    ]


def doc_table() -> str:
    """Return the generated Markdown encoding table for the production ISA."""

    rows = [
        "| Assembly | Example | Word | Opcode | `A[3:0]` | Effect |",
        "|---|---|---:|---:|---:|---|",
    ]
    for insn in sorted(_doc_examples(), key=lambda i: (encode(i) >> 12, encode(i))):
        word = encode(insn)
        name = mnemonic(insn)
        rows.append(
            f"| `{name}` | `{format_instruction(insn)}` | `{word:04X}` "
            f"| `{word >> 12:X}` | `{word >> 8 & 0xF:04b}` | {_EFFECTS[name]} |"
        )
    return "\n".join(rows)


def render_design(text: str) -> str:
    pattern = re.compile(re.escape(DOC_BEGIN) + r".*?" + re.escape(DOC_END), re.S)
    if not pattern.search(text):
        raise IsaError("docs/design.md has no generated ISA section markers")
    block = f"{DOC_BEGIN}\n{doc_table()}\n{DOC_END}"
    return pattern.sub(lambda _: block, text)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--doc", action="store_true", help="regenerate docs/design.md tables"
    )
    args = parser.parse_args()
    if args.doc:
        DESIGN.write_text(render_design(DESIGN.read_text()))
    else:
        print(doc_table())


if __name__ == "__main__":
    main()
