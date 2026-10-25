#!/usr/bin/env python3
"""Persistent CAN counter/passive/bus-off experiment in generic firmware."""

from pathlib import Path

from build_can_resync import generate as resync_source
from build_can_rx import Block, load, put


def generate():
    source = resync_source()

    def replace(old, new):
        nonlocal source
        assert source.count(old) == 1, old
        source = source.replace(old, new)

    # Three bytes persist across requests; the operation lives in a register.
    boot = Block().add(put(250, 0)).add(put(251, 0)).add(put(255, 0))
    replace(
        "SETO 1\nSETOE 1\nidle:", "\n".join(boot.lines) + "\nSETO 1\nSETOE 1\nidle:"
    )
    replace("PREAD r0, r3\nLDI r1, 250\nSTORE r0, r1", "PREAD r0, r3\nMOV r6, r0")
    replace("LDI r1, 250\nLOAD r0, r1\nLDI r4, 0", "MOV r0, r6\nLDI r4, 0")
    replace(
        "LDI r6, 0\nCMPI r0, 3",
        """LDI r6, 0
CMPI r0, 6
JFAIL not_counter_query
JMP counter_query
not_counter_query:
CMPI r0, 5
JFAIL not_bus_recovery
JMP bus_recovery
not_bus_recovery:
MOV r7, r0
LDI r1, 255
LOAD r0, r1
JZ r0, node_available
JMP bus_off_reject
node_available:
MOV r0, r7
CMPI r0, 3""",
    )
    replace(
        "ordinary_dispatch:\nCMPI r0, 2\nJFAIL rx_entry\nJMP tx_entry",
        "ordinary_dispatch:\nCMPI r0, 2\nJFAIL rx_entry\nLDI r6, 5\nJMP tx_entry",
    )

    # Single-level generic leaves compact otherwise repeated software work.
    emit = """LDI r3, 0x30
PWRITE r0, r3
LDI r0, 0
ADDI r3, 1
PWRITE r0, r3
ADDI r3, 1
PWRITE r0, r3"""
    transfer = emit.split("\n", 1)[1]
    assert source.count(transfer) == 4
    source = source.replace(transfer, "CALL emit_byte")
    source = source.replace("LDI r3, 0x30\nCALL emit_byte", "CALL emit_byte")
    leaves = Block("emit_byte:\n" + emit + "\nRET")
    increment = load(251).add("ADDI r0, 8\nSTORE r0, r1\nCMPLTI r0, 8")
    increment.add(Block.choose("JFAIL", "", put(255, 1).add("SETOE 0")))
    inc_call = Block("CALL increment_tec", cycles=1 + increment.cycles + 1)
    leaves.add("increment_tec:").add(increment).add("RET")

    # Equalize every TX mismatch path to18 clocks at tx_fault entry.
    begin = source.index("tx_mismatch:\n")
    end = source.index("tx_tx_tail:\n", begin)
    source = (
        source[:begin]
        + """tx_mismatch:
SETO 1
JZ r0, dominant_bit_error
LDI r1, 244
LOAD r0, r1
JZ r0, tx_arbitration_check
WAIT 3
JMP tx_bit_error
dominant_bit_error:
WAIT 7
JMP tx_bit_error
tx_arbitration_check:
LDI r1, 247
LOAD r0, r1
CMPLTI r0, 157
JFAIL tx_bit_error
CMPI r6, 2
JFAIL legacy_arbitration_loss
JMP winner_loss
legacy_arbitration_loss:
LDI r2, 22
JMP failure
tx_bit_error:
LDI r2, 21
JMP tx_fault
"""
        + source[end:]
    )
    begin = source.index("ack_error:\n")
    end = source.index("error_delimiter_sample:\n", begin)
    flag = Block("""ack_error:
LDI r2, 24
WAIT 11
JMP tx_fault
tx_fault:
LDI r1, 131
STORE r2, r1
LDI r1, 251
LOAD r0, r1
ANDI r0, 128
MOV r7, r0
LDI r1, 250
LOAD r0, r1
ANDI r0, 128
OR r7, r0
LDI r4, 0
JZ r7, active_flag_start""")
    # Entry18 +status3 +passive10 +observed reset1 +branch1 =33.
    flag.add(Block.delay(67)).add("SETO 1\nJMP flag_started\nactive_flag_start:")
    flag.add(Block.delay(67)).add("SETO 0\nJMP flag_started\nflag_started:\nLDI r3, 6")
    flag.add(Block.delay(297)).add("""flag_sample:
INBIT r0, 1
ANDI r0, 1
XORI r0, 1
OR r4, r0
DJNZ r3, flag_more""")
    flag.add(Block.delay(95)).add("SETO 1\nJMP flag_finished\nflag_more:")
    flag.add(Block.delay(394)).add("JMP flag_sample\nflag_finished:")
    # Release+JMP =2 clocks after flag end. Decide counter exceptions off wire.
    ack_increment = Block.choose("JZ r7", inc_call, Block.choose("JZ r4", "", inc_call))
    stuff_increment = load(244).add(
        Block.choose(
            "JZ r0",
            inc_call,
            load(246).add(
                Block.choose(
                    "JZ r0",
                    inc_call,
                    load(247)
                    .add("CMPLTI r0, 157")
                    .add(Block.choose("JFAIL", inc_call)),
                )
            ),
        )
    )
    counter = Block("CMPI r2, 21").add(
        Block.choose("JFAIL", ack_increment, stuff_increment)
    )
    flag.add(counter).add("LDI r2, 8\nLDI r3, 32")
    flag.add(Block.delay(300 - 2 - counter.cycles - 2 - 1)).add(
        "JMP error_delimiter_sample\n"
    )
    source = source[:begin] + "\n".join(flag.lines) + "\n" + source[end:]

    # Complete intermission, then retire/retry under the persistent fault state.
    begin = source.index(
        "CMPLTI r5, 3\nJFAIL retry_exhausted", source.index("error_delimited:")
    )
    end = source.index("recovery_timeout:\n", begin)
    retry = Block("""WAIT 96
LDI r1, 255
LOAD r0, r1
JZ r0, not_bus_off
LDI r2, 26
JMP failure
not_bus_off:
CMPI r6, 5
JFAIL may_retry
JMP publish
may_retry:
CMPLTI r5, 3
JFAIL publish
LDI r1, 251
LOAD r0, r1
ANDI r0, 128
LDI r1, 250
LOAD r1, r1
ANDI r1, 128
OR r0, r1
JZ r0, retry_ready
LDI r3, 8
passive_retry_suspend:
WAIT 255
WAIT 142
DJNZ r3, passive_retry_suspend
retry_ready:""")
    for address, value in [(242, 1), (243, 0), (245, 0), (247, 144)]:
        retry.add(put(address, value))
    retry.add("LDI r4, 0\nLDI r7, 0\nADDI r5, 1\nJMP tx_tx_cell")
    source = source[:begin] + "\n".join(retry.lines) + "\n" + source[end:]
    # Success updates counters once, independent of the number of retries.
    replace("tx_tail:\nINBIT", "tx_tail:\nINBIT")  # Guard the unique tail label.
    replace("DJNZ r2, tx_tail\nJMP publish", "DJNZ r2, tx_tail\nJMP tx_success")
    replace(
        "rx_output_done:\n",
        """rx_output_done:
LDI r1, 250
LOAD r0, r1
CMPLTI r0, 128
JFAIL receive_counter_passive
JZ r0, receive_counter_done
ADDI r0, 255
JMP receive_counter_store
receive_counter_passive:
LDI r0, 127
receive_counter_store:
STORE r0, r1
receive_counter_done:
""",
    )
    replace(
        "failure:\nSETO 1\nLDI r1, 131\nSTORE r2, r1\npublish:",
        """failure:
SETO 1
LDI r1, 131
STORE r2, r1
JZ r6, receiver_failure
CMPI r6, 3
JFAIL publish
receiver_failure:
CMPLTI r2, 16
JFAIL receiver_error_range
JMP publish
receiver_error_range:
CMPLTI r2, 21
JFAIL publish
CMPI r2, 18
JFAIL increment_rec
JMP publish
increment_rec:
LDI r1, 250
LOAD r0, r1
CMPI r0, 255
JFAIL rec_not_saturated
JMP publish
rec_not_saturated:
ADDI r0, 1
STORE r0, r1
publish:""",
    )

    extra = Block("""tx_success:
LDI r1, 251
LOAD r0, r1
JZ r0, tx_counter_done
ADDI r0, 255
STORE r0, r1
tx_counter_done:""").add(put(131, 0))
    extra.add("""LDI r1, 251
LOAD r0, r1
ANDI r0, 128
LDI r1, 250
LOAD r1, r1
ANDI r1, 128
OR r0, r1
JZ r0, publish
LDI r3, 8
passive_success_suspend:
WAIT 255
WAIT 142
DJNZ r3, passive_success_suspend
JMP publish
counter_query:""")
    for address in [251, 255, 250]:
        extra.add(load(address)).add("CALL emit_byte")
    extra.add(put(134, 3)).add(
        "JMP publish\nbus_off_reject:\nLDI r3, 0x11\ndrain_rejected_input:\nPREAD r0, r3\nJFAIL rejected_drained\nJMP drain_rejected_input\nrejected_drained:\nLDI r2, 26\nJMP failure"
    )
    extra.add("""bus_recovery:
LDI r1, 255
LOAD r0, r1
JZ r0, publish
LDI r2, 128
LDI r3, 11
LDI r4, 0
LDI r7, 16
bus_recovery_sample:
INBIT r0, 1
ANDI r0, 1
JZ r0, bus_recovery_dominant
DJNZ r3, bus_recovery_not_group
LDI r3, 11
DJNZ r2, bus_recovery_budget
JMP bus_recovered
bus_recovery_not_group:
NOP
JMP bus_recovery_budget
bus_recovery_dominant:
LDI r3, 11
NOP
NOP
bus_recovery_budget:
DJNZ r4, bus_recovery_fast
DJNZ r7, bus_recovery_budget_ready
LDI r2, 6
JMP failure
bus_recovery_fast:
NOP
bus_recovery_budget_ready:""")
    extra.add(Block.delay(391)).add("JMP bus_recovery_sample\nbus_recovered:")
    extra.add(Block.delay(400)).add(put(250, 0)).add(put(251, 0)).add(put(255, 0))
    extra.add("SETOE 1\nJMP publish")
    return (source + "\n".join(extra.lines + leaves.lines) + "\n").replace(
        "# GENERATED by build_can_resync.py.",
        "# GENERATED by build_can_fault.py. Persistent counters; generic leaf calls.",
    )


if __name__ == "__main__":
    Path(__file__).with_name("can_fault_candidate.asm").write_text(generate())
