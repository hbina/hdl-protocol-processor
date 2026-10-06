#!/usr/bin/env python3
"""Assembler for the protocol emulator's compact 16-bit instruction set."""

from __future__ import annotations

import argparse
import pathlib
import re
from collections.abc import Iterable

PROGRAM_WORDS = 64


class AssemblyError(ValueError):
    """Raised when source cannot be encoded."""


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


def _register(token: str) -> int:
    match = re.fullmatch(r"[rR]([0-3])", token.strip())
    if not match:
        raise AssemblyError(f"expected register r0..r3: {token}")
    return int(match.group(1))


def _parse_lines(source: str) -> tuple[list[tuple[int, str, list[str]]], dict[str, int]]:
    instructions: list[tuple[int, str, list[str]]] = []
    labels: dict[str, int] = {}

    for line_number, original in enumerate(source.splitlines(), start=1):
        line = original.split("#", 1)[0].split(";", 1)[0].strip()
        if not line:
            continue

        if ":" in line:
            label, line = line.split(":", 1)
            label = label.strip()
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", label):
                raise AssemblyError(f"line {line_number}: invalid label {label!r}")
            if label in labels:
                raise AssemblyError(f"line {line_number}: duplicate label {label!r}")
            labels[label] = len(instructions)
            line = line.strip()
            if not line:
                continue

        fields = line.replace(",", " ").split()
        instructions.append((line_number, fields[0].upper(), fields[1:]))

    if len(instructions) > PROGRAM_WORDS:
        raise AssemblyError(
            f"program contains {len(instructions)} words; maximum is {PROGRAM_WORDS}"
        )
    return instructions, labels


def _expect(args: list[str], count: int, mnemonic: str, line_number: int) -> None:
    if len(args) != count:
        raise AssemblyError(
            f"line {line_number}: {mnemonic} expects {count} operand(s), got {len(args)}"
        )


def assemble(source: str) -> list[int]:
    """Assemble source text and return a list of 16-bit instruction words."""

    parsed, labels = _parse_lines(source)
    words: list[int] = []

    for line_number, mnemonic, args in parsed:
        try:
            if mnemonic == "NOP":
                _expect(args, 0, mnemonic, line_number)
                word = 0x0000
            elif mnemonic in {"LDI", "ADDI", "ANDI", "ORI", "XORI"}:
                _expect(args, 2, mnemonic, line_number)
                rd = _register(args[0])
                imm = _bounded(args[1], labels, 0xFF, "immediate")
                if mnemonic == "LDI":
                    word = 0x1000 | (rd << 8) | imm
                else:
                    subop = {"ADDI": 0, "ANDI": 1, "ORI": 2, "XORI": 3}[mnemonic]
                    word = 0xC000 | ((subop << 2 | rd) << 8) | imm
            elif mnemonic in {"IN", "OUT", "OE"}:
                _expect(args, 1, mnemonic, line_number)
                rd = _register(args[0])
                opcode = {"IN": 0x2, "OUT": 0x3, "OE": 0x4}[mnemonic]
                word = opcode << 12 | rd << 8
            elif mnemonic in {"SETO", "SETOE", "WAIT"}:
                _expect(args, 1, mnemonic, line_number)
                imm = _bounded(args[0], labels, 0xFF, "immediate")
                opcode = {"SETO": 0x5, "SETOE": 0x6, "WAIT": 0x7}[mnemonic]
                word = opcode << 12 | imm
            elif mnemonic == "JMP":
                _expect(args, 1, mnemonic, line_number)
                word = 0x8000 | _bounded(args[0], labels, 0x3F, "address")
            elif mnemonic in {"JZ", "DJNZ"}:
                _expect(args, 2, mnemonic, line_number)
                rd = _register(args[0])
                address = _bounded(args[1], labels, 0x3F, "address")
                opcode = 0x9 if mnemonic == "JZ" else 0xA
                word = opcode << 12 | rd << 8 | address
            elif mnemonic in {"MOV", "XOR", "OR", "AND"}:
                _expect(args, 2, mnemonic, line_number)
                rd = _register(args[0])
                rs = _register(args[1])
                subop = {"MOV": 0, "XOR": 1, "OR": 2, "AND": 3}[mnemonic]
                word = 0xB000 | ((subop << 2 | rd) << 8) | rs
            elif mnemonic in {"SHL", "SHR", "ROL", "ROR"}:
                _expect(args, 1, mnemonic, line_number)
                rd = _register(args[0])
                subop = {"SHL": 0, "SHR": 1, "ROL": 2, "ROR": 3}[mnemonic]
                word = 0xD000 | ((subop << 2 | rd) << 8)
            elif mnemonic in {"OUTBIT", "INBIT", "OEBIT", "OEBITN"}:
                _expect(args, 2, mnemonic, line_number)
                rd = _register(args[0])
                pin = _bounded(args[1], labels, 7, "pin")
                subop = {"OUTBIT": 0, "INBIT": 1, "OEBIT": 2, "OEBITN": 3}[
                    mnemonic
                ]
                word = 0xE000 | ((subop << 2 | rd) << 8) | pin
            elif mnemonic == "WAITPIN":
                _expect(args, 2, mnemonic, line_number)
                pin = _bounded(args[0], labels, 7, "pin")
                expected = _bounded(args[1], labels, 1, "pin value")
                word = 0xF000 | ((0b0100 | expected) << 8) | pin
            elif mnemonic == "HALT":
                _expect(args, 0, mnemonic, line_number)
                word = 0xF000
            else:
                raise AssemblyError(f"line {line_number}: unknown instruction {mnemonic}")
        except AssemblyError as exc:
            if str(exc).startswith("line "):
                raise
            raise AssemblyError(f"line {line_number}: {exc}") from exc

        words.append(word)

    return words


def words_to_hex(words: Iterable[int]) -> str:
    """Return one four-digit hexadecimal instruction per line."""

    return "".join(f"{word:04x}\n" for word in words)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=pathlib.Path, help="assembly input file")
    parser.add_argument("-o", "--output", type=pathlib.Path, help="hex output file")
    args = parser.parse_args()

    output = words_to_hex(assemble(args.source.read_text()))
    if args.output:
        args.output.write_text(output)
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
