#!/usr/bin/env python3
"""CAN first-post-flag and prolonged-dominance counters in generic firmware."""

from pathlib import Path

from build_can_rx_flags_compact import generate as rx_flags_source
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
    ORI,
    RET,
    ROR,
    STORE,
    WAIT,
    XOR,
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


def generate(*, compact=True, cleanup=True):
    source = rx_flags_source()

    def replace(old, new):
        nonlocal source
        assert source.count(old) == 1, old
        source = source.replace(old, new)

    # All counted receiver errors already update REC in the shared sequencer.
    # Retained unsupported EOF/intermission diagnostics are local results, not
    # another increment path for a completed physical error flag.
    begin = source.index([JZ(r6, Label("receiver_failure"))])
    end = source.index([Label("publish")], begin)
    source = source[:begin] + source[end:]
    replace(
        [
            LDI(r2, 8),
            LDI(r3, 32),
            WAIT(255),
            WAIT(1),
            JMP(Label("error_delimiter_sample")),
        ],
        [
            LDI(r4, 0),
            LDI(r2, 8),
            LDI(r3, 32),
            WAIT(255),
            NOP(),
            JMP(Label("error_delimiter_sample")),
        ],
    )
    begin = source.index([Label("error_delimiter_sample")])
    end = source.index([Label("error_delimited")], begin)
    source = (
        source[:begin]
        + [
            Label("error_delimiter_sample"),
            INBIT(r0, 1),
            ANDI(r0, 1),
            JZ(r0, Label("postflag_dominant")),
            LDI(r4, 0),
            DJNZ(r2, Label("postflag_recessive_more")),
            JMP(Label("error_delimited")),
            Label("postflag_recessive_more"),
            WAIT(96),
            JMP(Label("error_more")),
            Label("postflag_dominant"),
            ADDI(r4, 1),
            ANDI(r4, 7),
            JZ(r4, Label("postflag_periodic")),
            CMPI(r3, 32),
            JFAIL(Label("postflag_no_bonus_early")),
            CMPI(r6, 6),
            JFAIL(Label("postflag_no_bonus_late")),
            Label("postflag_bonus"),
            CMPI(r6, 6),
            JFAIL(Label("postflag_transmitter")),
            LDI(r7, 8),
            Label("postflag_receiver_add"),
            CALL(Label("increment_rec_leaf")),
            DJNZ(r7, Label("postflag_receiver_add")),
            JMP(Label("postflag_counted")),
            Label("postflag_transmitter"),
            CALL(Label("increment_tec")),
            WAIT(72),
            JMP(Label("postflag_counted")),
            Label("postflag_periodic"),
            WAIT(2),
            JMP(Label("postflag_bonus")),
            Label("postflag_no_bonus_early"),
            WAIT(92),
            JMP(Label("postflag_counted")),
            Label("postflag_no_bonus_late"),
            WAIT(90),
            JMP(Label("postflag_counted")),
            Label("postflag_counted"),
            LDI(r2, 8),
            Label("error_more"),
            DJNZ(r3, Label("error_delay")),
            JMP(Label("recovery_timeout")),
            Label("error_delay"),
            WAIT(255),
            WAIT(38),
            JMP(Label("error_delimiter_sample")),
        ]
        + source[end:]
    )
    # Clearing the run counter adds1 clock before the final delimiter branch.
    replace(
        [Label("error_delimited"), WAIT(255), WAIT(138)],
        [Label("error_delimited"), WAIT(255), WAIT(137)],
    )
    if compact:
        # Early unsupported-header exits remove dead work while the valid path
        # keeps its exact old timing. No counted error case is removed.
        replace(
            [
                JZ(r0, Label("rx_balance_4_yes")),
                LDI(r1, 248),
                LDI(r0, 18),
                STORE(r0, r1),
                JMP(Label("rx_balance_4_end")),
                Label("rx_balance_4_yes"),
                WAIT(4),
                Label("rx_balance_4_end"),
            ],
            [
                JZ(r0, Label("rx_balance_4_yes")),
                LDI(r2, 18),
                JMP(Label("failure")),
                Label("rx_balance_4_yes"),
                WAIT(4),
            ],
        )
        replace(
            [
                JFAIL(Label("rx_balance_5_yes")),
                WAIT(2),
                JMP(Label("rx_balance_5_end")),
                Label("rx_balance_5_yes"),
                LDI(r1, 248),
                LDI(r0, 18),
                STORE(r0, r1),
                Label("rx_balance_5_end"),
            ],
            [JFAIL(Label("postflag_bad_dlc")), WAIT(3)],
        )
        source += [Label("postflag_bad_dlc"), LDI(r2, 18), JMP(Label("failure"))]
        replace([MOV(r0, r6), LDI(r4, 0), LDI(r5, 0)], [MOV(r0, r6), LDI(r5, 0)])
        # Share the two untimed passive suspension waits with a tail-free leaf.
        for label in ["passive_retry_suspend", "passive_success_suspend"]:
            replace(
                [
                    LDI(r3, 8),
                    Label(label),
                    WAIT(255),
                    WAIT(142),
                    DJNZ(r3, Label(label)),
                ],
                [CALL(Label("passive_suspend"))],
            )
        source += [
            Label("passive_suspend"),
            LDI(r3, 8),
            Label("passive_suspend_bit"),
            WAIT(255),
            WAIT(142),
            DJNZ(r3, Label("passive_suspend_bit")),
            RET(),
        ]
        if cleanup:
            # The first polarity observation always consumes one of the six
            # initially remaining samples, whether it resets the run or not.
            replace(
                [
                    Label("flag_started"),
                    LDI(r3, 6),
                    LDI(r1, 1),
                    ORI(r7, 64),
                    WAIT(255),
                    WAIT(38),
                ],
                [Label("flag_started"), LDI(r3, 6), ORI(r7, 64), WAIT(255), WAIT(39)],
            )
            # Return passive state directly in its persistent consumer register.
            replace(
                [
                    Label("passive_state"),
                    LDI(r1, 251),
                    LOAD(r0, r1),
                    ANDI(r0, 128),
                    LDI(r1, 250),
                    LOAD(r1, r1),
                    ANDI(r1, 128),
                    OR(r0, r1),
                    RET(),
                ],
                [
                    Label("passive_state"),
                    LDI(r1, 251),
                    LOAD(r7, r1),
                    ANDI(r7, 128),
                    LDI(r1, 250),
                    LOAD(r1, r1),
                    ANDI(r1, 128),
                    OR(r7, r1),
                    RET(),
                ],
            )
            assert source.count([CALL(Label("passive_state")), MOV(r7, r0)]) == 2
            source = source.replace(
                [CALL(Label("passive_state")), MOV(r7, r0)],
                [CALL(Label("passive_state"))],
            )
            replace(
                [CALL(Label("passive_state")), JZ(r0, Label("retry_ready"))],
                [CALL(Label("passive_state")), JZ(r7, Label("retry_ready"))],
            )
            replace(
                [CALL(Label("passive_state")), JZ(r0, Label("publish"))],
                [CALL(Label("passive_state")), JZ(r7, Label("publish"))],
            )
            replace(
                [LDI(r4, 0), WAIT(63), JMP(Label("flag_drive"))],
                [LDI(r4, 0), WAIT(64), JMP(Label("flag_drive"))],
            )
            replace(
                [LDI(r4, 0), WAIT(29), JMP(Label("flag_drive"))],
                [LDI(r4, 0), WAIT(30), JMP(Label("flag_drive"))],
            )
            # Rotating an isolated0/1 right twice gives the same0/64 operand
            # as six left shifts. Both original wire-cycle budgets stay intact.
            for label, padding in [("balance_118", [WAIT(3)]), ("balance_119", [])]:
                replace(
                    [
                        JZ(r1, Label(f"{label}_yes")),
                        XORI(r0, 64),
                        JMP(Label(f"{label}_end")),
                        Label(f"{label}_yes"),
                        WAIT(1),
                        Label(f"{label}_end"),
                    ]
                    + padding,
                    [ROR(r1), ROR(r1), XOR(r0, r1)] + padding,
                )
    return source.replace_comment_text(
        "GENERATED by build_can_rx_flags_compact.py.",
        "GENERATED by build_can_postflag.py. Shared generic post-flag counter rules.",
    )


if __name__ == "__main__":
    here = Path(__file__).parent
    (here / "can_postflag_unoptimized_candidate.asm").write_text(
        generate(compact=False).to_asm()
    )
    (here / "can_postflag_partial_compaction_candidate.asm").write_text(
        generate(cleanup=False).to_asm()
    )
    (here / "can_postflag_candidate.asm").write_text(generate().to_asm())
