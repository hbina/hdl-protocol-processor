#!/usr/bin/env python3
"""Further generic firmware reuse for the frozen bounded CAN tail draft."""

from pathlib import Path

from build_can_tail import generate as prior_source
from tools.program import concat
from tools.program import Program
from tools.isa import (
    ADDI,
    ANDI,
    CALL,
    CMPI,
    DJNZ,
    INBIT,
    JFAIL,
    JMP,
    JZ,
    LDI,
    LOAD,
    Label,
    MOV,
    NOP,
    OR,
    RET,
    ROL,
    ROR,
    SHL,
    STORE,
    WAIT,
    XOR,
    XORI,
    r0,
    r1,
    r2,
    r3,
    r4,
    r7,
)


def generate(*, safe_idle=True):
    source = prior_source()

    def replace(old, new, count=1):
        nonlocal source
        assert source.count(old) == count, (old, source.count(old))
        source = source.replace(old, new)

    feedback = Program(
        [
            MOV(r0, r3),
            ANDI(r0, 64),
            LDI(r1, 246),
            LOAD(r1, r1),
            ROR(r1),
            ROR(r1),
            XOR(r0, r1),
        ]
    )
    shift = [
        SHL(r3),
        ANDI(r3, 127),
        ROL(r2),
        MOV(r1, r2),
        ANDI(r1, 1),
        OR(r3, r1),
        ANDI(r2, 254),
    ]
    rx = (
        feedback
        + [WAIT(3)]
        + shift
        + [
            JZ(r0, Label("rx_balance_3_yes")),
            XORI(r2, 0x99),
            XORI(r3, 0x45),
            JMP(Label("rx_balance_3_end")),
            Label("rx_balance_3_yes"),
            WAIT(2),
            Label("rx_balance_3_end"),
        ]
    )
    replace(rx, [CALL(Label("crc_step")), WAIT(1)])
    offline = (
        feedback.replace([LDI(r1, 246)], [])
        + shift
        + [
            JZ(r0, Label("tx_balance_101_yes")),
            XORI(r2, 0x99),
            XORI(r3, 0x45),
            Label("tx_balance_101_yes"),
            Label("tx_balance_101_end"),
        ]
    )
    replace(offline, [CALL(Label("crc_step"))])
    begin = source.index([MOV(r1, r7), ANDI(r1, 64)])
    end = source.index([Label("balance_107_end")], begin)
    source = Program(
        source[:begin]
        + [
            MOV(r2, r4),
            MOV(r3, r7),
            CALL(Label("crc_step")),
            MOV(r4, r2),
            MOV(r7, r3),
            LDI(r1, 246),
            LOAD(r0, r1),
        ]
        + source[end:]
    )
    replace(
        [WAIT(19), JMP(Label("balance_107_end"))],
        [WAIT(26), JMP(Label("balance_107_end"))],
    )
    replace(
        [Label("balance_107_end"), WAIT(255), WAIT(13)],
        [Label("balance_107_end"), WAIT(255), WAIT(6)],
    )
    source += (
        [Label("crc_step")]
        + feedback
        + shift
        + [
            JZ(r0, Label("crc_zero_feedback")),
            XORI(r2, 0x99),
            XORI(r3, 0x45),
            JMP(Label("crc_step_done")),
            Label("crc_zero_feedback"),
            WAIT(2),
            Label("crc_step_done"),
            RET(),
        ]
    )
    # Output encoding and offline staging do not have pin deadlines.
    replace(
        [MOV(r2, r0), CALL(Label("emit_byte")), MOV(r4, r2)],
        [MOV(r4, r0), CALL(Label("emit_byte"))],
    )
    replace(
        [MOV(r0, r2), LDI(r2, 254), STORE(r0, r2), MOV(r0, r3)],
        [LDI(r0, 254), STORE(r2, r0), MOV(r0, r3)],
    )
    old = [LDI(r0, 0)] + concat(
        [LDI(r1, address), LOAD(r1, r1), SHL(r0), OR(r0, r1)]
        for address in range(159, 163)
    )
    new = [LDI(r1, 159), LOAD(r0, r1)] + [
        SHL(r0),
        ADDI(r1, 1),
        LOAD(r4, r1),
        OR(r0, r4),
    ] * 3
    replace(old, new)
    replace(
        [JFAIL(Label("postflag_bad_dlc")), WAIT(3)],
        [JFAIL(Label("postflag_bad_dlc")), WAIT(6)],
    )
    # Shared saturating store tails preserve both existing leaf cycle counts.
    replace(
        [
            Label("increment_rec_leaf"),
            LDI(r1, 250),
            LOAD(r0, r1),
            CMPI(r0, 255),
            JFAIL(Label("balance_116_yes")),
            WAIT(1),
            JMP(Label("balance_116_end")),
            Label("balance_116_yes"),
            ADDI(r0, 1),
            STORE(r0, r1),
            Label("balance_116_end"),
            RET(),
        ],
        [
            Label("increment_rec_leaf"),
            LDI(r1, 250),
            LOAD(r0, r1),
            CMPI(r0, 255),
            JFAIL(Label("balance_116_yes")),
            JMP(Label("rec_store")),
            Label("balance_116_yes"),
            ADDI(r0, 1),
            Label("rec_store"),
            STORE(r0, r1),
            RET(),
        ],
    )
    replace([JMP(Label("flagbit_rec_store"))], [JMP(Label("rec_store"))])
    replace(
        [
            Label("flagbit_rec_saturates"),
            LDI(r0, 255),
            NOP(),
            Label("flagbit_rec_store"),
            STORE(r0, r1),
            RET(),
        ],
        [Label("flagbit_rec_saturates"), LDI(r0, 255), JMP(Label("rec_store"))],
    )
    # Reorder the leaf feedback so offline TX can pass its already-loaded bit.
    replace(
        [Label("crc_step")] + feedback,
        [
            Label("crc_step"),
            LDI(r1, 246),
            LOAD(r1, r1),
            Label("crc_from_r1"),
            ROR(r1),
            ROR(r1),
            MOV(r0, r3),
            ANDI(r0, 64),
            XOR(r0, r1),
        ],
    )
    replace(
        [LOAD(r0, r1), LDI(r1, 246), STORE(r0, r1), CALL(Label("crc_step"))],
        [LOAD(r0, r1), MOV(r1, r0), CALL(Label("crc_from_r1"))],
    )
    # Ignore the last EOF polarity without a dead input read. Overload uses
    # twelve generic delay segments; the public dominant pulse remains2400
    # clocks, and the existing lack of per-bit overload fault checks is kept.
    replace(
        [LDI(r7, 3), INBIT(r0, 1), WAIT(255), WAIT(140)],
        [LDI(r7, 3), WAIT(255), WAIT(141)],
    )
    replace(
        [Label("rx_overload_allowed"), LDI(r3, 6), WAIT(191)],
        [Label("rx_overload_allowed"), LDI(r3, 12), WAIT(192)],
    )
    replace(
        [
            Label("rx_overload_bit"),
            WAIT(255),
            WAIT(141),
            DJNZ(r3, Label("rx_overload_bit")),
            WAIT(4),
        ],
        [
            Label("rx_overload_bit"),
            WAIT(197),
            DJNZ(r3, Label("rx_overload_bit")),
            WAIT(10),
        ],
    )
    # INBIT replaces only bit0. These paths already keep r0 upper bits zero;
    # frame-state initialization below supplies that invariant for TX idle.
    # Compensate the timed paths using existing padding words.
    replace(
        [
            Label("shared_idle_bus"),
            INBIT(r0, 1),
            ANDI(r0, 1),
            JZ(r0, Label("shared_busy_bus")),
            WAIT(255),
            WAIT(139),
        ],
        [
            Label("shared_idle_bus"),
            INBIT(r0, 1),
            JZ(r0, Label("shared_busy_bus")),
            WAIT(255),
            WAIT(140),
        ],
    )
    replace(
        [Label("rx_sof_wait"), INBIT(r0, 1), ANDI(r0, 1)],
        [Label("rx_sof_wait"), INBIT(r0, 1)],
    )
    replace(
        [Label("rx_sof_seen"), LDI(r2, 0), LDI(r3, 0), WAIT(192)],
        [Label("rx_sof_seen"), LDI(r2, 0), LDI(r3, 0), WAIT(193)],
    )
    replace(
        [INBIT(r0, 1), ANDI(r0, 1), WAIT(147), JMP(Label("rx_fault_prepare"))],
        [INBIT(r0, 1), WAIT(148), JMP(Label("rx_fault_prepare"))],
    )
    replace(
        [INBIT(r0, 1), ANDI(r0, 1), JZ(r0, Label("rx_ack_ok")), LDI(r2, 20), WAIT(145)],
        [INBIT(r0, 1), JZ(r0, Label("rx_ack_ok")), LDI(r2, 20), WAIT(146)],
    )
    replace([Label("rx_ack_ok"), WAIT(196)], [Label("rx_ack_ok"), WAIT(197)])
    replace(
        [
            Label("rx_tail"),
            INBIT(r0, 1),
            ANDI(r0, 1),
            JZ(r0, Label("rx_form_error")),
            WAIT(255),
            WAIT(139),
        ],
        [
            Label("rx_tail"),
            INBIT(r0, 1),
            JZ(r0, Label("rx_form_error")),
            WAIT(255),
            WAIT(140),
        ],
    )
    replace(
        [Label("rx_form_error"), LDI(r2, 17), WAIT(145)],
        [Label("rx_form_error"), LDI(r2, 17), WAIT(146)],
    )
    replace(
        [
            Label("rx_intermission"),
            INBIT(r0, 1),
            ANDI(r0, 1),
            JZ(r0, Label("rx_intermission_dominant")),
            WAIT(255),
            WAIT(139),
        ],
        [
            Label("rx_intermission"),
            INBIT(r0, 1),
            JZ(r0, Label("rx_intermission_dominant")),
            WAIT(255),
            WAIT(140),
        ],
    )
    replace(
        [Label("rx_overload_delimiter"), INBIT(r0, 1), ANDI(r0, 1)],
        [Label("rx_overload_delimiter"), INBIT(r0, 1)],
    )
    replace(
        [LDI(r2, 3), WAIT(255), WAIT(137), JMP(Label("rx_intermission"))],
        [LDI(r2, 3), WAIT(255), WAIT(138), JMP(Label("rx_intermission"))],
    )
    replace(
        [Label("rx_overload_delay"), WAIT(255), WAIT(135)],
        [Label("rx_overload_delay"), WAIT(255), WAIT(136)],
    )
    if safe_idle:
        # The generic input-bit operation preserves bits7:1. Return r0=1
        # rather than144 from setup so dominant idle samples compare as zero.
        # All addresses/values and total instruction/cycle counts are unchanged.
        replace(
            [
                Label("reset_frame_state"),
                LDI(r1, 242),
                LDI(r0, 1),
                STORE(r0, r1),
                LDI(r1, 243),
                LDI(r0, 0),
                STORE(r0, r1),
                LDI(r1, 245),
                STORE(r0, r1),
                LDI(r1, 247),
                LDI(r0, 144),
                STORE(r0, r1),
                RET(),
            ],
            [
                Label("reset_frame_state"),
                LDI(r1, 247),
                LDI(r0, 144),
                STORE(r0, r1),
                LDI(r1, 243),
                LDI(r0, 0),
                STORE(r0, r1),
                LDI(r1, 245),
                STORE(r0, r1),
                LDI(r1, 242),
                LDI(r0, 1),
                STORE(r0, r1),
                RET(),
            ],
        )
    return source.replace_comment_text(
        "GENERATED by build_can_tail.py. UNVERIFIED capacity integration;",
        "GENERATED by build_can_tail_compact.py. Shared generic firmware routines;",
    )


if __name__ == "__main__":
    Path(__file__).with_name("can_tail_compact_candidate.asm").write_text(
        generate().to_asm()
    )
    Path(__file__).with_name("can_tail_compact_unsafe_candidate.asm").write_text(
        generate(safe_idle=False).to_asm()
    )
