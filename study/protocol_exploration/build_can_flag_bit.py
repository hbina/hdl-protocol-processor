#!/usr/bin/env python3
"""Draft active error-flag bit-error restart/accounting using the generic ISA.

This first integration intentionally preserves the full listing even if real
1024-word assembly rejects it. It is not behavior-verified until it assembles
and passes the independent fault peer and earlier protocol regressions.
"""

from pathlib import Path

from build_can_postflag import generate as prior_source
from tools.isa import (
    ADDI,
    ANDI,
    CALL,
    CMPI,
    CMPLTI,
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
    ORI,
    RET,
    SETO,
    STORE,
    WAIT,
    XOR,
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
    source = prior_source()

    def replace(old, new):
        nonlocal source
        assert source.count(old) == 1, old
        source = source.replace(old, new)

    begin = source.index([Label("flag_finished")])
    end = source.index([LDI(r4, 0), LDI(r2, 8)], begin)
    charge = source[begin:end].removeprefix([Label("flag_finished"), ANDI(r7, 128)])
    # Account for the original error before sampling the flag, so a later
    # flag-bit error sees the updated error-active/passive threshold state.
    # Passive ACK with no observed dominant bit is deferred until completion.
    charge = charge.replace(
        [Label("balance_109_yes"), WAIT(16)],
        [Label("balance_109_yes"), LDI(r4, 2), WAIT(15)],
    )
    source = (
        source[:begin]
        + [
            Label("flag_finished"),
            CMPI(r4, 3),
            JFAIL(Label("flagbit_no_deferred_ack")),
            CALL(Label("increment_tec")),
            JMP(Label("flagbit_deferred_done")),
            Label("flagbit_no_deferred_ack"),
            WAIT(16),
            Label("flagbit_deferred_done"),
        ]
        + source[end:]
    )
    replace(
        [Label("flag_started"), LDI(r3, 6), ORI(r7, 64), WAIT(255), WAIT(39)],
        [Label("flag_started"), LDI(r3, 6)]
        + charge
        + [ORI(r7, 64), LDI(r1, 1), WAIT(255), WAIT(2)],
    )
    replace(
        [Label("flag_sample"), INBIT(r0, 1), ANDI(r0, 1), XOR(r1, r0)],
        [
            Label("flag_sample"),
            INBIT(r0, 1),
            ANDI(r0, 1),
            CMPLTI(r7, 128),
            JFAIL(Label("flagbit_passive_sample")),
            JZ(r0, Label("flagbit_normal_sample")),
            JMP(Label("flagbit_error")),
            Label("flagbit_passive_sample"),
            NOP(),
            Label("flagbit_normal_sample"),
            XOR(r1, r0),
        ],
    )
    replace(
        [DJNZ(r3, Label("flag_more")), WAIT(85)],
        [DJNZ(r3, Label("flag_more")), WAIT(82)],
    )
    replace(
        [Label("flag_more"), WAIT(255), WAIT(128)],
        [Label("flag_more"), WAIT(255), WAIT(125)],
    )
    # The final counter block changed its cost; preserve the intended next
    # sample phase. These pads remain draft until a runnable image is tested.
    replace(
        [LDI(r3, 32), WAIT(255), NOP(), JMP(Label("error_delimiter_sample"))],
        [LDI(r3, 32), WAIT(255), WAIT(18), JMP(Label("error_delimiter_sample"))],
    )
    source += [
        Comment(
            "252 is dead transmit-packer scratch after an exchange abort. Save only the"
        ),
        Comment(
            "current flag sample budget; the leaf calls clobber r0/r1 and return_pc."
        ),
        Comment(
            "No nested calls and no added data memory or protocol-specific operation."
        ),
        Label("flagbit_error"),
        LDI(r1, 252),
        STORE(r7, r1),
        CALL(Label("passive_state")),
        CMPI(r6, 6),
        JFAIL(Label("flagbit_transmit_increment")),
        CALL(Label("increment_rec_eight")),
        WAIT(4),
        JMP(Label("flagbit_incremented")),
        Label("flagbit_transmit_increment"),
        CALL(Label("increment_tec")),
        NOP(),
        Label("flagbit_incremented"),
        LDI(r1, 252),
        LOAD(r1, r1),
        OR(r7, r1),
        LDI(r3, 6),
        MOV(r0, r7),
        ANDI(r0, 128),
        LDI(r1, 1),
        ADDI(r7, 255),
        MOV(r0, r7),
        ANDI(r0, 127),
        JZ(r0, Label("recovery_timeout")),
        MOV(r0, r7),
        ANDI(r0, 128),
        WAIT(45),
        JZ(r0, Label("flagbit_restart_active")),
        SETO(1),
        JMP(Label("flagbit_restarted")),
        Label("flagbit_restart_active"),
        SETO(0),
        NOP(),
        Label("flagbit_restarted"),
        WAIT(255),
        WAIT(40),
        JMP(Label("flag_sample")),
        Label("increment_rec_eight"),
        LDI(r1, 250),
        LOAD(r0, r1),
        CMPLTI(r0, 248),
        JFAIL(Label("flagbit_rec_saturates")),
        ADDI(r0, 8),
        JMP(Label("flagbit_rec_store")),
        Label("flagbit_rec_saturates"),
        LDI(r0, 255),
        NOP(),
        Label("flagbit_rec_store"),
        STORE(r0, r1),
        RET(),
    ]
    return source.replace_comment_text(
        "GENERATED by build_can_postflag.py.",
        "GENERATED by build_can_flag_bit.py. UNVERIFIED first integration; actual assembly capacity must be checked.",
    )


if __name__ == "__main__":
    Path(__file__).with_name("can_flag_bit_candidate.asm").write_text(
        generate().to_asm()
    )
