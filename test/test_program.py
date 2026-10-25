"""Program builder, linker, listings and the text front end."""

from pathlib import Path

import pytest

from tools.assembler import AssemblyError, assemble, assemble_image, parse
from tools.isa import (
    BASE,
    CARRY_FRONTIER,
    DJNZ,
    HALT,
    JMP,
    LDI,
    NOP,
    OUTBIT,
    SHRC,
    WAIT,
    IsaError,
    Label,
    r0,
    r2,
)
from tools.program import Comment, Program

ROOT = Path(__file__).resolve().parents[1]


def test_builder_matches_text_assembly():
    loop = Label("loop")
    program = Program()
    program += LDI(r2, 0xA5)
    program.mark(loop)
    program += [OUTBIT(r2, 7), DJNZ(r2, loop), HALT()]
    image = program.link()
    assert image.words == assemble(
        "LDI r2, 0xa5\nloop: OUTBIT r2, 7\nDJNZ r2, loop\nHALT"
    )
    assert image.symbols == {"loop": 1}


def test_pad_to_places_far_targets():
    far = Label("far")
    program = Program([JMP(far)])
    program.pad_to(127).mark(far)
    program += HALT()
    image = program.link()
    assert len(image.words) == 128 and image.words[0] == 0x847F
    assert image.words[1:127] == [0] * 126
    with pytest.raises(IsaError, match="cannot pad to 3"):
        Program([NOP()] * 4).pad_to(3)


def test_link_errors():
    with pytest.raises(IsaError, match="undefined label nowhere"):
        Program([JMP(Label("nowhere"))]).link()
    here = Label("here")
    with pytest.raises(IsaError, match="duplicate label 'here'"):
        Program([here, NOP(), here]).link()
    with pytest.raises(IsaError, match="duplicate label 'same'"):
        Program([Label("same"), NOP(), Label("same")]).link()
    with pytest.raises(IsaError, match="program contains 129 words; maximum is 128"):
        Program([NOP()] * 129).link()
    with pytest.raises(IsaError, match=r"word 0 \(SHRC r0\): SHRC requires"):
        Program([SHRC(r0)]).link(BASE)


def test_anonymous_labels_are_unique_in_listings():
    first, second = Label(), Label()
    program = Program([Comment("two loops"), first, JMP(first), second, JMP(second)])
    text = program.to_asm()
    assert text == "# two loops\n_L0:\nJMP _L0\n_L1:\nJMP _L1\n"
    assert assemble(text) == program.link().words


def test_cycles_sum_instruction_costs():
    assert Program([LDI(r0, 1), WAIT(9), Label(), NOP()]).cycles() == 12


@pytest.mark.parametrize(
    "path", sorted((ROOT / "firmware").glob("*.asm")), ids=lambda p: p.name
)
def test_firmware_round_trips_through_listing_and_disassembly(path):
    program = parse(path.read_text())
    image = program.link()
    assert assemble(program.to_asm()) == image.words
    assert assemble(image.disassemble()) == image.words


def test_wide_listing_round_trip():
    source = (ROOT / "study/protocol_exploration/usb_out_candidate.asm").read_text()
    image = assemble_image(source, CARRY_FRONTIER)
    assert (
        assemble(parse(source, CARRY_FRONTIER).to_asm(), CARRY_FRONTIER) == image.words
    )
    assert assemble(image.disassemble(), CARRY_FRONTIER) == image.words


def test_text_errors_keep_line_numbers():
    with pytest.raises(AssemblyError, match="line 2: expected register r0..r3: r4"):
        assemble("NOP\nLDI r4, 0")
    with pytest.raises(AssemblyError, match="line 1: JMP expects 1 operand"):
        assemble("JMP")
    with pytest.raises(AssemblyError, match="line 1: unknown instruction SHRC"):
        assemble("SHRC r0")
    with pytest.raises(AssemblyError, match="line 1: register names cannot be labels"):
        assemble("r1: NOP")
    with pytest.raises(
        AssemblyError, match="line 2: address must be in the range 0..127: 128"
    ):
        assemble("NOP\nJMP end\n" + "NOP\n" * 126 + "end:")
