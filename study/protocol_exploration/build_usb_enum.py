#!/usr/bin/env python3
"""Descriptor/configuration firmware; all USB processing remains generic ISA."""

import json
from pathlib import Path

from build_can_rx import Block
from build_usb_address import generate as address_source

DEVICE = bytes([18, 1, 0x10, 1, 0, 0, 0, 8, 0xAD, 0xDE, 0xEF, 0xBE, 0, 1, 0, 0, 0, 1])
CONFIG = bytes([9, 2, 18, 0, 1, 1, 0, 0x80, 50, 9, 4, 0, 0, 0, 0xFF, 0, 0, 0])


def generate(pipeline=True):
    source = address_source()
    # Remove unreachable packet-probe machinery and redundant checks.
    start, end = source.index("prepare_tx:\n"), source.index("tx_packet:\n")
    source = source[:start] + source[end:]
    start, end = source.index("out_length_ok:\n"), source.index("token_match:\n")
    source = source[:start] + "out_length_ok:\nJMP data_gate\n" + source[end:]
    start, end = source.index("token_valid:\n"), source.index("ignore_token:\n")
    source = source[:start] + "token_valid:\nJMP tx_packet\n" + source[end:]
    start, end = source.index("LDI r2, 6\nrecord:"), source.index("LDI r1, 130\n")
    source = (
        source[:start]
        + "LDI r2, 14\nrecord:\nPREAD r0, r3\nDJNZ r2, record\n"
        + source[end:]
    )
    start, end = source.index("# Parameters0..36"), source.index("LDI r4, 157\n")
    source = (
        source[:start]
        + "LDI r0, 155\nLDI r1, 0\nSTORE r1, r0\nADDI r0, 1\nLDI r1, 16\nSTORE r1, r0\n"
        + source[end:]
    )
    start, end = source.index("MOV r0, r5\nSHR r0\n"), source.index("MOV r0, r7\n")
    source = source[:start] + source[end:]
    source = source.replace("LDI r0, 32\nSTORE r0, r4", "LDI r0, 128\nSTORE r0, r4")
    source = source.replace("LDI r1, 32\nSTORE r1, r0", "LDI r1, 128\nSTORE r1, r0")
    # Boot and reset initialize descriptor state, source pointer and configuration.
    source = source.replace("JMP rearm\nrearm:", "CALL enum_init\nJMP rearm\nrearm:", 1)
    source = source.replace("reset_release:\n", "CALL enum_init\nreset_release:\n", 1)
    source = source.replace(
        "LDI r7, 160\nLOAD r1, r7", "LDI r1, 160\nLOAD r1, r1\nLDI r7, 181\nLOAD r7, r7"
    )
    # Restore ordinary vendor buffer/PID on every accepted SETUP. This happens
    # before DATA ACK; descriptor handlers overwrite the pointer as needed.
    marker = "LDI r0, 145\nLOAD r0, r0\nCMPI r0, 0\nJFAIL vendor_setup"
    source = source.replace(
        marker,
        """LDI r0, 181
LDI r1, 160
STORE r1, r0
LDI r0, 190
LDI r1, 0
STORE r1, r0
LDI r0, 160
LDI r1, 0x4b
STORE r1, r0
LDI r0, 145
LOAD r0, r0
CMPI r0, 0x80
JFAIL maybe_standard_write
JMP standard_read
maybe_standard_write:
CMPI r0, 0
JFAIL vendor_setup""",
    )
    source = source.replace(
        "CMPI r0, 5\nJFAIL unsupported\nJMP setup_address",
        """CMPI r0, 5
JFAIL maybe_set_config
LDI r5, 0
JMP setup_address
maybe_set_config:
CMPI r0, 9
JFAIL unsupported
LDI r5, 1
JMP setup_address""",
    )
    source = source.replace(
        "address_fields_ok:\n",
        "address_fields_ok:\nJZ r5, address_value\nJMP setup_config\naddress_value:\n",
        1,
    )
    # Commit configuration only when the shared standard-write status is ACKed.
    source = source.replace(
        "LDI r0, 175\nSTORE r4, r0\nLDI r6, 16",
        "LDI r0, 188\nLOAD r1, r0\nADDI r0, 1\nSTORE r1, r0\nLDI r0, 175\nSTORE r4, r0\nLDI r6, 16",
    )
    source = source.replace(
        "LDI r0, 182\nLDI r1, 0\nSTORE r1, r0\nLDI r0, 160\nLDI r1, 0x4b\nSTORE r1, r0\nLDI r0, 171\nLDI r1, 7",
        "standard_write_status:\nLDI r0, 182\nLDI r1, 0\nSTORE r1, r0\nLDI r0, 160\nLDI r1, 0x4b\nSTORE r1, r0\nLDI r0, 171\nLDI r1, 7",
    )
    source = source.replace(
        "commit_address:\n",
        "commit_address:\nLDI r0, 189\nLOAD r1, r0\nLDI r0, 188\nSTORE r1, r0\n",
        1,
    )
    # Standard-read status completes the control transfer, not the runtime job.
    source = source.replace(
        "LDI r0, 172\nLOAD r2, r0\nLDI r0, 134",
        "LDI r0, 190\nLOAD r0, r0\nJZ r0, publish_vendor\nLDI r0, 171\nLDI r1, 0\nSTORE r1, r0\nJMP rearm\npublish_vendor:\nLDI r0, 172\nLOAD r2, r0\nLDI r0, 134",
    )
    # First implementation: update descriptor source after ACK; a separate
    # minimum-gap regression measures this path rather than assuming it fits.
    source = source.replace(
        "ack_vendor_read:\nCMPI r1, 11\nJFAIL rearm\nLDI r1, 5",
        "ack_vendor_read:\nCMPI r1, 11\nJFAIL rearm\nLDI r0, 190\nLOAD r0, r0\nJZ r0, vendor_ack_done\nJMP descriptor_ack\nvendor_ack_done:\nLDI r0, 171\nLDI r1, 5",
    )
    tail = """
enum_init:
LDI r0, 181
LDI r1, 160
STORE r1, r0
LDI r0, 187
LDI r1, 0
LDI r2, 4
enum_clear:
STORE r1, r0
ADDI r0, 1
DJNZ r2, enum_clear
RET
setup_config:
CMPLTI r4, 2
JFAIL unsupported
LDI r0, 189
STORE r4, r0
LDI r0, 155
LOAD r1, r0
LDI r0, 175
STORE r1, r0
LDI r0, 156
LOAD r1, r0
LDI r0, 176
STORE r1, r0
JMP standard_write_status
standard_read:
LDI r0, 146
LOAD r0, r0
CMPI r0, 8
JFAIL maybe_descriptor
LDI r1, 187
LDI r4, 1
JMP begin_standard_read
maybe_descriptor:
CMPI r0, 6
JFAIL unsupported
LDI r0, 147
LOAD r0, r0
JZ r0, descriptor_index_ok
JMP unsupported
descriptor_index_ok:
LDI r0, 148
LOAD r0, r0
CMPI r0, 1
JFAIL config_descriptor
LDI r1, 40
JMP descriptor_length
config_descriptor:
CMPI r0, 2
JFAIL unsupported
LDI r1, 58
descriptor_length:
LDI r0, 151
LOAD r4, r0
ADDI r0, 1
LOAD r0, r0
JZ r0, short_length
LDI r4, 18
short_length:
CMPLTI r4, 19
JFAIL cap_length
JMP begin_standard_read
cap_length:
LDI r4, 18
begin_standard_read:
JZ r4, form_error
LDI r0, 181
STORE r1, r0
CMPLTI r4, 9
JFAIL first_full_packet
MOV r1, r4
LDI r4, 0
JMP store_packet_size
first_full_packet:
LDI r1, 8
ADDI r4, 248
store_packet_size:
LDI r0, 182
STORE r1, r0
LDI r0, 187
STORE r4, r0
LDI r0, 190
LDI r1, 1
STORE r1, r0
LDI r0, 171
LDI r1, 3
STORE r1, r0
JMP control_ack
descriptor_ack:
LDI r0, 187
LOAD r4, r0
JZ r4, descriptor_done
LDI r0, 181
LOAD r1, r0
ADDI r1, 8
STORE r1, r0
LDI r0, 160
LOAD r1, r0
XORI r1, 136
STORE r1, r0
JMP begin_next_packet
descriptor_done:
LDI r0, 171
LDI r1, 5
STORE r1, r0
JMP rearm
begin_next_packet:
CMPLTI r4, 9
JFAIL next_full_packet
MOV r1, r4
LDI r4, 0
JMP next_size
next_full_packet:
LDI r1, 8
ADDI r4, 248
next_size:
LDI r0, 182
STORE r1, r0
LDI r0, 187
STORE r4, r0
LDI r0, 171
LDI r1, 3
STORE r1, r0
JMP rearm
"""
    result = (source + tail).replace(
        "# GENERATED by build_usb_address.py.", "# GENERATED by build_usb_enum.py."
    )
    return pipeline_ack(result) if pipeline else result


def pipeline_ack(source):
    # ACK packet has no CRC. Use EOP padding to prefetch staged metadata while
    # preserving the exact sample schedule on ACK and non-ACK paths.
    prefetch = Block("LDI r1, 186\nLDI r0, 4\nSTORE r0, r1\nCMPI r7, 145")
    ack = Block("")
    for reg, address in [
        ("r1", 171),
        ("r2", 192),
        ("r3", 193),
        ("r4", 194),
        ("r5", 195),
        ("r6", 190),
    ]:
        ack.add(f"LDI {reg}, {address}\nLOAD {reg}, {reg}")
    prefetch.add(Block.choose("JFAIL", "LDI r6, 155\nLOAD r6, r6", ack))
    prefetch.add(Block.delay(26 - prefetch.cycles))
    old = "LDI r6, 155\nLOAD r6, r6\nLDI r1, 186\nLDI r0, 4\nSTORE r0, r1\nWAIT 18"
    assert source.count(old) == 1
    source = source.replace(old, "\n".join(prefetch.lines))
    # Classify one-byte handshakes before ordinary packet dispatch; token paths
    # retain the original two-cycle length-test overhead.
    old = "CMPLTI r7, 145\nJFAIL length_ok\nJMP form_error"
    source = source.replace(
        old,
        """
CMPI r7, 145
JFAIL length_ok
LDI r0, 144
LOAD r0, r0
CMPI r0, 0xd2
JFAIL rearm
CMPI r1, 11
JFAIL other_host_ack
JZ r6, read_ack_done
JZ r3, read_ack_done
LDI r0, 181
STORE r2, r0
LDI r0, 182
STORE r3, r0
LDI r0, 187
STORE r4, r0
LDI r0, 160
STORE r5, r0
LDI r0, 171
LDI r1, 3
STORE r1, r0
JMP rearm
read_ack_done:
LDI r0, 171
LDI r1, 5
STORE r1, r0
JMP rearm
other_host_ack:
CMPI r1, 10
JFAIL maybe_address_ack
LDI r0, 171
LDI r1, 4
STORE r1, r0
JMP rearm
maybe_address_ack:
CMPI r1, 15
JFAIL rearm
JMP commit_address
""",
    )
    start, end = (
        source.index("control_maybe_ack:\n"),
        source.index("control_in_gate:\n"),
    )
    source = source[:start] + "control_maybe_ack:\nJMP control_in_gate\n" + source[end:]
    start, end = source.index("descriptor_ack:\n"), source.index("begin_next_packet:\n")
    source = source[:start] + source[end:]
    source = source[: source.index("begin_next_packet:\n")]
    # Precompute next-descriptor metadata during the first SYNC cell. No packet
    # state commits until ACK; retries recalculate the same metadata.
    staged = Block(
        "LDI r0, 181\nLOAD r4, r0\nADDI r4, 8\nLDI r0, 192\nSTORE r4, r0\nLDI r0, 187\nLOAD r4, r0\nCMPLTI r4, 9"
    )
    staged.add(
        Block.choose("JFAIL", "LDI r5, 8\nADDI r4, 248", "MOV r5, r4\nLDI r4, 0")
    )
    staged.add(
        "LDI r0, 193\nSTORE r5, r0\nADDI r0, 1\nSTORE r4, r0\nLDI r0, 160\nLOAD r4, r0\nXORI r4, 136\nLDI r0, 195\nSTORE r4, r0\nLDI r0, 36\nLDI r4, 1\nLDI r5, 8"
    )
    staged.add(Block.delay(32 - staged.cycles))
    old = "stream_sync:\nWAIT 20\nSETO 36\nWAIT 31"
    assert source.count(old) == 1
    return source.replace(
        old, "stream_sync:\nWAIT 20\nSETO 36\n" + "\n".join(staged.lines)
    )


if __name__ == "__main__":
    Path(__file__).with_name("usb_enum_candidate.asm").write_text(generate())
    Path(__file__).with_name("usb_enum_unoptimized_candidate.asm").write_text(
        generate(False)
    )
    Path(__file__).with_name("usb_enum_constants.json").write_text(
        json.dumps({"device": list(DEVICE), "configuration": list(CONFIG)}, indent=2)
        + "\n"
    )
