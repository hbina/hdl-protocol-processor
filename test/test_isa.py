"""Typed instruction model: encoding tables, boundaries and round trips."""

import itertools

import pytest

from tools import isa
from tools.isa import (
    BASE,
    CALL_FRONTIER,
    CARRY_FRONTIER,
    CONFIGS,
    FRONTIER,
    WIDE512,
    CondJump,
    CondJumpOp,
    Imm,
    ImmOp,
    IsaError,
    Jump,
    JumpOp,
    PinOp,
    Reg,
    RegImm,
    RegImmOp,
    RegPin,
    RegReg,
    RegRegOp,
    Unary,
    UnaryOp,
    decode,
    encode,
    r0,
    r2,
    r3,
    r4,
    r7,
)

OPERATION_TABLES = [
    (isa.RegImmOp, isa.REG_IMM_CODES),
    (isa.RegRegOp, isa.REG_REG_CODES),
    (isa.UnaryOp, isa.UNARY_CODES),
    (isa.ImmOp, isa.IMM_CODES),
    (isa.CondJumpOp, isa.COND_JUMP_CODES),
    (isa.PinOp, isa.PIN_CODES),
]
ALL_OPERATIONS = [
    *isa.RegImmOp,
    *isa.RegRegOp,
    *isa.UnaryOp,
    *isa.ImmOp,
    *isa.JumpOp,
    *isa.CondJumpOp,
    *isa.PinOp,
]


@pytest.mark.parametrize("enum,table", OPERATION_TABLES)
def test_every_operation_has_an_encoding(enum, table):
    assert set(table) == set(enum)


def test_every_mnemonic_has_one_smart_constructor():
    mnemonics = [op.value for op in ALL_OPERATIONS] + [
        "NOP",
        "HALT",
        "RET",
        "CALL",
        "WAITPIN",  # fmt: skip
    ]
    assert len(mnemonics) == len(set(mnemonics))
    for name in mnemonics:
        assert callable(getattr(isa, name)), name


def instructions(cfg):
    """Every operation at its operand boundaries for ``cfg``."""

    regs = [Reg(i) for i in range(cfg.registers)]
    bytes_ = [0, 1, 0x3F, 0x40, 0x7F, 0x80, 0xFF]
    targets = [
        a
        for a in [0, 1, 63, 64, 127, 128, 255, 256, 511, 512, 767, 1023]
        if a < cfg.program_words
    ]
    yield from [isa.Nop(), isa.Halt()]
    if cfg.call:
        yield isa.Ret()
        yield from (isa.Call(t) for t in targets)
    for op, rd, imm in itertools.product(RegImmOp, regs, bytes_):
        yield RegImm(op, rd, imm)
    for op, rd, rs in itertools.product(RegRegOp, regs, regs):
        yield RegReg(op, rd, rs)
    for op, rd in itertools.product(UnaryOp, regs):
        if op in isa.CARRY_UNARY and not cfg.carry:
            continue
        yield Unary(op, rd)
    for op, imm in itertools.product(ImmOp, bytes_):
        yield Imm(op, imm)
    for op, target in itertools.product(JumpOp, targets):
        if op is JumpOp.JNC and not cfg.carry:
            continue
        yield Jump(op, target)
    for op, rd, target in itertools.product(CondJumpOp, regs, targets):
        yield CondJump(op, rd, target)
    for op, rd, pin in itertools.product(PinOp, regs, range(8)):
        yield RegPin(op, rd, pin)
    for pin, value in itertools.product(range(8), range(2)):
        yield isa.WaitPin(pin, value)


@pytest.mark.parametrize("cfg", CONFIGS.values(), ids=CONFIGS)
def test_decode_inverts_encode(cfg):
    words = {}
    for insn in instructions(cfg):
        word = encode(insn, cfg)
        assert 0 <= word < 1 << cfg.word_bits
        assert decode(word, cfg) == insn, (insn, hex(word))
        assert words.setdefault(word, insn) == insn, "two instructions share a word"


@pytest.mark.parametrize("cfg", [BASE, WIDE512, CARRY_FRONTIER], ids=lambda c: c.name)
def test_every_decodable_word_reencodes_exactly(cfg):
    decoded = 0
    for word in range(1 << cfg.word_bits):
        try:
            insn = decode(word, cfg)
        except IsaError:
            continue
        decoded += 1
        assert encode(insn, cfg) == word, hex(word)
    assert decoded > 1000


def test_production_golden_words():
    assert [
        encode(i)
        for i in [
            isa.LDI(r2, 0xA5),
            isa.OUTBIT(r2, 7),
            isa.DJNZ(r2, 1),
            isa.WAITPIN(3, 1),
            isa.HALT(),
            isa.LOAD(r2, r3),
            isa.STORE(r2, r3),
            isa.PREAD(r2, r3),
            isa.PWRITE(r2, r3),
            isa.CMPLT(r2, r3),
            isa.JMP(63),
            isa.JMP(64),
            isa.JFAIL(64),
            isa.JZ(r2, 64),
            isa.DJNZ(r3, 127),
            isa.CMPI(Reg(1), 255),
            isa.CMPLTI(r2, 65),
        ]
    ] == [
        0x12A5, 0xE207, 0xA201, 0xF503, 0xF000, 0x2603, 0x3603, 0x2A03,
        0x3A03, 0x1A03, 0x803F, 0x8440, 0x8C40, 0x9640, 0xA77F, 0x15FF, 0x1E41,
    ]  # fmt: skip


def test_wide_golden_words():
    assert [
        encode(i, FRONTIER)
        for i in [
            isa.LDI(r7, 0xA5),
            isa.MOV(r0, r7),
            isa.DJNZ(r7, 512),
            isa.JZ(r4, 1023),
            isa.JMP(1023),
            isa.JFAIL(512),
        ]
    ] == [0x113A5, 0x2B003, 0x3A700, 0x39CFF, 0x286FF, 0x28C00]
    assert encode(isa.JMP(300), WIDE512) == 0x862C
    assert encode(isa.JZ(r0, 300), WIDE512) == 0x9C2C
    assert [encode(i, CARRY_FRONTIER) for i in [isa.SHRC(r3), isa.RRC(Reg(6))]] == [
        0x2D700,
        0x3DE00,
    ]
    assert encode(isa.JNC(512), CARRY_FRONTIER) == 0x28D00
    assert [
        encode(i, CALL_FRONTIER) for i in [isa.CALL(0), isa.CALL(1023), isa.RET()]
    ] == [
        0x0400,
        0x07FF,
        0x0800,
    ]


@pytest.mark.parametrize(
    "insn,cfg,message",
    [
        (isa.LDI(r4, 0), BASE, "expected register r0..r3: r4"),
        (isa.JMP(128), BASE, "address must be in the range 0..127: 128"),
        (isa.JMP(512), WIDE512, "address must be in the range 0..511: 512"),
        (isa.CALL(0), FRONTIER, "CALL requires a call-capable ISA"),
        (isa.RET(), BASE, "RET requires a call-capable ISA"),
        (isa.SHRC(r0), CALL_FRONTIER, "SHRC requires a carry-capable ISA"),
        (isa.JNC(0), FRONTIER, "JNC requires a carry-capable ISA"),
    ],
)
def test_configuration_limits_are_enforced(insn, cfg, message):
    with pytest.raises(IsaError, match=message):
        encode(insn, cfg)


@pytest.mark.parametrize(
    "build",
    [
        lambda: isa.LDI(r0, 256),
        lambda: isa.LDI(r0, -1),
        lambda: isa.WAIT(True),
        lambda: isa.OUTBIT(r0, 8),
        lambda: isa.WAITPIN(0, 2),
        lambda: isa.JMP(1024),
        lambda: isa.LDI(0x5A, r0),  # type: ignore[arg-type]  # swapped operands
        lambda: isa.MOV(r0, 1),  # type: ignore[arg-type]
        lambda: Reg(8),
    ],
)
def test_bad_operands_fail_at_construction(build):
    with pytest.raises(IsaError):
        build()


def test_non_canonical_words_are_rejected():
    for word in [0x8420, 0x2004, 0x4400, 0xF001, 0x0001]:
        with pytest.raises(IsaError):
            decode(word)
    with pytest.raises(IsaError):
        decode(0x10000)


def test_cycles():
    assert isa.cycles(isa.WAIT(0)) == 1
    assert isa.cycles(isa.WAIT(255)) == 256
    assert isa.cycles(isa.LOAD(r0, Reg(1))) == 2
    assert isa.cycles(isa.MOV(r0, Reg(1))) == 1
    assert isa.cycles(isa.JMP(0)) == 1
