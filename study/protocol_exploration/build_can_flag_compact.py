#!/usr/bin/env python3
"""Compact the retained active-flag fault draft using generic software reuse."""

from pathlib import Path

from build_can_flag_bit import generate as draft_source
from tools.isa import INBIT
from tools.program import Program
from tools.isa import (
    ANDI,
    CALL,
    CMPI,
    CMPLTI,
    DJNZ,
    JFAIL,
    JMP,
    JZ,
    LDI,
    LOAD,
    Label,
    MOV,
    ORI,
    RET,
    ROR,
    SHL,
    STORE,
    WAIT,
    XORI,
    r0,
    r1,
    r2,
    r3,
    r4,
    r6,
    r7,
)


def generate():
    source = draft_source()

    def replace(old, new, count=1):
        nonlocal source
        assert source.count(old) == count, (old, source.count(old))
        source = source.replace(old, new)

    clear = [
        LDI(r1, 250),
        LDI(r0, 0),
        STORE(r0, r1),
        LDI(r1, 251),
        LDI(r0, 0),
        STORE(r0, r1),
        LDI(r1, 255),
        LDI(r0, 0),
        STORE(r0, r1),
    ]
    replace(clear, [CALL(Label("clear_counters"))], 2)
    source += (
        [Label("clear_counters")]
        + Program(clear)
        .replace([LDI(r1, 251), LDI(r0, 0)], [LDI(r1, 251)])
        .replace([LDI(r1, 255), LDI(r0, 0)], [LDI(r1, 255)])
        + [RET()]
    )
    common = Program(
        [
            LDI(r1, 242),
            LDI(r0, 1),
            STORE(r0, r1),
            LDI(r1, 243),
            LDI(r0, 0),
            STORE(r0, r1),
            LDI(r1, 245),
            LDI(r0, 0),
            STORE(r0, r1),
            LDI(r1, 247),
            LDI(r0, 144),
            STORE(r0, r1),
        ]
    )
    # Initial receive setup is off-wire, so move its header count after the
    # common stores to expose the same leaf as initial TX and retransmission.
    replace(
        [
            LDI(r1, 243),
            LDI(r0, 0),
            STORE(r0, r1),
            LDI(r1, 244),
            LDI(r0, 19),
            STORE(r0, r1),
            LDI(r1, 245),
        ],
        [LDI(r1, 243), LDI(r0, 0), STORE(r0, r1), LDI(r1, 245)],
    )
    replace(
        [Label("rx_entry")] + common,
        [Label("rx_entry")] + common + [LDI(r1, 244), LDI(r0, 19), STORE(r0, r1)],
    )
    replace(common, [CALL(Label("reset_frame_state"))], 3)
    source += (
        [Label("reset_frame_state")]
        + common.replace([LDI(r1, 245), LDI(r0, 0)], [LDI(r1, 245)])
        + [RET()]
    )
    replace([SHL(r0)] * 5 + [LDI(r2, 3)], [ROR(r0)] * 3 + [LDI(r2, 3)])
    # Offline CRC construction has no on-wire deadline; discard branch padding.
    replace(
        [
            XORI(r3, 0x45),
            JMP(Label("tx_balance_101_end")),
            Label("tx_balance_101_yes"),
            WAIT(2),
            Label("tx_balance_101_end"),
        ],
        [XORI(r3, 0x45), Label("tx_balance_101_yes"), Label("tx_balance_101_end")],
    )
    # Two calculations are dead before the same scratch value is overwritten.
    replace(
        [LDI(r3, 6), MOV(r0, r7), ANDI(r0, 128), LDI(r1, 1)], [LDI(r3, 6), LDI(r1, 1)]
    )
    replace(
        [WAIT(45), JZ(r0, Label("flagbit_restart_active"))],
        [WAIT(47), JZ(r0, Label("flagbit_restart_active"))],
    )
    replace(
        [
            LDI(r7, 8),
            Label("postflag_receiver_add"),
            CALL(Label("increment_rec_leaf")),
            DJNZ(r7, Label("postflag_receiver_add")),
        ],
        [CALL(Label("increment_rec_eight")), WAIT(77)],
    )
    begin = source.index([CMPI(r6, 6)], source.index([Label("flag_started")]))
    end = source.index([ORI(r7, 64)], begin)
    source = Program(
        source[:begin]
        + [
            CMPI(r6, 6),
            JFAIL(Label("flagbit_initial_transmit")),
            CALL(Label("increment_rec_leaf")),
            WAIT(22),
            JMP(Label("flagbit_initial_done")),
            Label("flagbit_initial_transmit"),
            CMPI(r2, 21),
            JFAIL(Label("flagbit_initial_ack")),
            LDI(r1, 244),
            LOAD(r0, r1),
            JZ(r0, Label("flagbit_initial_early")),
            LDI(r1, 246),
            LOAD(r0, r1),
            JZ(r0, Label("flagbit_initial_middle")),
            LDI(r1, 247),
            LOAD(r0, r1),
            CMPLTI(r0, 157),
            JFAIL(Label("flagbit_initial_late")),
            WAIT(17),
            JMP(Label("flagbit_initial_done")),
            Label("flagbit_initial_early"),
            WAIT(3),
            Label("flagbit_initial_middle"),
            WAIT(4),
            Label("flagbit_initial_late"),
            WAIT(1),
            Label("flagbit_initial_charge"),
            CALL(Label("increment_tec")),
            JMP(Label("flagbit_initial_done")),
            Label("flagbit_initial_ack"),
            JZ(r7, Label("flagbit_initial_ack_active")),
            LDI(r4, 2),
            WAIT(28),
            JMP(Label("flagbit_initial_done")),
            Label("flagbit_initial_ack_active"),
            WAIT(12),
            JMP(Label("flagbit_initial_charge")),
            Label("flagbit_initial_done"),
        ]
        + source[end:]
    )

    # Both initial roles qualify the same11-bit idle interval before their
    # role-specific next action. The new leaf adds only call/return clocks
    # outside a frame; all sampling loops retain their original400 clocks.
    def idle(role):
        loop, busy_bus = Label(f"{role}_idle_bus"), Label(f"{role}_busy_bus")
        return [LDI(r2, 11), LDI(r3, 0), loop, INBIT(r0, 1), ANDI(r0, 1)] + [
            JZ(r0, busy_bus),
            WAIT(255),
            WAIT(139),
            DJNZ(r2, loop),
        ]

    def busy(role):
        loop, busy_bus = Label(f"{role}_idle_bus"), Label(f"{role}_busy_bus")
        return [
            busy_bus,
            LDI(r2, 11),
            DJNZ(r3, loop),
            LDI(r2, 6),
            JMP(Label("failure")),
        ]

    for role in ["rx", "tx"]:
        replace(idle(role), [CALL(Label("qualify_idle"))])
        replace(busy(role), [])
    source += [Label("qualify_idle")] + idle("shared") + [RET()] + busy("shared")
    return source.replace_comment_text(
        "GENERATED by build_can_flag_bit.py. UNVERIFIED first integration; actual assembly capacity must be checked.",
        "GENERATED by build_can_flag_compact.py. Active flag-bit counter/restart experiment; generic software compaction.",
    )


if __name__ == "__main__":
    Path(__file__).with_name("can_flag_compact_candidate.asm").write_text(
        generate().to_asm()
    )
