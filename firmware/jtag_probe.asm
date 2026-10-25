# Generic-ISA JTAG controller probe. TCK0, TMS1, TDI2, TDO3.
# Reset TAP once at boot; preserve instruction selection between requests.
# parameter[0]: 0=DR, 1=IR; parameter[1]: valid bits in last byte, 1..8.
# 1..64 input bytes, LSB-first; outputs same count, final byte high-aligned.
# Valid request envelopes only. Scratch: event144..159, remaining count160.
    SETO 2
    SETOE 7
    LDI r2, 5
tap_reset:
    WAIT 249
    SETO 3
    WAIT 249
    SETO 2
    DJNZ r2, tap_reset
    SETO 0
    WAIT 249
    SETO 1
    WAIT 249
    SETO 0
idle:
    LDI r3, 0x22
    PREAD r0, r3
    JFAIL idle
    LDI r1, 144
    STORE r0, r1
    PREAD r0, r3
    ADDI r1, 1
    STORE r0, r1
    LDI r2, 14
record:
    PREAD r0, r3
    DJNZ r2, record
    LDI r1, 146
    LDI r0, 1
    STORE r0, r1
    ADDI r1, 1
    LDI r2, 13
    LDI r0, 0
clear_event:
    STORE r0, r1
    ADDI r1, 1
    DJNZ r2, clear_event
    LDI r3, 2
    PREAD r0, r3
    LDI r1, 148
    STORE r0, r1
    LDI r1, 150
    STORE r0, r1
    LDI r1, 160
    STORE r0, r1
    JZ r0, publish
    # Run-Test/Idle -> Select-DR; one more TMS-high clock selects IR.
    SETO 2
    WAIT 249
    SETO 3
    WAIT 249
    SETO 2
    LDI r1, 0
    LOAD r0, r1
    JZ r0, capture
    WAIT 249
    SETO 3
    WAIT 249
    SETO 2
capture:
    SETO 0
    WAIT 249
    SETO 1
    WAIT 249
    SETO 0
    WAIT 249
    SETO 1
    WAIT 249
    SETO 0
byte:
    LDI r3, 0x11
    PREAD r0, r3
    LDI r1, 0
    LDI r2, 16
    LDI r3, 160
    LOAD r3, r3
    CMPI r3, 1
    JFAIL bit
    LDI r3, 1
    LOAD r2, r3
    SHL r2
    ORI r2, 1
bit:
    # r2=2*remaining_bits+last_byte; value3 identifies the final scan bit.
    CMPI r2, 3
    JFAIL shift
    LDI r3, 1
    OUTBIT r3, 1
shift:
    OUTBIT r0, 2
    SHR r0
    WAIT 249
    LDI r3, 1
    OUTBIT r3, 0
    WAIT 249
    INBIT r1, 3
    ROR r1
    LDI r3, 0
    OUTBIT r3, 0
    ADDI r2, 254
    CMPLTI r2, 2
    JFAIL bit
    LDI r3, 0x30
    PWRITE r1, r3
    LDI r0, 0
    ADDI r3, 1
    PWRITE r0, r3
    ADDI r3, 1
    PWRITE r0, r3
    LDI r3, 160
    LOAD r0, r3
    ADDI r0, 255
    STORE r0, r3
    JZ r0, update
    JMP byte
update:
    # Exit1 -> Update -> Run-Test/Idle, with TMS setup before each clock.
    WAIT 249
    SETO 3
    WAIT 249
    SETO 2
    SETO 0
    WAIT 249
    SETO 1
    WAIT 249
    SETO 0
publish:
    LDI r1, 144
    LDI r2, 16
    LDI r3, 0x40
event:
    LOAD r0, r1
    PWRITE r0, r3
    ADDI r1, 1
    DJNZ r2, event
    LDI r0, 0
    ADDI r3, 1
    PWRITE r0, r3
    JMP idle
