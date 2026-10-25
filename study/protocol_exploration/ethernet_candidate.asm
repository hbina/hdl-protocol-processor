# Minimum-frame SNI MAC exploration. Does not fit actual 128-word core.
# uio0 TXD,1 TX_EN,2 TX_CLK,3 RXD,4 RX_CLK,5 CRS; only0/1 outputs.
# parameter[0]=0 TX (60 input bytes, no output),1 RX (64 outputs including FCS).
# Firmware generates preamble/FCS; RX captures before offline CRC checking.
# Scratch event144..159; wire buffer160..231; CRC232..235; pointer236,
# bytes237, bits239, feedback240. No protocol-aware hardware.
# Status6 no CRS,16 bad FCS,17 CRS still asserted beyond minimum frame.
    SETO 2
    SETOE 1
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
    LDI r1, 0
    LOAD r0, r1
    JZ r0, prepare_tx
    LDI r3, 0
    LDI r2, 0
crs_wait:
    IN r0
    ANDI r0, 0x20
    JZ r0, crs_tick
    LDI r1, 168
    LDI r2, 64
    LDI r0, 0
    LDI r3, 0
clock_low:
    INBIT r0, 4
    ANDI r0, 1
    JZ r0, clock_high_init
    DJNZ r3, clock_low
    JMP no_clock
clock_high_init:
    LDI r3, 0
clock_high:
    INBIT r0, 4
    ANDI r0, 1
    JZ r0, clock_high_tick
    LDI r3, 0
sfd_search:
    INBIT r0, 3
    ROR r0
    CMPI r0, 0xd5
    DJNZ r3, sfd_check
    JMP no_clock
sfd_check:
    JFAIL sfd_search
rx_byte:
    INBIT r0, 3
    ROR r0
    WAIT 1
    INBIT r0, 3
    ROR r0
    WAIT 2
    INBIT r0, 3
    ROR r0
    WAIT 2
    INBIT r0, 3
    ROR r0
    WAIT 2
    INBIT r0, 3
    ROR r0
    WAIT 2
    INBIT r0, 3
    ROR r0
    WAIT 2
    INBIT r0, 3
    ROR r0
    WAIT 2
    INBIT r0, 3
    ROR r0
    STORE r0, r1
    ADDI r1, 1
    DJNZ r2, rx_byte
    WAIT 8
    IN r0
    ANDI r0, 0x20
    JZ r0, checksum
    LDI r2, 17
    JMP failure
crs_tick:
    DJNZ r3, crs_wait
    DJNZ r2, crs_wait
    JMP no_clock
clock_high_tick:
    DJNZ r3, clock_high
no_clock:
    LDI r2, 6
    JMP failure
prepare_tx:
    LDI r1, 160
    LDI r0, 0x55
    LDI r2, 7
preamble:
    STORE r0, r1
    ADDI r1, 1
    DJNZ r2, preamble
    LDI r0, 0xd5
    STORE r0, r1
    ADDI r1, 1
    LDI r2, 60
    LDI r3, 0x11
input:
    PREAD r0, r3
    STORE r0, r1
    ADDI r1, 1
    DJNZ r2, input
checksum:
    LDI r1, 232
    LDI r0, 255
    LDI r2, 4
crc_init:
    STORE r0, r1
    ADDI r1, 1
    DJNZ r2, crc_init
    LDI r0, 168
    STORE r0, r1
    ADDI r1, 1
    LDI r0, 60
    LDI r2, 0
    LOAD r2, r2
    JZ r2, crc_count
    LDI r0, 64
crc_count:
    STORE r0, r1
crc_byte:
    LDI r1, 236
    LOAD r1, r1
    LOAD r0, r1
    LDI r1, 232
    LOAD r2, r1
    XOR r0, r2
    STORE r0, r1
    LDI r0, 8
    LDI r1, 239
    STORE r0, r1
crc_bit:
    LDI r1, 232
    LOAD r0, r1
    ANDI r0, 1
    LDI r1, 240
    STORE r0, r1
    LDI r0, 0
    LDI r1, 235
crc_shift:
    LOAD r3, r1
    ROR r3
    MOV r2, r3
    ANDI r2, 128
    ANDI r3, 127
    OR r3, r0
    STORE r3, r1
    MOV r0, r2
    ADDI r1, 255
    CMPI r1, 231
    JFAIL crc_shift
    LDI r1, 240
    LOAD r0, r1
    JZ r0, crc_no_xor
    LDI r1, 232
    LOAD r0, r1
    XORI r0, 0x20
    STORE r0, r1
    ADDI r1, 1
    LOAD r0, r1
    XORI r0, 0x83
    STORE r0, r1
    ADDI r1, 1
    LOAD r0, r1
    XORI r0, 0xb8
    STORE r0, r1
    ADDI r1, 1
    LOAD r0, r1
    XORI r0, 0xed
    STORE r0, r1
crc_no_xor:
    LDI r1, 239
    LOAD r0, r1
    ADDI r0, 255
    STORE r0, r1
    JZ r0, crc_next_byte
    JMP crc_bit
crc_next_byte:
    LDI r1, 236
    LOAD r0, r1
    ADDI r0, 1
    STORE r0, r1
    ADDI r1, 1
    LOAD r0, r1
    ADDI r0, 255
    STORE r0, r1
    JZ r0, crc_done
    JMP crc_byte
crc_done:
    LDI r1, 0
    LOAD r0, r1
    JZ r0, tx_fcs
    LDI r1, 232
    LOAD r0, r1
    CMPI r0, 0xe3
    JFAIL bad_fcs
    ADDI r1, 1
    LOAD r0, r1
    CMPI r0, 0x20
    JFAIL bad_fcs
    ADDI r1, 1
    LOAD r0, r1
    CMPI r0, 0xbb
    JFAIL bad_fcs
    ADDI r1, 1
    LOAD r0, r1
    CMPI r0, 0xde
    JFAIL bad_fcs
    LDI r1, 168
    LDI r2, 64
    LDI r3, 0x30
output:
    LOAD r0, r1
    PWRITE r0, r3
    LDI r0, 0
    ADDI r3, 1
    PWRITE r0, r3
    ADDI r3, 1
    PWRITE r0, r3
    ADDI r3, 254
    ADDI r1, 1
    DJNZ r2, output
    LDI r0, 64
    LDI r1, 150
    STORE r0, r1
    JMP publish
tx_fcs:
    LDI r1, 232
    LDI r2, 228
    LDI r3, 4
fcs_byte:
    LOAD r0, r1
    XORI r0, 255
    STORE r0, r2
    ADDI r1, 1
    ADDI r2, 1
    DJNZ r3, fcs_byte
    LDI r1, 160
    LOAD r0, r1
    ADDI r1, 1
    LDI r2, 72
    # Preload first data bit while TX_EN is pulled down. A 25%-duty PHY TX_CLK
    # requires aligning to its rising edge and delaying into the next LOW
    # interval; two-flop clock observation cannot be treated as the wire edge.
    OUTBIT r0, 0
    WAITPIN 2, 0
    WAITPIN 2, 1
    WAIT 2
    SETOE 3
tx_byte:
    OUTBIT r0, 0
    ROR r0
    WAIT 2
    OUTBIT r0, 0
    ROR r0
    WAIT 2
    OUTBIT r0, 0
    ROR r0
    WAIT 2
    OUTBIT r0, 0
    ROR r0
    WAIT 2
    OUTBIT r0, 0
    ROR r0
    WAIT 2
    OUTBIT r0, 0
    ROR r0
    WAIT 2
    OUTBIT r0, 0
    ROR r0
    WAIT 2
    OUTBIT r0, 0
    LOAD r0, r1
    ADDI r1, 1
    DJNZ r2, tx_byte
    SETOE 1
    JMP publish
bad_fcs:
    LDI r2, 16
failure:
    LDI r1, 147
    STORE r2, r1
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
