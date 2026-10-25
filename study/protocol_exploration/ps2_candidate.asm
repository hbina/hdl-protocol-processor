# PS/2 host: uio0 clock, uio1 data (open drain); uio2 RX-armed indicator.
# Valid request has 0..1 command byte, parameter[0]=0..64 receive bytes.
# Device clocks both directions; odd parity; link ACK distinct from 0xfa byte.
# Scratch event144..159, receive count160, parity161.
# Status6 edge timeout,13 link NACK,14 framing,15 parity; 0 success.
    SETO 0
    SETOE 4
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
    JZ r0, receive
    LDI r3, 0x11
    PREAD r0, r3
    LDI r1, 161
    LDI r2, 1
    STORE r2, r1
    SETOE 5
    LDI r2, 24
inhibit:
    WAIT 249
    DJNZ r2, inhibit
    SETOE 7
    WAIT 249
    SETOE 6
    LDI r2, 10
tx_bit:
    CMPI r2, 2
    JFAIL tx_not_parity
    LDI r1, 161
    LOAD r0, r1
tx_not_parity:
    CMPI r2, 1
    JFAIL tx_not_stop
    LDI r0, 1
tx_not_stop:
    LDI r3, 0
tx_low:
    IN r1
    ANDI r1, 1
    JZ r1, tx_ready
    WAIT 255
    DJNZ r3, tx_low
    JMP timeout
tx_ready:
    OEBITN r0, 1
    MOV r3, r0
    ANDI r3, 1
    LDI r1, 161
    LOAD r1, r1
    XOR r1, r3
    LDI r3, 161
    STORE r1, r3
    LDI r3, 0
tx_high:
    IN r1
    ANDI r1, 1
    JZ r1, tx_high_wait
    SHR r0
    DJNZ r2, tx_bit
    LDI r3, 0
ack_low:
    IN r1
    ANDI r1, 1
    JZ r1, ack_sample
    WAIT 255
    DJNZ r3, ack_low
    JMP timeout
ack_sample:
    LDI r1, 0
    INBIT r1, 1
    JZ r1, ack_received
    LDI r2, 13
    JMP failure
ack_received:
    LDI r3, 0
ack_idle:
    IN r1
    ANDI r1, 3
    CMPI r1, 3
    JFAIL ack_wait
    JMP receive
ack_wait:
    WAIT 255
    DJNZ r3, ack_idle
    JMP timeout
tx_high_wait:
    WAIT 255
    DJNZ r3, tx_high
    JMP timeout
receive:
    SETOE 4
    LDI r1, 0
    LOAD r0, r1
    LDI r1, 160
    STORE r0, r1
    JZ r0, publish
    SETO 4
rx_byte:
    LDI r1, 161
    LDI r0, 1
    STORE r0, r1
    LDI r0, 0
    LDI r2, 11
rx_bit:
    LDI r3, 0
rx_low:
    IN r1
    ANDI r1, 1
    JZ r1, rx_ready
    WAIT 255
    DJNZ r3, rx_low
    JMP timeout
rx_ready:
    CMPI r2, 11
    JFAIL rx_not_start
    LDI r1, 0
    INBIT r1, 1
    JZ r1, rx_high_begin
    JMP framing
rx_not_start:
    CMPI r2, 2
    JFAIL rx_not_parity
    LDI r1, 0
    INBIT r1, 1
    LDI r3, 161
    LOAD r3, r3
    XOR r1, r3
    JZ r1, rx_high_begin
    LDI r2, 15
    JMP failure
rx_not_parity:
    CMPI r2, 1
    JFAIL rx_data
    LDI r1, 0
    INBIT r1, 1
    JZ r1, framing
    JMP rx_high_begin
rx_data:
    INBIT r0, 1
    MOV r3, r0
    ANDI r3, 1
    LDI r1, 161
    LOAD r1, r1
    XOR r1, r3
    LDI r3, 161
    STORE r1, r3
    ROR r0
rx_high_begin:
    LDI r3, 0
rx_high:
    IN r1
    ANDI r1, 1
    JZ r1, rx_high_wait
    DJNZ r2, rx_bit
    LDI r1, 0x30
    PWRITE r0, r1
    LDI r0, 0
    ADDI r1, 1
    PWRITE r0, r1
    ADDI r1, 1
    PWRITE r0, r1
    LDI r1, 150
    LOAD r0, r1
    ADDI r0, 1
    STORE r0, r1
    LDI r1, 160
    LOAD r0, r1
    ADDI r0, 255
    STORE r0, r1
    JZ r0, publish
    JMP rx_byte
rx_high_wait:
    WAIT 255
    DJNZ r3, rx_high
timeout:
    LDI r2, 6
    JMP failure
framing:
    LDI r2, 14
failure:
    LDI r1, 147
    STORE r2, r1
    LDI r3, 0x11
discard:
    PREAD r0, r3
    JFAIL publish
    JMP discard
publish:
    SETO 0
    SETOE 4
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
