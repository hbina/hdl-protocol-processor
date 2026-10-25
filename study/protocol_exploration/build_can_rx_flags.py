#!/usr/bin/env python3
"""RX CRC/stuff/form error signaling sharing generic firmware flag machinery."""

from pathlib import Path

from build_can_fault_equal import generate as fault_source
from fragments import Fragment
from tools.isa import (
    ADDI,
    ANDI,
    CALL,
    CMPI,
    CMPLTI,
    INBIT,
    JFAIL,
    JMP,
    JZ,
    LDI,
    LOAD,
    Label,
    MOV,
    NOP,
    RET,
    SETO,
    STORE,
    WAIT,
    r0,
    r1,
    r2,
    r3,
    r4,
    r6,
    r7,
)
from tools.program import Comment


def generate():
    source = fault_source()

    def replace(old, new):
        nonlocal source
        assert source.count(old) == 1, old
        source = source.replace(old, new)

    # Defer CRC status16 while consuming the possible final stuff bit. Other
    # bit-stream faults still take the immediate next-bit signaling path.
    ignore_crc = Fragment([CMPI(r0, 16)]).add(Fragment.choose(JFAIL, (), [LDI(r0, 0)]))
    replace(
        [
            LDI(r1, 248),
            LOAD(r0, r1),
            JZ(r0, Label("rx_sample_ok")),
            MOV(r2, r0),
            JMP(Label("failure")),
        ],
        [LDI(r1, 248), LOAD(r0, r1)]
        + (ignore_crc.program)
        + [JZ(r0, Label("rx_sample_ok")), MOV(r2, r0), JMP(Label("rx_error_dispatch"))],
    )
    # The normal RX path gains4 clocks, preserving the sample window's end.
    replace([LDI(r7, 27), Label("rx_edge_poll")], [LDI(r7, 26), Label("rx_edge_poll")])
    replace(
        [Label("rx_no_edge_window"), WAIT(251)], [Label("rx_no_edge_window"), WAIT(247)]
    )

    replace(
        [
            Label("rx_delimiter"),
            Comment(
                "r0 is CRC rx_delimiter. Data and CRC already checked, final stuff consumed."
            ),
            CMPI(r0, 1),
            JFAIL(Label("rx_form_error")),
            Comment("50% sample: ACK starts200 clocks after CRC-delimiter sample."),
            WAIT(181),
        ],
        [
            Label("rx_delimiter"),
            CMPI(r0, 1),
            JFAIL(Label("rx_delimiter_form_error")),
            LDI(r1, 248),
            LOAD(r0, r1),
            JZ(r0, Label("rx_valid_crc")),
            LDI(r2, 16),
            WAIT(255),
            WAIT(255),
            WAIT(255),
            WAIT(8),
            Comment(
                "ACK delimiter sample,800 clocks after CRC delimiter. Do not ACK bad CRC."
            ),
            INBIT(r0, 1),
            ANDI(r0, 1),
            WAIT(147),
            JMP(Label("rx_fault_prepare")),
            Label("rx_valid_crc"),
            WAIT(177),
        ],
    )
    replace(
        [LDI(r2, 20), JMP(Label("failure"))],
        [LDI(r2, 20), WAIT(145), JMP(Label("rx_fault_prepare"))],
    )
    replace(
        [Label("rx_form_error"), LDI(r2, 17), JMP(Label("failure"))],
        [
            Label("rx_form_error"),
            Comment("r2=11 at ACK delimiter,10..4 at EOF,3..1 at intermission."),
            Comment(
                "Preserve the older local-only limitation for last EOF/intermission traffic."
            ),
            CMPLTI(r2, 5),
            JFAIL(Label("rx_tail_form_error")),
            LDI(r2, 17),
            JMP(Label("failure")),
            Label("rx_tail_form_error"),
            LDI(r2, 17),
            WAIT(143),
            JMP(Label("rx_fault_prepare")),
            Label("rx_delimiter_form_error"),
            LDI(r2, 17),
            WAIT(130),
            JMP(Label("rx_fault_prepare")),
        ],
    )

    # TX reaches the flag drive at its next boundary exactly as before. RX
    # enters after151 clocks of its50% sample and uses its own remaining wait.
    replace(
        [
            JZ(r7, Label("active_flag_start")),
            WAIT(64),
            SETO(1),
            JMP(Label("flag_started")),
            Label("active_flag_start"),
            WAIT(64),
            SETO(0),
            JMP(Label("flag_started")),
        ],
        [
            WAIT(63),
            JMP(Label("flag_drive")),
            Label("flag_drive"),
            JZ(r7, Label("active_flag_start")),
            SETO(1),
            JMP(Label("flag_started")),
            Label("active_flag_start"),
            SETO(0),
            NOP(),
        ],
    )
    extra = Fragment(
        [
            Label("rx_error_dispatch"),
            CMPI(r2, 18),
            JFAIL(Label("rx_fault_prepare")),
            JMP(Label("failure")),
            Label("rx_fault_prepare"),
            LDI(r6, 6),
            LDI(r1, 131),
            STORE(r2, r1),
            CALL(Label("passive_state")),
            MOV(r7, r0),
            LDI(r4, 0),
            WAIT(29),
            JMP(Label("flag_drive")),
        ]
    )
    # Make the existing REC increment a reusable non-nesting generic leaf.
    begin = source.index([Label("increment_rec")])
    end = source.index([Label("publish")], begin)
    old_rec = source[begin:end]
    assert [STORE(r0, r1)] in old_rec
    source = (
        source[:begin]
        + [
            Label("increment_rec"),
            CALL(Label("increment_rec_leaf")),
            JMP(Label("publish")),
        ]
        + source[end:]
    )
    rec = Fragment([LDI(r1, 250), LOAD(r0, r1), CMPI(r0, 255)])
    rec.add(Fragment.choose(JFAIL, [ADDI(r0, 1), STORE(r0, r1)]))
    extra.add([Label("increment_rec_leaf")]).add(rec).add([RET()])
    # The TX counter body is cycle-balanced at34 clocks. Select REC instead
    # for receive-error mode, retaining the first-delimiter sample's phase.
    begin = source.index([CMPI(r2, 21)], source.index([Label("flag_finished")]))
    end = source.index([LDI(r2, 8), LDI(r3, 32)], begin)
    tx_counter = Fragment(source[begin:end], cycles=34)
    counter = Fragment([CMPI(r6, 6)]).add(
        Fragment.choose(
            JFAIL,
            tx_counter,
            Fragment([CALL(Label("increment_rec_leaf"))], cycles=1 + rec.cycles + 1),
        )
    )
    assert counter.cycles == 36
    source = source[:begin] + counter.program + source[end:]
    replace(
        [
            LDI(r2, 8),
            LDI(r3, 32),
            WAIT(255),
            WAIT(3),
            JMP(Label("error_delimiter_sample")),
        ],
        [
            LDI(r2, 8),
            LDI(r3, 32),
            WAIT(255),
            WAIT(1),
            JMP(Label("error_delimiter_sample")),
        ],
    )
    replace(
        [WAIT(96), LDI(r1, 255), LOAD(r0, r1), JZ(r0, Label("not_bus_off"))],
        [
            WAIT(96),
            CMPI(r6, 6),
            JFAIL(Label("error_was_transmit")),
            JMP(Label("publish")),
            Label("error_was_transmit"),
            LDI(r1, 255),
            LOAD(r0, r1),
            JZ(r0, Label("not_bus_off")),
        ],
    )
    return (source + extra.program).replace_comment_text(
        "GENERATED by build_can_fault_equal.py.",
        "GENERATED by build_can_rx_flags.py. RX error flags; capacity-only until assembled.",
    )


if __name__ == "__main__":
    Path(__file__).with_name("can_rx_flags_candidate.asm").write_text(
        generate().to_asm()
    )
