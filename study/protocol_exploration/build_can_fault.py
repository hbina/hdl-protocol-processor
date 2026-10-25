#!/usr/bin/env python3
"""Persistent CAN counter/passive/bus-off experiment in generic firmware."""

from pathlib import Path

from build_can_resync import generate as resync_source
from fragments import Fragment, load, put
from tools.isa import PinOp, RegPin
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
    PREAD,
    PWRITE,
    RET,
    SETO,
    SETOE,
    STORE,
    WAIT,
    XORI,
    r0,
    r1,
    r2,
    r3,
    r4,
    r5,
    r6,
    r7,
)


def generate():
    source = resync_source()

    def replace(old, new):
        nonlocal source
        assert source.count(old) == 1, old
        source = source.replace(old, new)

    # Three bytes persist across requests; the operation lives in a register.
    boot = Fragment().add(put(250, 0)).add(put(251, 0)).add(put(255, 0))
    replace(
        [SETO(1), SETOE(1), Label("idle")],
        (boot.program) + [SETO(1), SETOE(1), Label("idle")],
    )
    replace([PREAD(r0, r3), LDI(r1, 250), STORE(r0, r1)], [PREAD(r0, r3), MOV(r6, r0)])
    replace([LDI(r1, 250), LOAD(r0, r1), LDI(r4, 0)], [MOV(r0, r6), LDI(r4, 0)])
    replace(
        [LDI(r6, 0), CMPI(r0, 3)],
        [
            LDI(r6, 0),
            CMPI(r0, 6),
            JFAIL(Label("not_counter_query")),
            JMP(Label("counter_query")),
            Label("not_counter_query"),
            CMPI(r0, 5),
            JFAIL(Label("not_bus_recovery")),
            JMP(Label("bus_recovery")),
            Label("not_bus_recovery"),
            MOV(r7, r0),
            LDI(r1, 255),
            LOAD(r0, r1),
            JZ(r0, Label("node_available")),
            JMP(Label("bus_off_reject")),
            Label("node_available"),
            MOV(r0, r7),
            CMPI(r0, 3),
        ],
    )
    replace(
        [
            Label("ordinary_dispatch"),
            CMPI(r0, 2),
            JFAIL(Label("rx_entry")),
            JMP(Label("tx_entry")),
        ],
        [
            Label("ordinary_dispatch"),
            CMPI(r0, 2),
            JFAIL(Label("rx_entry")),
            LDI(r6, 5),
            JMP(Label("tx_entry")),
        ],
    )

    # Single-level generic leaves compact otherwise repeated software work.
    emit = [
        LDI(r3, 0x30),
        PWRITE(r0, r3),
        LDI(r0, 0),
        ADDI(r3, 1),
        PWRITE(r0, r3),
        ADDI(r3, 1),
        PWRITE(r0, r3),
    ]
    transfer = emit[1:]  # everything after LDI r3, 0x30
    assert source.count(transfer) == 4
    source = source.replace(transfer, [CALL(Label("emit_byte"))])
    source = source.replace(
        [LDI(r3, 0x30), CALL(Label("emit_byte"))], [CALL(Label("emit_byte"))]
    )
    leaves = Fragment([Label("emit_byte")] + emit + [RET()])
    increment = load(251).add([ADDI(r0, 8), STORE(r0, r1), CMPLTI(r0, 8)])
    increment.add(Fragment.choose(JFAIL, (), put(255, 1).add([SETOE(0)])))
    inc_call = Fragment([CALL(Label("increment_tec"))], cycles=1 + increment.cycles + 1)
    leaves.add([Label("increment_tec")]).add(increment).add([RET()])

    # Equalize every TX mismatch path to18 clocks at tx_fault entry.
    begin = source.index([Label("tx_mismatch")])
    end = source.index([Label("tx_tx_tail")], begin)
    source = (
        source[:begin]
        + [
            Label("tx_mismatch"),
            SETO(1),
            JZ(r0, Label("dominant_bit_error")),
            LDI(r1, 244),
            LOAD(r0, r1),
            JZ(r0, Label("tx_arbitration_check")),
            WAIT(3),
            JMP(Label("tx_bit_error")),
            Label("dominant_bit_error"),
            WAIT(7),
            JMP(Label("tx_bit_error")),
            Label("tx_arbitration_check"),
            LDI(r1, 247),
            LOAD(r0, r1),
            CMPLTI(r0, 157),
            JFAIL(Label("tx_bit_error")),
            CMPI(r6, 2),
            JFAIL(Label("legacy_arbitration_loss")),
            JMP(Label("winner_loss")),
            Label("legacy_arbitration_loss"),
            LDI(r2, 22),
            JMP(Label("failure")),
            Label("tx_bit_error"),
            LDI(r2, 21),
            JMP(Label("tx_fault")),
        ]
        + source[end:]
    )
    begin = source.index([Label("ack_error")])
    end = source.index([Label("error_delimiter_sample")], begin)
    flag = Fragment(
        [
            Label("ack_error"),
            LDI(r2, 24),
            WAIT(11),
            JMP(Label("tx_fault")),
            Label("tx_fault"),
            LDI(r1, 131),
            STORE(r2, r1),
            LDI(r1, 251),
            LOAD(r0, r1),
            ANDI(r0, 128),
            MOV(r7, r0),
            LDI(r1, 250),
            LOAD(r0, r1),
            ANDI(r0, 128),
            OR(r7, r0),
            LDI(r4, 0),
            JZ(r7, Label("active_flag_start")),
        ]
    )
    # Entry18 +status3 +passive10 +observed reset1 +branch1 =33.
    flag.add(Fragment.delay(67)).add(
        [SETO(1), JMP(Label("flag_started")), Label("active_flag_start")]
    )
    flag.add(Fragment.delay(67)).add(
        [SETO(0), JMP(Label("flag_started")), Label("flag_started"), LDI(r3, 6)]
    )
    flag.add(Fragment.delay(297)).add(
        [
            Label("flag_sample"),
            INBIT(r0, 1),
            ANDI(r0, 1),
            XORI(r0, 1),
            OR(r4, r0),
            DJNZ(r3, Label("flag_more")),
        ]
    )
    flag.add(Fragment.delay(95)).add(
        [SETO(1), JMP(Label("flag_finished")), Label("flag_more")]
    )
    flag.add(Fragment.delay(394)).add(
        [JMP(Label("flag_sample")), Label("flag_finished")]
    )
    # Release+JMP =2 clocks after flag end. Decide counter exceptions off wire.
    ack_increment = Fragment.choose(
        lambda t: JZ(r7, t),
        inc_call,
        Fragment.choose(lambda t: JZ(r4, t), (), inc_call),
    )
    stuff_increment = load(244).add(
        Fragment.choose(
            lambda t: JZ(r0, t),
            inc_call,
            load(246).add(
                Fragment.choose(
                    lambda t: JZ(r0, t),
                    inc_call,
                    load(247)
                    .add([CMPLTI(r0, 157)])
                    .add(Fragment.choose(JFAIL, inc_call)),
                )
            ),
        )
    )
    counter = Fragment([CMPI(r2, 21)]).add(
        Fragment.choose(JFAIL, ack_increment, stuff_increment)
    )
    flag.add(counter).add([LDI(r2, 8), LDI(r3, 32)])
    flag.add(Fragment.delay(300 - 2 - counter.cycles - 2 - 1)).add(
        [JMP(Label("error_delimiter_sample"))]
    )
    source = source[:begin] + flag.program + source[end:]

    # Complete intermission, then retire/retry under the persistent fault state.
    begin = source.index(
        [CMPLTI(r5, 3), JFAIL(Label("retry_exhausted"))],
        source.index([Label("error_delimited")]),
    )
    end = source.index([Label("recovery_timeout")], begin)
    retry = Fragment(
        [
            WAIT(96),
            LDI(r1, 255),
            LOAD(r0, r1),
            JZ(r0, Label("not_bus_off")),
            LDI(r2, 26),
            JMP(Label("failure")),
            Label("not_bus_off"),
            CMPI(r6, 5),
            JFAIL(Label("may_retry")),
            JMP(Label("publish")),
            Label("may_retry"),
            CMPLTI(r5, 3),
            JFAIL(Label("publish")),
            LDI(r1, 251),
            LOAD(r0, r1),
            ANDI(r0, 128),
            LDI(r1, 250),
            LOAD(r1, r1),
            ANDI(r1, 128),
            OR(r0, r1),
            JZ(r0, Label("retry_ready")),
            LDI(r3, 8),
            Label("passive_retry_suspend"),
            WAIT(255),
            WAIT(142),
            DJNZ(r3, Label("passive_retry_suspend")),
            Label("retry_ready"),
        ]
    )
    for address, value in [(242, 1), (243, 0), (245, 0), (247, 144)]:
        retry.add(put(address, value))
    retry.add([LDI(r4, 0), LDI(r7, 0), ADDI(r5, 1), JMP(Label("tx_tx_cell"))])
    source = source[:begin] + retry.program + source[end:]
    # Success updates counters once, independent of the number of retries.
    # Guard the unique tail label, which must start with its line sample.
    assert source.count([Label("tx_tail")]) == 1
    tail = source[source.index([Label("tx_tail")]) + 1]
    assert isinstance(tail, RegPin) and tail.op is PinOp.INBIT
    replace(
        [DJNZ(r2, Label("tx_tail")), JMP(Label("publish"))],
        [DJNZ(r2, Label("tx_tail")), JMP(Label("tx_success"))],
    )
    replace(
        [Label("rx_output_done")],
        [
            Label("rx_output_done"),
            LDI(r1, 250),
            LOAD(r0, r1),
            CMPLTI(r0, 128),
            JFAIL(Label("receive_counter_passive")),
            JZ(r0, Label("receive_counter_done")),
            ADDI(r0, 255),
            JMP(Label("receive_counter_store")),
            Label("receive_counter_passive"),
            LDI(r0, 127),
            Label("receive_counter_store"),
            STORE(r0, r1),
            Label("receive_counter_done"),
        ],
    )
    replace(
        [Label("failure"), SETO(1), LDI(r1, 131), STORE(r2, r1), Label("publish")],
        [
            Label("failure"),
            SETO(1),
            LDI(r1, 131),
            STORE(r2, r1),
            JZ(r6, Label("receiver_failure")),
            CMPI(r6, 3),
            JFAIL(Label("publish")),
            Label("receiver_failure"),
            CMPLTI(r2, 16),
            JFAIL(Label("receiver_error_range")),
            JMP(Label("publish")),
            Label("receiver_error_range"),
            CMPLTI(r2, 21),
            JFAIL(Label("publish")),
            CMPI(r2, 18),
            JFAIL(Label("increment_rec")),
            JMP(Label("publish")),
            Label("increment_rec"),
            LDI(r1, 250),
            LOAD(r0, r1),
            CMPI(r0, 255),
            JFAIL(Label("rec_not_saturated")),
            JMP(Label("publish")),
            Label("rec_not_saturated"),
            ADDI(r0, 1),
            STORE(r0, r1),
            Label("publish"),
        ],
    )

    extra = Fragment(
        [
            Label("tx_success"),
            LDI(r1, 251),
            LOAD(r0, r1),
            JZ(r0, Label("tx_counter_done")),
            ADDI(r0, 255),
            STORE(r0, r1),
            Label("tx_counter_done"),
        ]
    ).add(put(131, 0))
    extra.add(
        [
            LDI(r1, 251),
            LOAD(r0, r1),
            ANDI(r0, 128),
            LDI(r1, 250),
            LOAD(r1, r1),
            ANDI(r1, 128),
            OR(r0, r1),
            JZ(r0, Label("publish")),
            LDI(r3, 8),
            Label("passive_success_suspend"),
            WAIT(255),
            WAIT(142),
            DJNZ(r3, Label("passive_success_suspend")),
            JMP(Label("publish")),
            Label("counter_query"),
        ]
    )
    for address in [251, 255, 250]:
        extra.add(load(address)).add([CALL(Label("emit_byte"))])
    extra.add(put(134, 3)).add(
        [
            JMP(Label("publish")),
            Label("bus_off_reject"),
            LDI(r3, 0x11),
            Label("drain_rejected_input"),
            PREAD(r0, r3),
            JFAIL(Label("rejected_drained")),
            JMP(Label("drain_rejected_input")),
            Label("rejected_drained"),
            LDI(r2, 26),
            JMP(Label("failure")),
        ]
    )
    extra.add(
        [
            Label("bus_recovery"),
            LDI(r1, 255),
            LOAD(r0, r1),
            JZ(r0, Label("publish")),
            LDI(r2, 128),
            LDI(r3, 11),
            LDI(r4, 0),
            LDI(r7, 16),
            Label("bus_recovery_sample"),
            INBIT(r0, 1),
            ANDI(r0, 1),
            JZ(r0, Label("bus_recovery_dominant")),
            DJNZ(r3, Label("bus_recovery_not_group")),
            LDI(r3, 11),
            DJNZ(r2, Label("bus_recovery_budget")),
            JMP(Label("bus_recovered")),
            Label("bus_recovery_not_group"),
            NOP(),
            JMP(Label("bus_recovery_budget")),
            Label("bus_recovery_dominant"),
            LDI(r3, 11),
            NOP(),
            NOP(),
            Label("bus_recovery_budget"),
            DJNZ(r4, Label("bus_recovery_fast")),
            DJNZ(r7, Label("bus_recovery_budget_ready")),
            LDI(r2, 6),
            JMP(Label("failure")),
            Label("bus_recovery_fast"),
            NOP(),
            Label("bus_recovery_budget_ready"),
        ]
    )
    extra.add(Fragment.delay(391)).add(
        [JMP(Label("bus_recovery_sample")), Label("bus_recovered")]
    )
    extra.add(Fragment.delay(400)).add(put(250, 0)).add(put(251, 0)).add(put(255, 0))
    extra.add([SETOE(1), JMP(Label("publish"))])
    return (source + (extra.program + leaves.program)).replace_comment_text(
        "GENERATED by build_can_resync.py.",
        "GENERATED by build_can_fault.py. Persistent counters; generic leaf calls.",
    )


if __name__ == "__main__":
    Path(__file__).with_name("can_fault_candidate.asm").write_text(generate().to_asm())
