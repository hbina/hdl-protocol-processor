# Generic bounded ECHO/XOR dispatcher. Scratch: request 128..143, event 144..159.
idle:
    LDI r3, 0x22
    PREAD r0, r3
    JFAIL idle
    LDI r1, 128
    LDI r2, 16
request:
    STORE r0, r1
    ADDI r1, 1
    DJNZ r2, next
initialize:
    LDI r1, 144
    LDI r2, 16
    LDI r0, 0
zero_event:
    STORE r0, r1
    ADDI r1, 1
    DJNZ r2, zero_event
    # Preserve request ID.
    LDI r1, 128
    LOAD r0, r1
    LDI r1, 144
    STORE r0, r1
    LDI r1, 129
    LOAD r0, r1
    LDI r1, 145
    STORE r0, r1
    LDI r0, 1
    LDI r1, 146
    STORE r0, r1
    # Actual buffered occupancy is reported, including discarded input.
    LDI r3, 2
    PREAD r0, r3
    LDI r1, 148
    STORE r0, r1
    # Flags and reserved bytes must all be zero.
    LDI r1, 131
    LOAD r0, r1
    LDI r1, 140
    LDI r2, 4
reserved:
    LOAD r3, r1
    OR r0, r3
    ADDI r1, 1
    DJNZ r2, reserved
    LDI r2, 1
    CMPI r0, 0
    JFAIL reject
    # High bytes of address, argument length, input count, output limit.
    LDI r1, 133
    LDI r3, 4
high_bytes:
    LOAD r2, r1
    OR r0, r2
    ADDI r1, 2
    DJNZ r3, high_bytes
    LDI r2, 1
    CMPI r0, 0
    JFAIL reject
    # Input must match prebuffered data; output limit must cover it and <=64.
    LDI r1, 136
    LOAD r0, r1
    LDI r1, 148
    LOAD r3, r1
    XOR r0, r3
    LDI r2, 4
    CMPI r0, 0
    JFAIL reject
    LDI r1, 138
    LOAD r0, r1
    CMPLTI r0, 65
    JFAIL reject
    CMPLT r0, r3
    JFAIL operation
    JMP reject
operation:
    LDI r1, 130
    LOAD r0, r1
    LDI r2, 2
    CMPI r0, 1
    JFAIL check_xor
    # ECHO requires zero address and length.
    LDI r1, 132
    LOAD r0, r1
    LDI r1, 134
    LOAD r3, r1
    OR r0, r3
    LDI r2, 3
    CMPI r0, 0
    JFAIL reject
    LDI r2, 0
    JMP transfer
check_xor:
    CMPI r0, 2
    JFAIL reject
    LDI r2, 3
    LDI r1, 134
    LOAD r0, r1
    CMPI r0, 1
    JFAIL reject
    LDI r1, 132
    LOAD r1, r1
    # Restrict parameter addresses to the host half.
    CMPLTI r1, 128
    JFAIL reject
    LOAD r2, r1
transfer:
    LDI r1, 148
    LOAD r1, r1
byte:
    JZ r1, finish
    LDI r3, 0x11
    PREAD r0, r3
    XOR r0, r2
    LDI r3, 0x30
    PWRITE r0, r3
    LDI r0, 0
    LDI r3, 0x31
    PWRITE r0, r3
    LDI r3, 0x32
    PWRITE r0, r3
    DJNZ r1, byte
finish:
    LDI r1, 148
    LOAD r0, r1
    LDI r1, 150
    STORE r0, r1
    JMP publish
reject:
    LDI r1, 147
    STORE r2, r1
    LDI r3, 0x11
 discard:
    PREAD r0, r3
    JFAIL publish
    JMP discard
publish:
    LDI r1, 144
    LDI r2, 16
    LDI r3, 0x40
 event:
    LOAD r0, r1
    PWRITE r0, r3
    ADDI r1, 1
    DJNZ r2, event
    LDI r3, 0x41
    PWRITE r0, r3
    JMP idle

next:
    PREAD r0, r3
    JMP request
