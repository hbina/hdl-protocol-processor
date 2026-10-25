"""Isolated generic ISA experiment:1024x18 program words and eight8-bit regs.

No production source is changed. Low16 instruction bits keep their encoding.
Bit16 extends Rd. Bit17 extends Rs for non-branches and address for branches.
The existing three6-bit loader transfers already have room for18 bits.
"""

import re
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.assembler import AssemblyError


def replace(source, old, new, count=1):
    if source.count(old) != count:
        raise RuntimeError(f"audit generic model extension: {old}")
    return source.replace(old, new)


def base_assembler():
    source = (ROOT / "tools/assembler.py").read_text()
    source = replace(source, "PROGRAM_WORDS = 128", "PROGRAM_WORDS = 1024")
    source = replace(
        source,
        "| (0x400 if address > 63 else 0) | address)",
        "| (0x400 if address > 63 else 0) | (address & 255) | (0x200 if address & 256 else 0) | (0x20000 if address & 512 else 0))",
    )
    source = replace(
        source,
        "word = opcode << 12 | rd << 8 | (0x400 if address > 63 else 0) | address",
        "word = opcode << 12 | rd << 8 | (0x400 if address > 63 else 0) | (address & 255) | (0x800 if address & 256 else 0) | (0x20000 if address & 512 else 0)",
    )
    module = types.ModuleType("frontier_assembler")
    # Trusted local assembler, after exact checked replacements.
    exec(compile(source, "<frontier_assembler>", "exec"), module.__dict__)  # noqa: S102
    return module


def assemble(source):
    assembler = base_assembler()
    parsed, labels = assembler._parse_lines(source)
    if any(re.fullmatch(r"[rR][0-7]", name) for name in labels):
        raise AssemblyError("register names cannot be labels in frontier assembly")
    normalized = re.sub(r"\b[rR]([4-7])\b", lambda m: f"r{int(m[1]) & 3}", source)
    words = assembler.assemble(normalized)
    rd_ops = {
        "LDI",
        "CMPI",
        "CMPLTI",
        "ADDI",
        "ANDI",
        "ORI",
        "XORI",
        "IN",
        "OUT",
        "OE",
        "LOAD",
        "STORE",
        "PREAD",
        "PWRITE",
        "CMPLT",
        "MOV",
        "XOR",
        "OR",
        "AND",
        "SHL",
        "SHR",
        "ROL",
        "ROR",
        "OUTBIT",
        "INBIT",
        "OEBIT",
        "OEBITN",
        "JZ",
        "DJNZ",
    }
    rs_ops = {"LOAD", "STORE", "PREAD", "PWRITE", "CMPLT", "MOV", "XOR", "OR", "AND"}
    for index, (_line, opcode, args) in enumerate(parsed):
        if opcode in rd_ops and int(args[0][1:]) >= 4:
            words[index] |= 0x10000
        if opcode in rs_ops and int(args[1][1:]) >= 4:
            words[index] |= 0x20000
    return words


def expanded_source():
    source = (ROOT / "src/protocol_core.v").read_text()
    for old, new in [
        ("reg [15:0] program_mem [0:127];", "reg [17:0] program_mem [0:1023];"),
        ("reg [7:0] registers [0:3];", "reg [7:0] registers [0:7];"),
        ("reg [6:0] pc;", "reg [9:0] pc;"),
        ("reg [6:0]  cfg_address;", "reg [9:0]  cfg_address;"),
        ("reg [1:0] memory_destination;", "reg [2:0] memory_destination;"),
        (
            "wire [15:0] instruction = program_mem[pc];",
            "wire [17:0] instruction = program_mem[pc];",
        ),
        (
            "wire [1:0] register_d = operand_a[1:0];",
            "wire [2:0] register_d = {instruction[16], operand_a[1:0]};",
        ),
        (
            "wire [1:0] register_s = immediate[1:0];",
            "wire [2:0] register_s = {instruction[17], immediate[1:0]};",
        ),
        (
            "program_mem[cfg_address] <= {cfg_data[3:0], cfg_partial};",
            "program_mem[cfg_address] <= {cfg_data, cfg_partial};",
        ),
    ]:
        source = replace(source, old, new)
    old = "operand_a[2] ? immediate[6:0] : {1'b0, immediate[5:0]}"
    source = replace(
        source,
        old,
        "operand_a[2] ? {instruction[17], operand_a[1], immediate} : {4'b0, immediate[5:0]}",
        3,
    )
    # Conditional branches use the existing bit8 location from their encoding.
    old = "{instruction[17], operand_a[1], immediate}"
    positions = [match.start() for match in re.finditer(re.escape(old), source)]
    assert len(positions) == 3
    for position in reversed(positions[1:]):
        source = (
            source[:position]
            + "{instruction[17], operand_a[3], immediate}"
            + source[position + len(old) :]
        )
    old = "registers[3] <= 8'h00;"
    new = old + "\n      " + " ".join(f"registers[{r}] <= 8'h00;" for r in range(4, 8))
    return replace(source, old, new, 2)
