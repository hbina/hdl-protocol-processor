#!/usr/bin/env python3
"""Assembler for the protocol emulator's compact instruction set.

Text is parsed into the typed instruction model in ``tools.isa`` and linked by
``tools.program``; this module only handles syntax, labels and operand text.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
from collections.abc import Callable, Iterable

if __package__ in (None, ""):  # Run as a script: make the `tools` package importable.
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from tools.isa import (
    BASE,
    CONFIGS,
    Call,
    CondJump,
    CondJumpOp,
    Halt,
    Imm,
    ImmOp,
    Instruction,
    IsaConfig,
    IsaError,
    Jump,
    JumpOp,
    Label,
    Nop,
    PinOp,
    Reg,
    RegImm,
    RegImmOp,
    RegPin,
    RegReg,
    RegRegOp,
    Ret,
    Target,
    Unary,
    UnaryOp,
    WaitPin,
)
from tools.program import Comment, Image, Program

PROGRAM_WORDS = BASE.program_words

AssemblyError = IsaError
"""Raised when source cannot be encoded (a ``ValueError``)."""


type ParsedLine = tuple[int, str, list[str]]
# Source order of labels, instructions (by index) and full-line comments.
type Event = tuple[str, str | int]


def _number(token: str, labels: dict[str, int]) -> int:
    token = token.strip()
    if token in labels:
        return labels[token]
    try:
        return int(token, 0)
    except ValueError as exc:
        raise AssemblyError(f"unknown number or label: {token}") from exc


def _bounded(token: str, labels: dict[str, int], maximum: int, kind: str) -> int:
    value = _number(token, labels)
    if not 0 <= value <= maximum:
        raise AssemblyError(f"{kind} must be in the range 0..{maximum}: {token}")
    return value


def _register(token: str, cfg: IsaConfig) -> Reg:
    match = re.fullmatch(r"[rR]([0-7])", token.strip())
    if not match or int(match.group(1)) >= cfg.registers:
        raise AssemblyError(f"expected register r0..r{cfg.registers - 1}: {token}")
    return Reg(int(match.group(1)))


def _parse_lines(
    source: str, cfg: IsaConfig = BASE, events: list[Event] | None = None
) -> tuple[list[ParsedLine], dict[str, int]]:
    instructions: list[ParsedLine] = []
    labels: dict[str, int] = {}
    order: list[Event] = [] if events is None else events

    for line_number, original in enumerate(source.splitlines(), start=1):
        if original.strip().startswith("#"):
            order.append(("comment", original.strip()[1:].strip()))
            continue
        line = original.split("#", 1)[0].split(";", 1)[0].strip()
        if not line:
            continue

        if ":" in line:
            label, line = line.split(":", 1)
            label = label.strip()
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", label):
                raise AssemblyError(f"line {line_number}: invalid label {label!r}")
            if re.fullmatch(r"[rR][0-7]", label):
                raise AssemblyError(
                    f"line {line_number}: register names cannot be labels: {label!r}"
                )
            if label in labels:
                raise AssemblyError(f"line {line_number}: duplicate label {label!r}")
            labels[label] = len(instructions)
            order.append(("label", label))
            line = line.strip()
            if not line:
                continue

        fields = line.replace(",", " ").split()
        order.append(("insn", len(instructions)))
        instructions.append((line_number, fields[0].upper(), fields[1:]))

    if len(instructions) > cfg.program_words:
        raise AssemblyError(
            f"program contains {len(instructions)} words; maximum is {cfg.program_words}"
        )
    return instructions, labels


def _expect(args: list[str], count: int, mnemonic: str) -> None:
    if len(args) != count:
        raise AssemblyError(f"{mnemonic} expects {count} operand(s), got {len(args)}")


class _Operands:
    """Operand decoding for one source program."""

    def __init__(self, cfg: IsaConfig, labels: dict[str, int]) -> None:
        self.cfg = cfg
        self.labels = labels
        self.objects = {name: Label(name) for name in labels}

    def register(self, token: str) -> Reg:
        return _register(token, self.cfg)

    def byte(self, token: str) -> int:
        return _bounded(token, self.labels, 0xFF, "immediate")

    def pin(self, token: str) -> int:
        return _bounded(token, self.labels, 7, "pin")

    def target(self, token: str, maximum: int, kind: str = "address") -> Target:
        if token.strip() in self.objects:
            return self.objects[token.strip()]
        return _bounded(token, self.labels, maximum, kind)


def _extensions(cfg: IsaConfig) -> set[str]:
    names: set[str] = set()
    if cfg.call:
        names |= {"CALL", "RET"}
    if cfg.carry:
        names |= {UnaryOp.SHRC.value, UnaryOp.RRC.value, JumpOp.JNC.value}
    return names


_OPTIONAL = {"CALL", "RET", UnaryOp.SHRC.value, UnaryOp.RRC.value, JumpOp.JNC.value}


def _instruction(mnemonic: str, args: list[str], ops: _Operands) -> Instruction:
    cfg = ops.cfg
    if mnemonic in _OPTIONAL and mnemonic not in _extensions(cfg):
        raise AssemblyError(f"unknown instruction {mnemonic}")
    last = cfg.program_words - 1

    def shape(count: int) -> list[str]:
        _expect(args, count, mnemonic)
        return args

    if mnemonic in ("NOP", "HALT", "RET"):
        shape(0)
        return {"NOP": Nop(), "HALT": Halt(), "RET": Ret()}[mnemonic]
    if mnemonic == "CALL":
        (target,) = shape(1)
        return Call(ops.target(target, 1023, "call target"))
    if mnemonic == "WAITPIN":
        pin, value = shape(2)
        return WaitPin(ops.pin(pin), _bounded(value, ops.labels, 1, "pin value"))
    if mnemonic in RegImmOp.__members__:
        rd, imm = shape(2)
        return RegImm(RegImmOp[mnemonic], ops.register(rd), ops.byte(imm))
    if mnemonic in RegRegOp.__members__:
        rd, rs = shape(2)
        return RegReg(RegRegOp[mnemonic], ops.register(rd), ops.register(rs))
    if mnemonic in UnaryOp.__members__:
        (rd,) = shape(1)
        return Unary(UnaryOp[mnemonic], ops.register(rd))
    if mnemonic in ImmOp.__members__:
        (imm,) = shape(1)
        return Imm(ImmOp[mnemonic], ops.byte(imm))
    if mnemonic in JumpOp.__members__:
        (target,) = shape(1)
        return Jump(JumpOp[mnemonic], ops.target(target, last))
    if mnemonic in CondJumpOp.__members__:
        rd, target = shape(2)
        return CondJump(
            CondJumpOp[mnemonic], ops.register(rd), ops.target(target, last)
        )
    if mnemonic in PinOp.__members__:
        rd, pin = shape(2)
        return RegPin(PinOp[mnemonic], ops.register(rd), ops.pin(pin))
    raise AssemblyError(f"unknown instruction {mnemonic}")


def parse(source: str, cfg: IsaConfig = BASE) -> Program:
    """Parse assembly text into a typed program for ``cfg``.

    Labels, instructions and full-line comments keep their source order;
    trailing comments on instruction lines are not retained.
    """

    events: list[Event] = []
    parsed, labels = _parse_lines(source, cfg, events)
    ops = _Operands(cfg, labels)
    program = Program()
    for kind, value in events:
        if kind == "comment":
            program.add(Comment(str(value)))
        elif kind == "label":
            program.mark(ops.objects[str(value)])
        else:
            line_number, mnemonic, args = parsed[int(value)]
            try:
                insn = _instruction(mnemonic, args, ops)
            except IsaError as exc:
                raise AssemblyError(f"line {line_number}: {exc}") from exc
            program.add(insn, origin=f"line {line_number}")
    return program


def labels(source: str, cfg: IsaConfig = BASE) -> dict[str, int]:
    """Return label addresses without encoding any instruction."""

    return _parse_lines(source, cfg)[1]


def assemble_image(source: str, cfg: IsaConfig = BASE) -> Image:
    """Assemble source text into linked words and its label table."""

    return parse(source, cfg).link(cfg)


def assemble(source: str, cfg: IsaConfig = BASE) -> list[int]:
    """Assemble source text and return a list of instruction words."""

    return assemble_image(source, cfg).words


def assembler_for(cfg: IsaConfig) -> Callable[[str], list[int]]:
    return lambda source: assemble(source, cfg)


def words_to_hex(words: Iterable[int], digits: int = 4) -> str:
    """Return one hexadecimal instruction per line."""

    return "".join(f"{word:0{digits}x}\n" for word in words)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=pathlib.Path, help="assembly input file")
    parser.add_argument("-o", "--output", type=pathlib.Path, help="hex output file")
    parser.add_argument("--isa", choices=sorted(CONFIGS), default=BASE.name)
    parser.add_argument(
        "--disassemble", action="store_true", help="print an annotated listing"
    )
    args = parser.parse_args()

    cfg = CONFIGS[args.isa]
    image = assemble_image(args.source.read_text(), cfg)
    if args.disassemble:
        output = image.disassemble()
    else:
        output = words_to_hex(image.words, 4 if cfg.word_bits == 16 else 5)
    if args.output:
        args.output.write_text(output)
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
