"""Tool behavior and active firmware contracts for the incompatible pin ISA."""

import json
from pathlib import Path
import subprocess
import sys
import pytest
from tools.assembler import assemble, assemble_image, parse
from tools.isa import (
    BASE,
    IsaConfig,
    IsaError,
    Reg,
    Label,
    INBIT,
    OUTBIT,
    LOAD,
    STORE,
    WAIT,
    WAITPIN,
    JMP,
    HALT,
    LDI,
    NOP,
    encode,
    decode,
    cycles,
)
from tools.program import Program
from tools.snapshot_isa import GOLDEN, snapshot

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "source",
    [
        "PREAD r0,r1",
        "PWRITE r0,r1",
        "CALL 1",
        "RET",
        "SHRC r0",
        "SETO 1",
        "SETOE 1",
        "LDI r4,0",
        "LDI r0,256",
        "INBIT r0,15",
        "OUTBIT r0,16",
        "IN r0,2",
        "OUT r0,2",
        "OE r0,-1",
        "WAITPIN 0,2",
        "WAITPIN r4,0",
        "JMP 256",
        "LDI r0",
        "LDI r0,1,2",
        "bad: NOP\nbad: HALT",
        "JMP unknown",
        "NOP\n" * 257,
        "JMP end\n" + "NOP\n" * 255 + "end:",
    ],
)
def test_invalid_assembly(source):
    with pytest.raises(IsaError):
        assemble(source)


@pytest.mark.parametrize("count", [0, -1, 257, True])
def test_invalid_counts(count):
    with pytest.raises(IsaError):
        IsaConfig(input_pins=count)
    with pytest.raises(IsaError):
        IsaConfig(output_pins=count)


@pytest.mark.parametrize("address", [0, 63, 64, 127, 128, 255])
def test_branches(address):
    for source in [
        f"JMP {address}",
        f"JFAIL {address}",
        f"JZ r3,{address}",
        f"DJNZ r2,{address}",
    ]:
        word = assemble(source)[0]
        assert word & 255 == address
        assert encode(decode(word)) == word


@pytest.mark.parametrize(
    "source",
    [
        "INBIT r0,14",
        "INBIT r0,r0",
        "OUTBIT r2,r1",
        "OEBIT r3,15",
        "OEBITN r0,r2",
        "WAITPIN r3,0",
        "WAITPIN 14,1",
        "IN r2,1",
        "OUT r1,1",
        "OE r2,1",
        "CMPI r1,99",
        "CMPLTI r2,55",
        "CMPLT r3,r0",
        "JFAIL 255",
        "NOP",
        "HALT",
        "WAIT 255",
        "LOAD r1,r1",
        "STORE r2,r2",
    ],
)
def test_round_trip(source):
    image = assemble_image(source)
    assert assemble(image.disassemble()) == image.words
    assert parse(source).link().words == image.words


@pytest.mark.parametrize(
    "word",
    [
        0x0001,
        0x6000,
        0x7001 | 0x100,
        0x8400,
        0x9400,
        0xB004,
        0xD001,
        0x5404,
        0xF600,
        0xF804,
        0xF001,
        0x2C00,
    ],
)
def test_reserved(word):
    with pytest.raises(IsaError):
        decode(word)


def test_dynamic_and_bank_limits():
    cfg = IsaConfig(input_pins=256, output_pins=256)
    for text in [
        "INBIT r3,255",
        "OUTBIT r3,255",
        "IN r3,31",
        "OE r3,31",
        "WAITPIN 255,0",
    ]:
        word = assemble(text, cfg)[0]
        assert encode(decode(word, cfg), cfg) == word
    assert (
        len(
            assemble(
                "INBIT r0,r1\nOUTBIT r0,r1", IsaConfig(input_pins=1, output_pins=1)
            )
        )
        == 2
    )
    assert BASE.program_words == 256


def test_timing_and_values():
    assert cycles(LOAD(Reg(0), Reg(1))) == 2
    assert cycles(STORE(Reg(0), Reg(1))) == 2
    assert cycles(WAIT(255)) == 256
    assert cycles(INBIT(Reg(0), 1)) == 1
    assert cycles(WAITPIN(0, 1)) == 1  # minimum; may stall indefinitely
    with pytest.raises(IsaError):
        Reg(True)
    with pytest.raises(IsaError):
        Reg(4)
    with pytest.raises(IsaError):
        INBIT(Reg(0), 256)


def test_labels_and_program():
    target = Label("end")
    p = Program([JMP(target), NOP(), target, HALT()])
    assert p.link().symbols == {"end": 2}
    assert assemble(p.to_asm()) == p.link().words
    with pytest.raises(IsaError):
        Program([JMP(Label("missing"))]).link()
    with pytest.raises(IsaError):
        Program([target, target]).link()
    with pytest.raises(IsaError):
        Program([NOP()] * 257).link()


def test_active_snapshot():
    assert snapshot() == json.loads(GOLDEN.read_text())
    assert len(snapshot()) == 5
    assert all(len(entry["words"]) <= 256 for entry in snapshot().values())


def test_cli_pin_configuration(tmp_path):
    src = tmp_path / "high.asm"
    src.write_text("INBIT r0,255\nOUTBIT r0,255\nHALT\n")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.assembler",
            str(src),
            "--input-pins",
            "256",
            "--output-pins",
            "256",
            "--disassemble",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "INBIT r0, 255" in result.stdout
    rejected = subprocess.run(
        [sys.executable, "-m", "tools.assembler", str(src)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert rejected.returncode != 0


def test_generated_isa_table():
    from tools.isa import instruction_table

    docs = (ROOT / "docs/pin_processor.md").read_text()
    assert instruction_table().strip() in docs
